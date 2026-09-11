"""LangSmith tracing setup for the Ledgerline agents."""

from __future__ import annotations

import atexit
import os

DEFAULT_PROJECT = "ledgerline"

_atexit_registered = False


def configure_tracing() -> None:
    """Enable LangSmith when LANGSMITH_API_KEY is set.

    Honors an explicit LANGSMITH_TRACING=false. Defaults the project name to
    ``ledgerline`` so traces are not dumped into LangSmith's "default" project.
    """
    global _atexit_registered

    if not os.environ.get("LANGSMITH_API_KEY"):
        return
    if os.environ.get("LANGSMITH_TRACING", "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        os.environ["LANGSMITH_TRACING"] = "false"
        return
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", DEFAULT_PROJECT)
    # Short scripts must flush before exit or background traces are dropped.
    os.environ.setdefault("LANGCHAIN_CALLBACKS_BACKGROUND", "false")
    # LANGSMITH_ENDPOINT is read by the SDK. US default is
    # https://api.smith.langchain.com; EU keys must use
    # https://eu.api.smith.langchain.com or ingest returns 403.
    if not _atexit_registered:
        atexit.register(flush_langsmith)
        _atexit_registered = True


def tracing_enabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def flush_langsmith() -> None:
    """Wait for background LangSmith runs to upload. No-op when tracing is off."""
    if not tracing_enabled():
        return
    try:
        from langsmith.run_trees import get_cached_client

        get_cached_client().flush()
    except Exception:
        try:
            from langsmith import Client

            Client().flush()
        except Exception as exc:
            print(f"LangSmith flush failed: {exc}", flush=True)
