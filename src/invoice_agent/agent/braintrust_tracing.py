"""Braintrust tracing setup for the Ledgerline agents.

Matches ``add_braintrust_intrumentation``: ``init_logger`` then
``auto_instrument`` (not per-client ``wrap_openai``). Official Python
instrumentation: https://www.braintrust.dev/docs/sdks/python/install-and-instrument

Enabled when ``BRAINTRUST_API_KEY`` is set. EU tenants should also set
``BRAINTRUST_API_URL`` (this repo uses ``https://api-eu.braintrust.dev``).

``BRAINTRUST_PROJECT_ID`` pins the destination project. Otherwise traces go to
``BRAINTRUST_PROJECT`` (default ``My Project``).
"""

from __future__ import annotations

import atexit
import os
import threading
from typing import Any

DEFAULT_PROJECT = "My Project"

_init_lock = threading.Lock()
_initialized = False
_atexit_registered = False
_init_failed = False
_logger: Any = None


def braintrust_enabled() -> bool:
    disabled = os.environ.get("BRAINTRUST_TRACING", "").strip().lower()
    if disabled in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("BRAINTRUST_API_KEY", "").strip())


def configure_braintrust() -> None:
    """Initialize the logger and patch AI libraries once per process.

    Must run before OpenAI clients are constructed so ``auto_instrument``
    wraps ``chat.completions.create``.
    """
    global _initialized, _atexit_registered, _init_failed, _logger

    if _initialized or _init_failed or not braintrust_enabled():
        return

    with _init_lock:
        if _initialized or _init_failed:
            return
        try:
            import braintrust
            from braintrust import init_logger

            kwargs: dict[str, Any] = {
                "api_key": os.environ["BRAINTRUST_API_KEY"],
            }
            project_id = os.environ.get("BRAINTRUST_PROJECT_ID", "").strip()
            project = os.environ.get("BRAINTRUST_PROJECT", "").strip()
            if project_id:
                kwargs["project_id"] = project_id
            else:
                kwargs["project"] = project or DEFAULT_PROJECT
            # Python init_logger takes app_url (control plane), not api_url.
            # The EU data plane is selected via BRAINTRUST_API_URL in the
            # environment (https://api-eu.braintrust.dev).
            app_url = os.environ.get("BRAINTRUST_APP_URL", "").strip()
            if app_url:
                kwargs["app_url"] = app_url
            _logger = init_logger(**kwargs)
            braintrust.auto_instrument()
        except Exception as exc:
            _init_failed = True
            print(f"Braintrust tracing init failed: {exc}", flush=True)
            return
        _initialized = True
        if not _atexit_registered:
            atexit.register(flush_braintrust)
            _atexit_registered = True


def flush_braintrust() -> None:
    """Upload buffered Braintrust traces. Safe to call when tracing is off."""
    if not _initialized or _logger is None:
        return
    try:
        _logger.flush()
    except Exception as exc:
        print(f"Braintrust flush failed: {exc}", flush=True)
