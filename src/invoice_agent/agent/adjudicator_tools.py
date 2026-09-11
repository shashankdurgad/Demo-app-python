"""Model-callable tools for Ledgerline Adjudicator.

Each method is backed by the in-repo fixture store and decorated so Overmind
records a tool_call child span. Outputs are deterministic.
"""

from __future__ import annotations

import overmind
from braintrust import traced
from galileo import log
from langfuse import observe
from langsmith import traceable

from invoice_agent.adjudicator_fixtures import (
    get_fx_rate_fixture,
    get_submitter_history_fixture,
    lookup_policy_fixture,
    post_decision_fixture,
)

OPENAI_TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_policy",
            "description": (
                "Look up the company expense policy clause that applies to a "
                "category and region on a given claim date. Returns clause id, "
                "cap, cap unit, receipt requirement, effective date, and whether "
                "the category is reimbursable."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Claim category, e.g. travel, lodging, meals, gifts.",
                    },
                    "region": {
                        "type": "string",
                        "description": "Region code: US, UK, EU, or APAC.",
                    },
                    "claim_date": {
                        "type": "string",
                        "description": "Date the expense was incurred, YYYY-MM-DD.",
                    },
                },
                "required": ["category", "region", "claim_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_fx_rate",
            "description": (
                "Return the FX rate to convert from_currency into to_currency "
                "on a date. Same-currency pairs return 1.0."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {
                        "type": "string",
                        "description": "ISO code of the claim currency.",
                    },
                    "to_currency": {
                        "type": "string",
                        "description": "ISO code of the reporting currency.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Rate date, YYYY-MM-DD.",
                    },
                },
                "required": ["from_currency", "to_currency", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_submitter_history",
            "description": (
                "Return prior claim count, prior policy violations, and recent "
                "claim fingerprints for a submitter. Use this before approving "
                "when history might require escalation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "submitter_id": {
                        "type": "string",
                        "description": "Employee / submitter identifier.",
                    },
                },
                "required": ["submitter_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "post_decision",
            "description": (
                "Record the adjudication on the claim. Call this once you have "
                "a final decision, before returning the JSON result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_id": {"type": "string"},
                    "decision": {
                        "type": "string",
                        "description": "approve, partial, reject, or escalate.",
                    },
                    "approved_amount": {
                        "type": ["number", "null"],
                        "description": "Amount approved in reporting currency, or null.",
                    },
                    "policy_clause": {
                        "type": ["string", "null"],
                        "description": "Single clause id, or null if none applies.",
                    },
                    "rationale": {"type": "string"},
                },
                "required": [
                    "claim_id",
                    "decision",
                    "approved_amount",
                    "policy_clause",
                    "rationale",
                ],
            },
        },
    },
]


class AdjudicatorTools:
    """One method per tool. Decorated so each call is a tool_call span."""

    @traced(name="lookup_policy")
    @observe(name="lookup_policy", as_type="tool")
    @log(span_type="tool", name="lookup_policy")
    @overmind.tool(name="lookup_policy")
    @traceable(name="lookup_policy", tags=["adjudicator", "tool"])
    def lookup_policy(self, category: str, region: str, claim_date: str) -> dict:
        return lookup_policy_fixture(category, region, claim_date)

    @traced(name="get_fx_rate")
    @observe(name="get_fx_rate", as_type="tool")
    @log(span_type="tool", name="get_fx_rate")
    @overmind.tool(name="get_fx_rate")
    @traceable(name="get_fx_rate", tags=["adjudicator", "tool"])
    def get_fx_rate(self, from_currency: str, to_currency: str, date: str) -> dict:
        return get_fx_rate_fixture(from_currency, to_currency, date)

    @traced(name="get_submitter_history")
    @observe(name="get_submitter_history", as_type="tool")
    @log(span_type="tool", name="get_submitter_history")
    @overmind.tool(name="get_submitter_history")
    @traceable(name="get_submitter_history", tags=["adjudicator", "tool"])
    def get_submitter_history(self, submitter_id: str) -> dict:
        return get_submitter_history_fixture(submitter_id)

    @traced(name="post_decision")
    @observe(name="post_decision", as_type="tool")
    @log(span_type="tool", name="post_decision")
    @overmind.tool(name="post_decision")
    @traceable(name="post_decision", tags=["adjudicator", "tool"])
    def post_decision(
        self,
        claim_id: str,
        decision: str,
        approved_amount: float | None,
        policy_clause: str | None,
        rationale: str,
    ) -> dict:
        return post_decision_fixture(
            claim_id, decision, approved_amount, policy_clause, rationale
        )

    def dispatch(self, name: str, arguments: dict) -> dict:
        if name == "lookup_policy":
            return self.lookup_policy(
                category=str(arguments.get("category", "")),
                region=str(arguments.get("region", "")),
                claim_date=str(arguments.get("claim_date", "")),
            )
        if name == "get_fx_rate":
            return self.get_fx_rate(
                from_currency=str(arguments.get("from_currency", "")),
                to_currency=str(arguments.get("to_currency", "")),
                date=str(arguments.get("date", "")),
            )
        if name == "get_submitter_history":
            return self.get_submitter_history(
                submitter_id=str(arguments.get("submitter_id", "")),
            )
        if name == "post_decision":
            amount = arguments.get("approved_amount")
            return self.post_decision(
                claim_id=str(arguments.get("claim_id", "")),
                decision=str(arguments.get("decision", "")),
                approved_amount=None if amount is None else float(amount),
                policy_clause=arguments.get("policy_clause"),
                rationale=str(arguments.get("rationale", "")),
            )
        return {"error": f"unknown tool {name}"}
