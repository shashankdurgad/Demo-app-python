"""Run both Ledgerline agents end to end: invoice triage, then payment planning."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402

PRIORITY_LABELS = {
    "pay_now": "PAY NOW ",
    "schedule": "SCHEDULE",
    "hold": "HOLD    ",
}


def _money(amount) -> str:
    if amount is None:
        return "—"
    return f"{amount.currency} {amount.value:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the invoice-triage agent, then the payment-planner agent."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="only triage the first N demo emails (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="also print the combined result as JSON",
    )
    args = parser.parse_args()

    load_env_local()
    require_llm_env()

    from invoice_agent.agent.llm import get_llm_status
    from invoice_agent.agent.planner import plan_payments
    from invoice_agent.agent.triage import run_invoice_agent
    from invoice_agent.demo_emails import DEMO_EMAILS

    emails = DEMO_EMAILS[: args.limit] if args.limit else list(DEMO_EMAILS)
    if not emails:
        print("Hard failure: no demo emails selected", file=sys.stderr)
        sys.exit(1)

    status = get_llm_status()
    print(
        f"Agent 1/2 — invoice triage: {len(emails)} emails "
        f"({status['provider']}/{status['model']})\n"
    )

    try:
        invoices = run_invoice_agent(emails, "demo")
    except Exception as err:
        print(f"Hard failure in invoice triage: {err}", file=sys.stderr)
        sys.exit(1)

    for invoice in invoices:
        print(
            f"  {invoice.vendor:<28} {_money(invoice.amount):>16}  "
            f"due {invoice.due_date or '—':<12} conf {invoice.confidence:.2f}"
        )
    print(
        f"\n  Invoices: {len(invoices)} · "
        f"Rejected: {len(emails) - len(invoices)}\n"
    )

    print(f"Agent 2/2 — payment planner: ranking {len(invoices)} invoices\n")
    plan = plan_payments(invoices)

    print(f"  {plan.summary}")
    if plan.totals:
        totals = " · ".join(f"{t.currency} {t.value:,.2f}" for t in plan.totals)
        print(f"  Total extracted: {totals}")
    print()

    for item in plan.items:
        print(
            f"  [{PRIORITY_LABELS[item.priority]}] {item.vendor:<28} "
            f"pay by {item.pay_by or '—':<12} {item.reason}"
        )

    if plan.risk_flags:
        print("\n  Risk flags:")
        for flag in plan.risk_flags:
            print(f"    • {flag}")

    if plan.source != "llm":
        print(f"\n  Note: plan came from the '{plan.source}' path, not the planner LLM.")

    if args.json:
        print("\n" + json.dumps(
            {
                "invoices": [inv.model_dump(by_alias=True) for inv in invoices],
                "plan": plan.model_dump(by_alias=True),
            },
            indent=2,
        ))

    sys.exit(0)


if __name__ == "__main__":
    main()
