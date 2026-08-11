"""Langfuse tracing helpers — init after env vars are loaded."""

from __future__ import annotations

import os
import re
from typing import Any

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.\w+\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_initialized = False


def is_langfuse_configured() -> bool:
    return bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )


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


def init_langfuse() -> None:
    """Initialize the global Langfuse client once (safe if keys are missing)."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    if not is_langfuse_configured():
        return

    import atexit

    from langfuse import Langfuse

    # Prefer LANGFUSE_BASE_URL; fall back to LANGFUSE_HOST for older setups.
    base_url = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    # Keep local/dev traces out of production dashboards when unset.
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", "development")
    # OpenTelemetry service name shows up in Langfuse resource attributes.
    os.environ.setdefault("OTEL_SERVICE_NAME", "ledgerline")

    kwargs: dict[str, Any] = {
        "public_key": os.environ["LANGFUSE_PUBLIC_KEY"],
        "secret_key": os.environ["LANGFUSE_SECRET_KEY"],
        "mask": _masking_function,
        "environment": os.environ["LANGFUSE_TRACING_ENVIRONMENT"],
    }
    if base_url:
        kwargs["base_url"] = base_url

    Langfuse(**kwargs)
    atexit.register(flush_langfuse)


def get_langfuse():
    """Return the Langfuse client after ensuring env-aware init."""
    init_langfuse()
    from langfuse import get_client

    return get_client()


def flush_langfuse() -> None:
    """Flush queued events — required for short-lived scripts."""
    if not is_langfuse_configured():
        return
    get_langfuse().flush()
