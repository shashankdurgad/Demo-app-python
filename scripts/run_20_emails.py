"""Run the 20 handcrafted demo emails through analyze_email."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402


def main() -> None:
    load_env_local()
    require_llm_env()

    from invoice_agent.agent.llm import get_llm_status
    from invoice_agent.agent.triage import analyze_email
    from invoice_agent.demo_emails import DEMO_EMAILS
    from invoice_agent.observability import flush_langfuse, init_langfuse

    init_langfuse()

    if len(DEMO_EMAILS) != 20:
        print(
            f"Hard failure: expected exactly 20 demo emails, found {len(DEMO_EMAILS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    status = get_llm_status()
    print(
        f"Running {len(DEMO_EMAILS)} emails through analyzeEmail "
        f"({status['provider']}/{status['model']})…\n"
    )

    rows = []
    for email in DEMO_EMAILS:
        try:
            record = analyze_email(email, "demo")
        except Exception as err:
            print(f"Hard failure on {email.id}: {err}", file=sys.stderr)
            flush_langfuse()
            sys.exit(1)

        row = {
            "emailId": email.id,
            "subject": email.subject,
            "isInvoice": bool(record),
            "harnessOutput": record.model_dump(by_alias=True) if record else None,
        }
        rows.append(row)
        print(json.dumps(row, indent=2))
        print("---")

    invoice_rows = [r for r in rows if r["isInvoice"]]
    print("\nSummary")
    print(f"  Scanned: {len(DEMO_EMAILS)}")
    print(f"  Classified as invoices: {len(invoice_rows)}")
    print(f"  Rejected / non-invoices: {len(DEMO_EMAILS) - len(invoice_rows)}")
    flush_langfuse()
    sys.exit(0)


if __name__ == "__main__":
    main()
