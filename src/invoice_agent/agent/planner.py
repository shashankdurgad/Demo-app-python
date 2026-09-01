"""Payment planner agent — turns triaged invoices into a prioritized payment plan."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import overmind
from langsmith import traceable

from invoice_agent.agent.llm import chat_json
from invoice_agent.agent.overmind_tracing import (
    PLANNER_AGENT_ID,
    PLANNER_AGENT_NAME,
    configure_overmind,
)
from invoice_agent.types import (
    CurrencyTotal,
    InvoiceRecord,
    LlmPaymentPlan,
    PaymentPlan,
    PaymentPlanItem,
    Priority,
)

# Keep the planner prompt bounded on large scans (e.g. the 250-email corpus).
MAX_PLANNED_INVOICES = 40

SYSTEM_PROMPT = """You are Ledgerline Planner, an accounts-payable prioritization agent.
You receive invoices that another agent already extracted from a mailbox, and you decide
in which order a small finance team should pay them.

Rules:
- Assign every invoice exactly one priority:
  - "pay_now": overdue, due within 7 days, or a late/suspension risk if delayed.
  - "schedule": due later; safe to queue for the next payment run.
  - "hold": do not pay yet — low extraction confidence, missing amount or due date,
    a possible duplicate, or anything that needs a human to check first.
- payBy must be YYYY-MM-DD and must never be later than the invoice due date, except for
  an already-overdue invoice, where payBy is today. Use null when the due date is unknown.
- Trust the daysUntilDue field for timing (negative means overdue); never recompute dates
  yourself.
- reason must be one short sentence a finance person can act on. Reference the concrete
  signal you used (days overdue, amount, missing field, duplicate vendor).
- riskFlags are portfolio-level warnings across the whole set: duplicate vendor/amount
  pairs, unusually large amounts, invoices missing an amount or due date, low confidence.
- Never invent invoices. Only use the invoiceId values given to you.

Return JSON only. No markdown."""


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _days_until(due_date: str | None, today: date) -> int | None:
    if not due_date:
        return None
    try:
        return (date.fromisoformat(due_date) - today).days
    except ValueError:
        return None


def _fallback_priority(invoice: InvoiceRecord, today: date) -> tuple[Priority, str]:
    """Deterministic due-date rules used when the LLM plan is unusable."""
    if invoice.amount is None or invoice.confidence < 0.5:
        return "hold", "Needs review — amount missing or low extraction confidence."

    days = _days_until(invoice.due_date, today)
    if days is None:
        return "hold", "Needs review — no due date extracted."
    if days < 0:
        return "pay_now", f"Overdue by {abs(days)} day(s)."
    if days <= 7:
        return "pay_now", f"Due in {days} day(s)."
    return "schedule", f"Due in {days} day(s); queue for the next payment run."


@overmind.function(name="fallback_plan")
def _fallback_plan(invoices: list[InvoiceRecord], reason: str) -> PaymentPlan:
    today = _today()
    items = []
    for invoice in invoices:
        priority, item_reason = _fallback_priority(invoice, today)
        items.append(
            PaymentPlanItem(
                invoice_id=invoice.id,
                vendor=invoice.vendor,
                priority=priority,
                pay_by=invoice.due_date,
                reason=item_reason,
            )
        )
    return PaymentPlan(
        items=_sorted_items(items),
        totals=_totals(invoices),
        summary=f"Due-date fallback plan ({reason}).",
        risk_flags=[],
        planned_count=len(items),
        source="fallback",
    )


@overmind.function(name="compute_currency_totals")
def _totals(invoices: list[InvoiceRecord]) -> list[CurrencyTotal]:
    """Sum amounts per currency in Python — never trust the LLM with arithmetic."""
    sums: dict[str, float] = {}
    for invoice in invoices:
        if invoice.amount is None:
            continue
        sums[invoice.amount.currency] = (
            sums.get(invoice.amount.currency, 0.0) + invoice.amount.value
        )
    return [
        CurrencyTotal(currency=currency, value=round(value, 2))
        for currency, value in sorted(sums.items())
    ]


_PRIORITY_ORDER: dict[Priority, int] = {"pay_now": 0, "schedule": 1, "hold": 2}


def _sorted_items(items: list[PaymentPlanItem]) -> list[PaymentPlanItem]:
    return sorted(
        items,
        key=lambda item: (_PRIORITY_ORDER[item.priority], item.pay_by or "9999-12-31"),
    )


def _planner_input(invoices: list[InvoiceRecord], today: date | None = None) -> list[dict]:
    """Invoice facts for the planner, with date math done here rather than by the LLM."""
    today = today or _today()
    return [
        {
            "invoiceId": invoice.id,
            "vendor": invoice.vendor,
            "amount": invoice.amount.value if invoice.amount else None,
            "currency": invoice.amount.currency if invoice.amount else None,
            "dueDate": invoice.due_date,
            "daysUntilDue": _days_until(invoice.due_date, today),
            "invoiceNumber": invoice.invoice_number,
            "confidence": invoice.confidence,
            "summary": invoice.summary,
        }
        for invoice in invoices
    ]


@overmind.workflow(name="plan_payments_llm")
@traceable(name="plan_payments_llm", tags=["planner"])
def _plan_core(invoices: list[InvoiceRecord]) -> PaymentPlan:
    today = _today()
    user_prompt = f"""Build the payment plan for these invoices.

Today is {today.isoformat()}.

Return ONLY valid JSON with exactly these keys:
{{
  "items": [
    {{
      "invoiceId": string,
      "priority": "pay_now"|"schedule"|"hold",
      "payBy": "YYYY-MM-DD"|null,
      "reason": string
    }}
  ],
  "summary": string,
  "riskFlags": [string]
}}

Include one item for every invoice below, using its exact invoiceId.
"summary" is 1–2 sentences on what the team should do first and the overall exposure.
"daysUntilDue" is already computed for you: negative means overdue, null means no due date.

Invoices:
{json.dumps(_planner_input(invoices, today), indent=2)}"""

    parsed = chat_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0.1,
    )
    llm_plan = LlmPaymentPlan.model_validate(parsed)

    by_id = {invoice.id: invoice for invoice in invoices}
    seen: set[str] = set()
    items: list[PaymentPlanItem] = []
    for llm_item in llm_plan.items:
        invoice = by_id.get(llm_item.invoice_id)
        if invoice is None or invoice.id in seen:
            continue
        seen.add(invoice.id)
        items.append(
            PaymentPlanItem(
                invoice_id=invoice.id,
                vendor=invoice.vendor,
                priority=llm_item.priority,
                pay_by=llm_item.pay_by or invoice.due_date,
                reason=llm_item.reason or "No reason given.",
            )
        )

    # Invoices the model skipped still need a verdict — fall back to due-date rules.
    for invoice in invoices:
        if invoice.id in seen:
            continue
        priority, reason = _fallback_priority(invoice, today)
        items.append(
            PaymentPlanItem(
                invoice_id=invoice.id,
                vendor=invoice.vendor,
                priority=priority,
                pay_by=invoice.due_date,
                reason=reason,
            )
        )

    return PaymentPlan(
        items=_sorted_items(items),
        totals=_totals(invoices),
        summary=llm_plan.summary or "Payment plan ready.",
        risk_flags=llm_plan.risk_flags,
        planned_count=len(items),
        source="llm",
    )


@overmind.entry_point(name="plan_payments")
@traceable(name="plan_payments", tags=["planner"])
def _plan_payments(invoices: list[InvoiceRecord]) -> PaymentPlan:
    considered = sorted(invoices, key=lambda inv: inv.due_date or "9999-12-31")
    considered = considered[:MAX_PLANNED_INVOICES]

    if not considered:
        return PaymentPlan(
            summary="No payable invoices to plan.",
            planned_count=0,
            source="empty",
        )

    try:
        return _plan_core(considered)
    except Exception as exc:
        # A broken plan must not fail a scan that already produced invoices.
        overmind.capture_exception(exc)
        return _fallback_plan(considered, str(exc))


def plan_payments(invoices: list[InvoiceRecord]) -> PaymentPlan:
    """Second agent: rank the triaged invoices into pay now / schedule / hold."""
    configure_overmind()
    # Both agents share this process, so re-stamp identity before the span opens
    # or the planner's spans inherit the triage agent's id.
    overmind.set_agent_id(PLANNER_AGENT_ID)
    overmind.set_agent_name(PLANNER_AGENT_NAME)
    return _plan_payments(invoices)
