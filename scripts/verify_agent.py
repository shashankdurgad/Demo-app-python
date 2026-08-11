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
    # Keep unit check offline — do not send traces.
    os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
    os.environ.pop("LANGFUSE_SECRET_KEY", None)

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

    call_index = 0
    demo_order = ["demo-1", "demo-2", "demo-3", "demo-4", "demo-5"]

    def fake_create(**_kwargs: Any) -> Any:
        nonlocal call_index
        email_id = demo_order[call_index] if call_index < len(demo_order) else "demo-3"
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
        from invoice_agent.agent.triage import run_invoice_agent
        from invoice_agent.demo_emails import DEMO_EMAILS

        assert is_llm_configured() is True
        require_llm_configured()

        # Mock only covers the first 5 emails; later calls fall back to demo-3 (non-invoice).
        invoices = run_invoice_agent(DEMO_EMAILS, "demo")

    assert len(invoices) == 3, f"expected 3 invoices, got {len(invoices)}"
    assert not any("Team lunch" in inv.subject for inv in invoices)
    assert not any(inv.vendor == "Figma" for inv in invoices)
    amazon = next(inv for inv in invoices if inv.vendor == "Amazon")
    assert amazon.invoice_number == "123456789"
    northwind = next(inv for inv in invoices if inv.vendor == "Northwind")
    assert northwind.amount is not None
    assert northwind.amount.value == 1240.5

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


if __name__ == "__main__":
    main()
