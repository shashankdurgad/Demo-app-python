"""Invoice triage pipeline — one LLM call per email."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Literal

from invoice_agent.agent.llm import analyze_email_with_llm, require_llm_configured
from invoice_agent.observability import get_langfuse, is_langfuse_configured
from invoice_agent.types import InvoiceRecord, MoneyAmount, RawEmail

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
            "email_id": email.id,
            "subject": email.subject,
            "from": email.from_,
            "date": email.date,
            "source": source,
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

    # Already under run_invoice_agent → nest span only.
    if _inside_ledgerline.get():
        return _analyze_email_span(email, source)

    # Standalone script/eval call → ledgerline must be the root.
    from langfuse import propagate_attributes

    langfuse = get_langfuse()
    token = _inside_ledgerline.set(True)
    try:
        with langfuse.start_as_current_observation(
            as_type="agent",
            name="ledgerline",
            input={
                "mode": source,
                "email_count": 1,
                "email_id": email.id,
                "subject": email.subject,
            },
            metadata={
                "source": source,
                "feature": "analyze-email",
                "agent": "ledgerline",
                "email_id": email.id,
            },
        ) as agent:
            with propagate_attributes(
                tags=["ledgerline", f"mode:{source}"],
                metadata={
                    "source": source,
                    "agent": "ledgerline",
                    "email_id": email.id,
                },
                trace_name="ledgerline",
            ):
                record = _analyze_email_span(email, source)
            if record is None:
                agent.update(output={"is_invoice": False, "invoice_count": 0})
            else:
                agent.update(
                    output={
                        "is_invoice": True,
                        "invoice_count": 1,
                        "vendor": record.vendor,
                        "amount": record.amount.model_dump() if record.amount else None,
                        "due_date": record.due_date,
                        "confidence": record.confidence,
                    }
                )
            return record
    finally:
        _inside_ledgerline.reset(token)


def run_invoice_agent(
    emails: list[RawEmail],
    source: Literal["gmail", "demo"],
    *,
    user_id: str | None = None,
) -> list[InvoiceRecord]:
    require_llm_configured()

    def _run_scan() -> list[InvoiceRecord]:
        invoices: list[InvoiceRecord] = []
        for email in emails:
            record = analyze_email(email, source)
            if record is not None:
                invoices.append(record)
        invoices.sort(key=lambda inv: inv.due_date or "9999-12-31")
        return invoices

    if not is_langfuse_configured():
        return _run_scan()

    from langfuse import propagate_attributes

    langfuse = get_langfuse()
    tags = ["ledgerline", "invoice-scan", f"mode:{source}"]
    attr_kwargs: dict = {
        "tags": tags,
        "metadata": {
            "source": source,
            "email_count": len(emails),
            "feature": "invoice-scan",
            "agent": "ledgerline",
        },
        "trace_name": "ledgerline",
    }
    if user_id:
        attr_kwargs["user_id"] = user_id

    token = _inside_ledgerline.set(True)
    try:
        with langfuse.start_as_current_observation(
            as_type="agent",
            name="ledgerline",
            input={"mode": source, "email_count": len(emails)},
            metadata={
                "source": source,
                "feature": "invoice-scan",
                "agent": "ledgerline",
            },
        ) as root:
            with propagate_attributes(**attr_kwargs):
                invoices = _run_scan()
            root.update(
                output={
                    "invoice_count": len(invoices),
                    "invoices": [
                        {
                            "vendor": inv.vendor,
                            "amount": inv.amount.model_dump() if inv.amount else None,
                            "due_date": inv.due_date,
                            "confidence": inv.confidence,
                        }
                        for inv in invoices
                    ],
                }
            )
            return invoices
    finally:
        _inside_ledgerline.reset(token)
