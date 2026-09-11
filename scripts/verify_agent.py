"""Mocked LLM unit check — no network."""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch


def main() -> None:
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_MODEL"] = "gpt-4o-mini"

    responses = {
        "demo-1": {
            "isInvoice": True,
            "vendor": "Northwind",
            "amount": 1240.5,
            "currency": "GBP",
            "dueDate": "2026-07-31",
            "invoiceNumber": "INV-1042",
            "summary": "Northwind invoice INV-1042",
            "confidence": 0.92,
        },
        "demo-2": {
            "isInvoice": True,
            "vendor": "Amazon",
            "amount": 312.88,
            "currency": "USD",
            "dueDate": "2026-07-20",
            "invoiceNumber": "123456789",
            "summary": "AWS invoice",
            "confidence": 0.9,
        },
        "demo-3": {
            "isInvoice": False,
            "vendor": None,
            "amount": None,
            "currency": None,
            "dueDate": None,
            "invoiceNumber": None,
            "summary": "Personal lunch email",
            "confidence": 0.95,
        },
        "demo-4": {
            "isInvoice": False,
            "vendor": "Figma",
            "amount": 45,
            "currency": "USD",
            "dueDate": None,
            "invoiceNumber": None,
            "summary": "Paid receipt",
            "confidence": 0.93,
        },
        "demo-5": {
            "isInvoice": True,
            "vendor": "Cloudhost",
            "amount": 890,
            "currency": "EUR",
            "dueDate": "2026-07-16",
            "invoiceNumber": "7781",
            "summary": "Cloudhost invoice 7781",
            "confidence": 0.91,
        },
    }

    plan_response = {
        "items": [
            {
                "invoiceId": "demo-demo-5",
                "priority": "pay_now",
                "payBy": "2026-07-16",
                "reason": "Cloudhost is due first.",
            },
            {
                "invoiceId": "demo-demo-2",
                "priority": "schedule",
                "payBy": "2026-07-20",
                "reason": "AWS has room before the due date.",
            },
        ],
        "summary": "Pay Cloudhost first, then AWS and Northwind.",
        "riskFlags": ["Northwind invoice is the largest exposure."],
    }

    call_index = 0
    demo_order = ["demo-1", "demo-2", "demo-3", "demo-4", "demo-5"]

    def fake_create(**kwargs: Any) -> Any:
        nonlocal call_index
        messages = kwargs.get("messages") or [{}]
        if "Ledgerline Planner" in (messages[0].get("content") or ""):
            payload: Any = plan_response
        else:
            email_id = (
                demo_order[call_index] if call_index < len(demo_order) else "demo-3"
            )
            call_index += 1
            payload = responses[email_id]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(payload))
                )
            ]
        )

    # Ensure package imports resolve
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
    if root not in sys.path:
        sys.path.insert(0, root)

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = fake_create

    with patch("invoice_agent.agent.llm.OpenAI", return_value=mock_client):
        from invoice_agent.agent.llm import is_llm_configured, require_llm_configured
        from invoice_agent.agent.triage import run_ledgerline
        from invoice_agent.demo_emails import DEMO_EMAILS

        assert is_llm_configured() is True
        require_llm_configured()

        # Mock only covers the first 5 emails; later calls fall back to demo-3 (non-invoice).
        run = run_ledgerline(DEMO_EMAILS, "demo")

    invoices = run.invoices
    plan = run.plan

    assert len(invoices) == 3, f"expected 3 invoices, got {len(invoices)}"
    assert not any("Team lunch" in inv.subject for inv in invoices)
    assert not any(inv.vendor == "Figma" for inv in invoices)
    amazon = next(inv for inv in invoices if inv.vendor == "Amazon")
    assert amazon.invoice_number == "123456789"
    northwind = next(inv for inv in invoices if inv.vendor == "Northwind")
    assert northwind.amount is not None
    assert northwind.amount.value == 1240.5

    # Planner agent: every invoice gets a verdict, even the ones the LLM skipped.
    assert plan.source == "llm", f"expected an LLM plan, got {plan.source}"
    assert len(plan.items) == len(invoices)
    assert {item.invoice_id for item in plan.items} == {inv.id for inv in invoices}
    assert plan.items[0].priority == "pay_now"
    assert plan.risk_flags
    totals = {total.currency: total.value for total in plan.totals}
    assert totals == {"EUR": 890.0, "GBP": 1240.5, "USD": 312.88}, totals

    print(
        "LLM agent verification passed:",
        [
            {
                "vendor": inv.vendor,
                "amount": inv.amount.model_dump() if inv.amount else None,
                "dueDate": inv.due_date,
            }
            for inv in invoices
        ],
    )
    print(
        "Payment planner verification passed:",
        {
            "summary": plan.summary,
            "items": [
                {
                    "vendor": item.vendor,
                    "priority": item.priority,
                    "payBy": item.pay_by,
                }
                for item in plan.items
            ],
            "totals": totals,
        },
    )

    # Adjudicator: mocked tool loop (lookup → post_decision → JSON).
    from invoice_agent.agent.adjudicator import adjudicate_claim
    from invoice_agent.types import ExpenseClaim

    claim = ExpenseClaim(
        claim_id="CLM-TEST",
        submitter_id="emp-clean-00",
        submitter_name="Test User",
        category="travel",
        region="US",
        merchant="Cedarline Air",
        claim_date="2026-07-12",
        submitted_at="2026-08-26",
        claimed_amount=280.0,
        claim_currency="USD",
        reporting_currency="USD",
        receipt_text=(
            "Cedarline Air\nDate: 2026-07-12\nItem: flight\nTotal: USD 280.00\n"
        ),
        notes="Return flight",
    )
    adjudication = {
        "reimbursable": True,
        "decision": "approve",
        "policy_clause": "TRV-04",
        "approved_amount": 280.0,
        "reporting_currency": "USD",
        "fx_rate_used": 1.0,
        "effective_date": "2025-01-01",
        "receipt_required": True,
        "rationale": "Within TRV-04 cap after policy and FX lookup.",
        "confidence": 0.93,
    }
    adj_round = 0

    def _tool_call(call_id: str, name: str, arguments: dict) -> Any:
        return SimpleNamespace(
            id=call_id,
            function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
        )

    def fake_adjudicate_create(**kwargs: Any) -> Any:
        nonlocal adj_round
        tools = kwargs.get("tools")
        if tools and adj_round == 0:
            adj_round += 1
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _tool_call(
                                    "call-policy",
                                    "lookup_policy",
                                    {
                                        "category": "travel",
                                        "region": "US",
                                        "claim_date": "2026-07-12",
                                    },
                                ),
                                _tool_call(
                                    "call-hist",
                                    "get_submitter_history",
                                    {"submitter_id": "emp-clean-00"},
                                ),
                                _tool_call(
                                    "call-fx",
                                    "get_fx_rate",
                                    {
                                        "from_currency": "USD",
                                        "to_currency": "USD",
                                        "date": "2026-07-12",
                                    },
                                ),
                            ],
                        )
                    )
                ]
            )
        if tools and adj_round == 1:
            adj_round += 1
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                _tool_call(
                                    "call-post",
                                    "post_decision",
                                    {
                                        "claim_id": "CLM-TEST",
                                        "decision": "approve",
                                        "approved_amount": 280.0,
                                        "policy_clause": "TRV-04",
                                        "rationale": "Within cap",
                                    },
                                ),
                            ],
                        )
                    )
                ]
            )
        adj_round += 1
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(adjudication),
                        tool_calls=None,
                    )
                )
            ]
        )

    adj_client = MagicMock()
    adj_client.chat.completions.create.side_effect = fake_adjudicate_create
    with patch("invoice_agent.agent.llm.OpenAI", return_value=adj_client):
        result = adjudicate_claim(claim)

    assert adj_round == 3, f"expected 3 LLM rounds, got {adj_round}"
    assert result.decision == "approve"
    assert result.reimbursable is True
    assert result.policy_clause == "TRV-04"
    assert result.approved_amount == 280.0
    assert adj_client.chat.completions.create.call_count == 3
    first_kwargs = adj_client.chat.completions.create.call_args_list[0].kwargs
    assert first_kwargs.get("tools"), "first round must advertise tools"
    print(
        "Adjudicator verification passed:",
        {
            "decision": result.decision,
            "policy_clause": result.policy_clause,
            "approved_amount": result.approved_amount,
            "tool_rounds": adj_round - 1,
        },
    )


if __name__ == "__main__":
    main()
