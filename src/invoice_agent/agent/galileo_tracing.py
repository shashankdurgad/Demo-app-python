"""Galileo tracing setup for the Ledgerline agents.

Sits alongside LangSmith (`tracing.py`). Both backends can be enabled at the same time.

Requires ``GALILEO_API_KEY``. Project and log stream default to ``demo app``
(matching the Galileo getting-started names) and can be overridden with
``GALILEO_PROJECT`` / ``GALILEO_LOG_STREAM``.
"""

from __future__ import annotations

import atexit
import os
import threading

from galileo import galileo_context

DEFAULT_PROJECT = "demo app"
DEFAULT_LOG_STREAM = "demo app"

_init_lock = threading.Lock()
_initialized = False
_atexit_registered = False
_init_failed = False


def galileo_enabled() -> bool:
    disabled = os.environ.get("GALILEO_LOGGING_DISABLED", "").strip().lower()
    if disabled in {"1", "true", "yes", "on", "t"}:
        return False
    return bool(os.environ.get("GALILEO_API_KEY", "").strip())


def configure_galileo() -> None:
    """Initialize the Galileo logger once per process."""
    global _initialized, _atexit_registered, _init_failed

    if _initialized or _init_failed or not galileo_enabled():
        return

    with _init_lock:
        if _initialized or _init_failed:
            return
        project = os.environ.get("GALILEO_PROJECT") or DEFAULT_PROJECT
        log_stream = os.environ.get("GALILEO_LOG_STREAM") or DEFAULT_LOG_STREAM
        try:
            galileo_context.init(project=project, log_stream=log_stream)
            # Importing this module wraps openai.resources.chat.completions.Completions.create
            # so every OpenAI client in the process logs LLM spans.
            from galileo.openai import openai as _galileo_openai  # noqa: F401
        except Exception as exc:
            _init_failed = True
            print(f"Galileo tracing init failed: {exc}", flush=True)
            return
        _initialized = True
        if not _atexit_registered:
            atexit.register(flush_galileo)
            _atexit_registered = True


def flush_galileo() -> None:
    """Upload buffered Galileo traces. Safe to call when tracing is off."""
    if not _initialized:
        return
    try:
        galileo_context.flush()
    except Exception as exc:
        print(f"Galileo flush failed: {exc}", flush=True)


def start_galileo_session(
    name: str,
    metadata: dict[str, str] | None = None,
) -> None:
    """Group the next traces into one Galileo session (no-op when disabled)."""
    if not galileo_enabled():
        return
    configure_galileo()
    if not _initialized:
        return
    try:
        galileo_context.start_session(name=name, metadata=metadata)
    except Exception as exc:
        print(f"Galileo start_session failed: {exc}", flush=True)


def galileo_log_urls() -> tuple[str, str] | None:
    """Return (project_url, log_stream_url) after a successful init."""
    if not _initialized:
        return None
    try:
        from galileo.config import GalileoPythonConfig

        config = GalileoPythonConfig.get()
        logger = galileo_context.get_logger_instance()
        base = str(config.console_url).rstrip("/")
        project_url = f"{base}/project/{logger.project_id}"
        log_stream_url = f"{project_url}/log-streams/{logger.log_stream_id}"
        return project_url, log_stream_url
    except Exception:
        return None
