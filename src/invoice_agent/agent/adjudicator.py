"""Ledgerline Adjudicator — policy-backed expense claim decisions."""

from __future__ import annotations

import json

from invoice_agent.agent.adjudicator_tools import OPENAI_TOOLS, AdjudicatorTools
from invoice_agent.agent.llm import (
    _extract_json_object,
    create_chat_completion,
    require_llm_configured,
)
from invoice_agent.adjudicator_fixtures import unhedge_identifier
from invoice_agent.types import Adjudication, ExpenseClaim

MAX_TOOL_ROUNDS = 4

SYSTEM_PROMPT = """You are Ledgerline Adjudicator, a company expense-policy agent.
You decide whether a submitted expense claim is reimbursable. You do not guess
policy, FX rates, or submitter history — you look them up with tools.

Tools:
- lookup_policy(category, region, claim_date) — applicable clause (id, cap, cap_unit,
  receipt_required, effective_date, reimbursable).
- get_fx_rate(from_currency, to_currency, date) — conversion rate; 1.0 if same currency.
- get_submitter_history(submitter_id) — prior claims, violations, recent fingerprints.
- post_decision(claim_id, decision, approved_amount, policy_clause, rationale) — write path.

Decision procedure (in order):
1. lookup_policy. If none applies, decision=escalate, policy_clause=null, amounts null.
2. get_submitter_history. If prior_violations >= 3, or the claim fingerprint
   (merchant|claim_date|amount) matches recent_fingerprints, decision=escalate.
   Still cite the clause you looked up. approved_amount=null, reimbursable=false.
3. If the clause is not reimbursable (e.g. gifts), decision=reject, approved_amount=0.
4. If receipt_required and the claim has no receipt text, decision=reject, approved_amount=0.
5. If the claim is older than stale_after_days (submitted_at minus claim_date), reject.
6. If the receipt has a clear Total that differs from claimed_amount, reject (mismatch).
7. get_fx_rate from claim_currency to reporting_currency on claim_date.
   Converted amount = claimed_amount * rate (round to 2 decimals).
8. Cap: per_claim uses cap_amount; per_day / per_night uses cap_amount * units.
   If units are missing for a per_day/per_night cap, escalate with nulls.
   If converted <= cap: approve (approved_amount = converted).
   If converted > cap: partial (approved_amount = cap).
9. Call post_decision once, then return the JSON object.
Batch independent lookups in a single round. After post_decision, stop calling tools.

reimbursable is true only for approve and partial.

Exactly-checked fields must never be hedged. If you are not sure of a single
clause id, set policy_clause to null — never "TRV-04? or TRV-06".

Confidence (required, 0.0–1.0, not a percentage):
- 0.90–1.00: policy, amounts, and dates are explicit and you applied them
- 0.70–0.89: a cap/FX/pro-rate step was required, or history triggered escalate
- 0.40–0.69: mixed or incomplete evidence (blurry receipt, unknown category)
- 0.00–0.39: guessing
Do not default every answer to 0.95. Spread scores with evidence strength.

Return JSON only (no markdown) with exactly these keys:
reimbursable, decision, policy_clause, approved_amount, reporting_currency,
fx_rate_used, effective_date, receipt_required, rationale, confidence.
"""


def _claim_user_prompt(claim: ExpenseClaim) -> str:
    payload = claim.model_dump()
    return (
        "Adjudicate this expense claim under company policy. Use tools.\n\n"
        + json.dumps(payload, indent=2)
    )


def _assistant_message(content: str | None, tool_calls) -> dict:
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in tool_calls
        ]
    return message


def _parse_adjudication(raw: dict) -> Adjudication:
    confidence = raw.get("confidence")
    if isinstance(confidence, (int, float)) and confidence > 1:
        raw["confidence"] = min(confidence / 100, 1)
    raw["policy_clause"] = unhedge_identifier(raw.get("policy_clause"))
    raw["reporting_currency"] = unhedge_identifier(raw.get("reporting_currency"))
    # receipt_required is a boolean on the contract, not nullable.
    if raw.get("receipt_required") is None:
        raw["receipt_required"] = False
    if raw.get("reimbursable") is None:
        raw["reimbursable"] = False
    return Adjudication.model_validate(raw)


def _run_tool_loop(claim: ExpenseClaim) -> Adjudication:
    tools = AdjudicatorTools()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _claim_user_prompt(claim)},
    ]

    for _round in range(MAX_TOOL_ROUNDS):
        response = create_chat_completion(
            messages=messages,
            tools=OPENAI_TOOLS,
        )
        if response.tool_calls:
            messages.append(_assistant_message(response.content, response.tool_calls))
            for call in response.tool_calls:
                try:
                    arguments = json.loads(call.arguments or "{}")
                    if not isinstance(arguments, dict):
                        arguments = {}
                except json.JSONDecodeError:
                    arguments = {}
                result = tools.dispatch(call.name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(result),
                    }
                )
            continue

        if not response.content:
            raise RuntimeError(
                f"LLM returned an empty final response for {claim.claim_id}"
            )
        parsed = _extract_json_object(response.content)
        if not isinstance(parsed, dict):
            raise RuntimeError("LLM returned invalid JSON: not an object")
        return _parse_adjudication(parsed)

    # Tool budget exhausted: one last completion with tools disabled.
    response = create_chat_completion(messages=messages, tools=None)
    if not response.content:
        raise RuntimeError(
            f"Exceeded {MAX_TOOL_ROUNDS} tool rounds for claim {claim.claim_id}"
        )
    parsed = _extract_json_object(response.content)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM returned invalid JSON: not an object")
    return _parse_adjudication(parsed)


def adjudicate_claim(claim: ExpenseClaim) -> Adjudication:
    """Public entry: one claim through the tool-calling adjudicator."""
    require_llm_configured()
    return _run_tool_loop(claim)
