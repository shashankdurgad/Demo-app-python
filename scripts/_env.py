"""Env loading helpers for CLI scripts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env_local() -> None:
    env_path = Path.cwd() / ".env.local"
    try:
        raw = env_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Missing .env.local — add OPENAI_API_KEY before running."
        ) from exc

    for line in raw.splitlines():
        trimmed = line.strip()
        if not trimmed or trimmed.startswith("#"):
            continue
        eq = trimmed.find("=")
        if eq <= 0:
            continue
        key = trimmed[:eq].strip()
        value = trimmed[eq + 1 :].strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        if os.environ.get(key) is None:
            os.environ[key] = value

    from invoice_agent.agent.braintrust_tracing import configure_braintrust
    from invoice_agent.agent.galileo_tracing import configure_galileo
    from invoice_agent.agent.langfuse_tracing import configure_langfuse
    from invoice_agent.agent.overmind_tracing import configure_overmind
    from invoice_agent.agent.tracing import configure_tracing

    configure_tracing()
    configure_overmind()
    configure_galileo()
    configure_langfuse()
    configure_braintrust()


def require_llm_env() -> None:
    if not os.environ.get("OPENAI_API_KEY") and not os.environ.get("OLLAMA_BASE_URL"):
        print(
            "Hard failure: set OPENAI_API_KEY or OLLAMA_BASE_URL in .env.local",
            file=sys.stderr,
        )
        sys.exit(1)
