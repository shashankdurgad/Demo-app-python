"""LangSmith tracing setup for the Ledgerline agents."""

from __future__ import annotations

import os

DEFAULT_PROJECT = "ledgerline"


def configure_tracing() -> None:
    """Enable LangSmith when LANGSMITH_API_KEY is set.

    Honors an explicit LANGSMITH_TRACING=false. Defaults the project name to
    ``ledgerline`` so traces are not dumped into LangSmith's "default" project.
    """
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
    # LANGSMITH_ENDPOINT is read by the SDK. US default is
    # https://api.smith.langchain.com; EU keys must use
    # https://eu.api.smith.langchain.com or ingest returns 403.


def tracing_enabled() -> bool:
    return os.environ.get("LANGSMITH_TRACING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
