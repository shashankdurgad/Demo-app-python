"""Ledgerline — LLM invoice email triage agent (package: invoice-agent)."""

__version__ = "0.1.0"

# Runs before any submodule imports the OpenAI client, so calls are auto-traced.
# No-op when BRAINTRUST_API_KEY is unset (e.g. verify_agent).
from invoice_agent.agent.braintrust_tracing import configure_braintrust

configure_braintrust()
