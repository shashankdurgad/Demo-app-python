"""Ledgerline agent flow — an invoice-triage agent feeding a payment-planner agent."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Literal

from invoice_agent import __version__
from invoice_agent.agent.llm import analyze_email_with_llm, require_llm_configured
from invoice_agent.agent.planner import plan_payments
from invoice_agent.observability import get_langfuse, is_langfuse_configured
from invoice_agent.types import (
    InvoiceRecord,
    LedgerlineResult,
    MoneyAmount,
    RawEmail,
)

# True while nested under a ledgerline agent observation (batch or single-email).
_inside_ledgerline: ContextVar[bool] = ContextVar("inside_ledgerline", default=False)


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


def _analyze_email_core(
    email: RawEmail,
    source: Literal["gmail", "demo"],
) -> tuple[InvoiceRecord | None, dict]:
    """Return (invoice_or_none, span_output) for tracing."""
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
        return None, {
            "is_invoice": False,
            "confidence": round(llm.confidence, 2),
            "summary": llm.summary,
        }

    currency = llm.currency or "USD"
    amount: MoneyAmount | None = None
    if llm.amount is not None:
        amount = MoneyAmount(
            value=llm.amount,
            currency=currency,
            raw=f"{currency} {llm.amount}",
        )

    record = InvoiceRecord.model_validate(
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
    return record, {
        "is_invoice": True,
        "vendor": record.vendor,
        "amount": record.amount.model_dump() if record.amount else None,
        "due_date": record.due_date,
        "invoice_number": record.invoice_number,
        "confidence": record.confidence,
    }


def _analyze_email_span(
    email: RawEmail,
    source: Literal["gmail", "demo"],
) -> InvoiceRecord | None:
    langfuse = get_langfuse()
    with langfuse.start_as_current_observation(
        as_type="span",
        name="analyze-email",
        input={
            "subject": email.subject,
            "from": email.from_,
            "date": email.date,
            "body": email.snippet or email.body_text,
        },
        metadata={"email_id": email.id, "source": source},
    ) as span:
        record, span_output = _analyze_email_core(email, source)
        span.update(output=span_output)
        return record


def analyze_email(
    email: RawEmail,
    source: Literal["gmail", "demo"],
) -> InvoiceRecord | None:
    if not is_langfuse_configured():
        record, _ = _analyze_email_core(email, source)
        return record

    # Already under a root agent (scan or eval) → nest a span only.
    if _inside_ledgerline.get():
        return _analyze_email_span(email, source)

    # Standalone script/eval call → this email is the whole unit of work.
    from langfuse import propagate_attributes

    langfuse = get_langfuse()
    token = _inside_ledgerline.set(True)
    try:
        with langfuse.start_as_current_observation(
            as_type="agent",
            name="triage-email",
            input={
                "subject": email.subject,
                "from": email.from_,
                "date": email.date,
                "body": email.snippet or email.body_text,
            },
            metadata={"source": source, "email_id": email.id},
        ) as agent:
            with propagate_attributes(**_trace_attributes(source, feature="triage-email")):
                record, output = _analyze_email_core(email, source)
            agent.update(output=output)
            return record
    finally:
        _inside_ledgerline.reset(token)


def _trace_attributes(
    source: Literal["gmail", "demo"],
    *,
    feature: str,
    user_id: str | None = None,
) -> dict:
    attributes: dict = {
        "tags": ["ledgerline", feature, f"mode:{source}"],
        "metadata": {"source": source, "feature": feature},
        "trace_name": feature,
        "version": __version__,
    }
    if user_id:
        attributes["user_id"] = user_id
    return attributes


def _triage_emails(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
) -> list[InvoiceRecord]:
    invoices: list[InvoiceRecord] = []
    for email in emails:
        record = analyze_email(email, source)
        if record is not None:
            invoices.append(record)
    invoices.sort(key=lambda inv: inv.due_date or "9999-12-31")
    return invoices


def _invoice_summaries(invoices: list[InvoiceRecord]) -> list[dict]:
    return [
        {
            "vendor": inv.vendor,
            "amount": inv.amount.model_dump() if inv.amount else None,
            "due_date": inv.due_date,
            "confidence": inv.confidence,
        }
        for inv in invoices
    ]


def _triage_agent(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
) -> list[InvoiceRecord]:
    """First agent: decide which emails are payable invoices and extract their fields."""
    langfuse = get_langfuse()
    with langfuse.start_as_current_observation(
        as_type="agent",
        name="triage-invoices",
        input={
            "emails": [
                {"subject": email.subject, "from": email.from_, "date": email.date}
                for email in emails
            ]
        },
        metadata={"email_count": len(emails)},
    ) as agent:
        invoices = _triage_emails(emails, source)
        agent.update(
            output={
                "invoice_count": len(invoices),
                "rejected_count": len(emails) - len(invoices),
                "invoices": _invoice_summaries(invoices),
            }
        )
        return invoices


def run_ledgerline(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
    *,
    user_id: str | None = None,
) -> LedgerlineResult:
    """Both agents in sequence: triage extracts invoices, the planner prioritizes them."""
    require_llm_configured()

    if not is_langfuse_configured():
        invoices = _triage_emails(emails, source)
        return LedgerlineResult(invoices=invoices, plan=plan_payments(invoices))

    from langfuse import propagate_attributes

    langfuse = get_langfuse()
    token = _inside_ledgerline.set(True)
    try:
        with langfuse.start_as_current_observation(
            as_type="agent",
            name="scan-inbox",
            input={"mode": source, "email_count": len(emails)},
            metadata={"source": source, "email_count": len(emails)},
        ) as root:
            with propagate_attributes(
                **_trace_attributes(source, feature="scan-inbox", user_id=user_id)
            ):
                invoices = _triage_agent(emails, source)
                plan = plan_payments(invoices)
            root.update(
                output={
                    "invoice_count": len(invoices),
                    "invoices": _invoice_summaries(invoices),
                    "plan_summary": plan.summary,
                    "pay_now": [
                        item.vendor for item in plan.items if item.priority == "pay_now"
                    ],
                    "totals": [total.model_dump() for total in plan.totals],
                    "risk_flags": plan.risk_flags,
                }
            )
            return LedgerlineResult(invoices=invoices, plan=plan)
    finally:
        _inside_ledgerline.reset(token)


def run_invoice_agent(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
    *,
    user_id: str | None = None,
) -> list[InvoiceRecord]:
    """Invoices only — kept for scripts and evals that ignore the payment plan."""
    return run_ledgerline(emails, source, user_id=user_id).invoices
