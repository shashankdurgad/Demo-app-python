"""Ledgerline — LLM invoice email triage agent (package: invoice-agent)."""

import braintrust

__version__ = "0.1.0"

# Runs before any submodule imports the OpenAI client, so calls are auto-traced.
braintrust.init_logger(project="Project 2")
braintrust.auto_instrument()
