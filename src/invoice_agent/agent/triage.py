"""Ledgerline agent flow — an invoice-triage agent feeding a payment-planner agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from braintrust import traced
from galileo import log
from langfuse import observe
from langsmith import traceable

from invoice_agent.agent.braintrust_tracing import configure_braintrust
from invoice_agent.agent.galileo_tracing import configure_galileo, start_galileo_session
from invoice_agent.agent.langfuse_tracing import configure_langfuse
from invoice_agent.agent.llm import analyze_email_with_llm, require_llm_configured
from invoice_agent.agent.tracing import configure_tracing
from invoice_agent.agent.planner import plan_payments
from invoice_agent.types import (
    InvoiceRecord,
    LedgerlineResult,
    MoneyAmount,
    RawEmail,
)


def _to_gmail_url(email_id: str, source: Literal["gmail", "demo"]) -> str:
    if source == "demo":
        return "#"
    return f"https://mail.google.com/mail/u/0/#inbox/{email_id}"


def _received_at(date_str: str) -> str:
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    except Exception:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        except Exception:
            return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@traced(name="analyze_email")
@observe(name="analyze-email", as_type="span")
@log(span_type="agent", name="analyze_email")
@traceable(name="analyze_email", tags=["triage"])
def analyze_email(
    email: RawEmail,
    source: Literal["gmail", "demo"],
) -> InvoiceRecord | None:
    """Classify one email and extract invoice fields, or return None if not payable."""
    combined_text = "\n".join(
        filter(
            None,
            [email.subject, email.snippet, email.body_text, *email.attachment_texts],
        )
    )

    llm = analyze_email_with_llm(
        subject=email.subject,
        from_=email.from_,
        date=email.date,
        text=combined_text,
    )

    if not llm.is_invoice:
        return None

    currency = llm.currency or "USD"
    amount: MoneyAmount | None = None
    if llm.amount is not None:
        amount = MoneyAmount(
            value=llm.amount,
            currency=currency,
            raw=f"{currency} {llm.amount}",
        )

    return InvoiceRecord.model_validate(
        {
            "id": f"{source}-{email.id}",
            "emailId": email.id,
            "threadId": email.thread_id or None,
            "subject": email.subject,
            "from": email.from_,
            "vendor": llm.vendor or "Unknown vendor",
            "receivedAt": _received_at(email.date),
            "amount": amount,
            "dueDate": llm.due_date,
            "invoiceNumber": llm.invoice_number,
            "confidence": round(llm.confidence, 2),
            "summary": llm.summary or email.snippet or email.subject,
            "gmailUrl": _to_gmail_url(email.id, source),
            "source": source,
        }
    )


@traced(name="run_invoice_agent")
@observe(name="triage-invoices", as_type="agent")
@log(span_type="workflow", name="run_invoice_agent")
@traceable(name="run_invoice_agent", tags=["triage"])
def run_invoice_agent(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
) -> list[InvoiceRecord]:
    """Triage agent: extract invoice records from a batch of emails."""
    configure_tracing()
    configure_galileo()
    configure_langfuse()
    configure_braintrust()
    require_llm_configured()

    invoices: list[InvoiceRecord] = []
    for email in emails:
        record = analyze_email(email, source)
        if record is not None:
            invoices.append(record)
    invoices.sort(key=lambda inv: inv.due_date or "9999-12-31")
    return invoices


@traced(name="run_ledgerline")
@observe(name="scan-inbox", as_type="agent")
@log(span_type="workflow", name="run_ledgerline")
@traceable(name="run_ledgerline", tags=["ledgerline"])
def run_ledgerline(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
) -> LedgerlineResult:
    """Both agents in sequence: triage extracts invoices, the planner prioritizes them."""
    configure_tracing()
    configure_galileo()
    configure_langfuse()
    configure_braintrust()
    scan_id = f"scan-{uuid4()}"
    start_galileo_session(scan_id)
    invoices = run_invoice_agent(emails, source)
    return LedgerlineResult(invoices=invoices, plan=plan_payments(invoices))
