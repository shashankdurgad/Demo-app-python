"""Langfuse tracing setup for the Ledgerline agents.

Follows ``add_langfuse_for_multi_agent`` and the Langfuse instrumentation skill:
init after env is loaded, mask PII, OpenAI drop-in for generations, ``flush()``
on short scripts.

Sits alongside LangSmith, Galileo, and Braintrust. Enabled when both
``LANGFUSE_PUBLIC_KEY`` and ``LANGFUSE_SECRET_KEY`` are set.

Langfuse SDK v4 shares process-wide OpenTelemetry context with other OTel
backends, so child observations would otherwise parent to span ids Langfuse
never ingested. We give Langfuse its own TracerProvider and re-parent new
Langfuse observations under the last Langfuse span.
"""

from __future__ import annotations

import atexit
import contextvars
import os
import re
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")

_init_lock = threading.Lock()
_initialized = False
_atexit_registered = False
_init_failed = False
_parent_isolation_installed = False

_LANGFUSE_SPAN_STACK: contextvars.ContextVar[tuple[Any, ...]] = contextvars.ContextVar(
    "ledgerline_langfuse_span_stack",
    default=(),
)


def langfuse_enabled() -> bool:
    disabled = os.environ.get("LANGFUSE_TRACING_ENABLED", "").strip().lower()
    if disabled in {"0", "false", "no", "off"}:
        return False
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
        and os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    )


is_langfuse_configured = langfuse_enabled


def _mask_value(data: Any) -> Any:
    if isinstance(data, str):
        masked = _EMAIL_RE.sub("[REDACTED EMAIL]", data)
        return _CARD_RE.sub("[REDACTED CARD]", masked)
    if isinstance(data, dict):
        return {key: _mask_value(value) for key, value in data.items()}
    if isinstance(data, list):
        return [_mask_value(item) for item in data]
    return data


def _masking_function(*, data: Any, **_kwargs: Any) -> Any:
    return _mask_value(data)


@contextmanager
def _use_langfuse_parent() -> Iterator[None]:
    """Point the current OTel parent at the last Langfuse span (or a new root)."""
    from opentelemetry import context as otel_context
    from opentelemetry import trace

    stack = _LANGFUSE_SPAN_STACK.get()
    current = trace.get_current_span()
    if stack:
        parent: Any = stack[-1]
    elif (
        current is not None
        and current is not trace.INVALID_SPAN
        and current.is_recording()
    ):
        # Another OTel backend is current; do not use that id as a Langfuse parent.
        parent = trace.INVALID_SPAN
    else:
        yield
        return

    token = otel_context.attach(trace.set_span_in_context(parent))
    try:
        yield
    finally:
        otel_context.detach(token)


def _install_parent_isolation() -> None:
    """Patch Langfuse so every client instance nests under Langfuse parents.

    ``get_client()`` constructs a new ``Langfuse`` object each call, so wrapping
    one instance is not enough.
    """
    global _parent_isolation_installed

    if _parent_isolation_installed:
        return

    from langfuse import Langfuse
    from opentelemetry import context as otel_context
    from opentelemetry import trace

    original_start = Langfuse.start_observation
    original_start_as_current = Langfuse.start_as_current_observation

    def start_observation(self: Any, *args: Any, **kwargs: Any) -> Any:
        with _use_langfuse_parent():
            return original_start(self, *args, **kwargs)

    @contextmanager
    def start_as_current_observation(
        self: Any, *args: Any, **kwargs: Any
    ) -> Iterator[Any]:
        previous = trace.get_current_span()
        with _use_langfuse_parent():
            with original_start_as_current(self, *args, **kwargs) as observation:
                span = getattr(observation, "_otel_span", None)
                stack_token = None
                if span is not None:
                    stack_token = _LANGFUSE_SPAN_STACK.set(
                        _LANGFUSE_SPAN_STACK.get() + (span,)
                    )
                # Put the previous current span back so other backends keep a
                # valid parent. Langfuse children read the stack.
                restore = otel_context.attach(trace.set_span_in_context(previous))
                try:
                    yield observation
                finally:
                    otel_context.detach(restore)
                    if stack_token is not None:
                        _LANGFUSE_SPAN_STACK.reset(stack_token)

    Langfuse.start_observation = start_observation  # type: ignore[method-assign]
    Langfuse.start_as_current_observation = start_as_current_observation  # type: ignore[method-assign]
    _parent_isolation_installed = True


def configure_langfuse() -> None:
    """Initialize the Langfuse client and wrap OpenAI once per process."""
    global _initialized, _atexit_registered, _init_failed

    if _initialized or _init_failed or not langfuse_enabled():
        return

    with _init_lock:
        if _initialized or _init_failed:
            return
        try:
            from langfuse import Langfuse
            from opentelemetry.sdk.trace import TracerProvider

            _install_parent_isolation()

            base_url = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get(
                "LANGFUSE_HOST"
            )
            if base_url:
                os.environ.setdefault("LANGFUSE_HOST", base_url)
            os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")

            kwargs: dict[str, Any] = {
                "public_key": os.environ["LANGFUSE_PUBLIC_KEY"],
                "secret_key": os.environ["LANGFUSE_SECRET_KEY"],
                "mask": _masking_function,
                "environment": os.environ["LANGFUSE_TRACING_ENVIRONMENT"],
                # Keep Langfuse off any other global TracerProvider so
                # foreign OpenAI spans are not also ingested as observations.
                "tracer_provider": TracerProvider(),
            }
            if base_url:
                kwargs["base_url"] = base_url
            Langfuse(**kwargs)

            # Drop-in wrapper: logs each chat.completions call as a generation.
            from langfuse.openai import openai as _langfuse_openai  # noqa: F401
        except Exception as exc:
            _init_failed = True
            print(f"Langfuse tracing init failed: {exc}", flush=True)
            return
        _initialized = True
        if not _atexit_registered:
            atexit.register(flush_langfuse)
            _atexit_registered = True


init_langfuse = configure_langfuse


def get_langfuse():
    """Return the Langfuse client after ensuring env-aware init."""
    configure_langfuse()
    from langfuse import get_client

    return get_client()


def flush_langfuse() -> None:
    """Upload buffered Langfuse traces. Safe to call when tracing is off."""
    if not langfuse_enabled():
        return
    try:
        get_langfuse().flush()
    except Exception as exc:
        print(f"Langfuse flush failed: {exc}", flush=True)
