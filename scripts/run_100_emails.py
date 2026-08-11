"""Run N generated demo emails (default 100) through analyze_email."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402


def main() -> None:
    load_env_local()
    require_llm_env()

    from invoice_agent.agent.llm import get_llm_status
    from invoice_agent.agent.triage import analyze_email
    from invoice_agent.generate_demo_emails import generate_demo_emails
    from invoice_agent.observability import init_langfuse

    init_langfuse()

    count = int(os.environ.get("DEMO_EMAIL_COUNT") or 100)
    emails = generate_demo_emails(count)
    if len(emails) != count:
        print(
            f"Hard failure: expected {count} generated emails, found {len(emails)}",
            file=sys.stderr,
        )
        sys.exit(1)

    status = get_llm_status()
    print(
        f"Running {len(emails)} generated emails through analyzeEmail "
        f"({status['provider']}/{status['model']})…\n"
    )

    rows = []
    started = time.time()

    for i, email in enumerate(emails):
        try:
            record = analyze_email(email, "demo")
        except Exception as err:
            print(f"Hard failure on {email.id}: {err}", file=sys.stderr)
            sys.exit(1)

        row = {
            "emailId": email.id,
            "subject": email.subject,
            "isInvoice": bool(record),
            "confidence": record.confidence if record else None,
            "vendor": record.vendor if record else None,
            "amount": record.amount.raw if record and record.amount else None,
            "dueDate": record.due_date if record else None,
            "summary": record.summary if record else None,
        }
        rows.append(row)

        n = i + 1
        if n % 10 == 0 or n == len(emails):
            invoice_so_far = sum(1 for r in rows if r["isInvoice"])
            elapsed_sec = f"{time.time() - started:.1f}"
            print(
                f"  [{n}/{len(emails)}] invoices={invoice_so_far} "
                f"elapsed={elapsed_sec}s last={email.id} isInvoice={row['isInvoice']}"
            )

    invoice_rows = [r for r in rows if r["isInvoice"]]
    print("\nSummary")
    print(f"  Scanned: {len(emails)}")
    print(f"  Classified as invoices: {len(invoice_rows)}")
    print(f"  Rejected / non-invoices: {len(emails) - len(invoice_rows)}")
    print(f"  Elapsed: {time.time() - started:.1f}s")

    print("\nSample responses (first 10 invoices):")
    for row in invoice_rows[:10]:
        print(
            f"  • {row['vendor']}: {row['amount']}, due {row['dueDate']} "
            f"(confidence {row['confidence']})"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
