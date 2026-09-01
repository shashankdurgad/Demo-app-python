"""Overmind telemetry setup for the Ledgerline agents.

This sits alongside the LangSmith wiring in ``tracing.py``; both backends can be
enabled at the same time.
"""

from __future__ import annotations

import os
import threading

import overmind

SERVICE_NAME = "ledgerline"

# Agent identities registered in the Overmind project. These UUIDs come from the
# platform and must match it exactly, or traces attribute to the wrong agent.
TRIAGE_AGENT_ID = "3ce720eb-33ef-48b9-96bb-9433970e2e7d"
TRIAGE_AGENT_NAME = "Ledgerline"

PLANNER_AGENT_ID = "da9245b1-140b-4e6e-81db-a8c3a6b76c23"
PLANNER_AGENT_NAME = "Ledgerline Planner"

# Copied verbatim from Overmind list_agents / get_agent after registration.
ADJUDICATOR_AGENT_ID = "0d9caf5e-6008-43d0-be38-9c801202f94a"
ADJUDICATOR_AGENT_NAME = "Ledgerline Adjudicator"

_init_lock = threading.Lock()
_initialized = False


def overmind_enabled() -> bool:
    return bool(os.environ.get("OVERMIND_API_KEY"))


def configure_overmind() -> None:
    """Install the Overmind tracer provider once per process."""
    global _initialized

    if _initialized or not overmind_enabled():
        return

    with _init_lock:
        if _initialized:
            return
        # No agent identity is pinned here on purpose: the Ledgerline agents
        # share this process, and resource attributes are process-global, so a
        # global identity would misattribute sibling agents. Each agent stamps
        # itself at its own entry point instead.
        # The SDK snapshots OVERMIND_API_URL into a module-level default when it
        # is first imported, which happens before .env is loaded — so pass the
        # URL explicitly or spans go to the cloud endpoint instead of this one.
        overmind.init(
            service_name=SERVICE_NAME,
            providers=["openai"],
            overmind_base_url=os.environ.get("OVERMIND_API_URL"),
        )
        _initialized = True


def stamp_adjudicator_identity() -> None:
    """Stamp Ledgerline Adjudicator on the current context before its span opens."""
    if ADJUDICATOR_AGENT_ID:
        overmind.set_agent_id(ADJUDICATOR_AGENT_ID)
    overmind.set_agent_name(ADJUDICATOR_AGENT_NAME)
