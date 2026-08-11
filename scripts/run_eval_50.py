"""Eval A — 50 gold scenarios, primary metric isInvoice triage accuracy."""

from __future__ import annotations

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
    from invoice_agent.eval_emails import EVAL_SCENARIOS_50
    from invoice_agent.observability import init_langfuse

    init_langfuse()

    if len(EVAL_SCENARIOS_50) != 50:
        print(
            f"Hard failure: expected 50 eval scenarios, found {len(EVAL_SCENARIOS_50)}",
            file=sys.stderr,
        )
        sys.exit(1)

    status = get_llm_status()
    print(
        f"Running {len(EVAL_SCENARIOS_50)} eval scenarios through analyzeEmail "
        f"({status['provider']}/{status['model']})…\n"
    )

    results = []
    triage_correct = 0

    for i, scenario in enumerate(EVAL_SCENARIOS_50):
        email = scenario.email
        expected = scenario.expected

        try:
            record = analyze_email(email, "demo")
        except Exception as err:
            print(f"Hard failure on {email.id}: {err}", file=sys.stderr)
            sys.exit(1)

        predicted_is_invoice = bool(record)
        triage_ok = predicted_is_invoice == expected.is_invoice
        if triage_ok:
            triage_correct += 1

        row = {
            "id": email.id,
            "subject": email.subject,
            "notes": expected.notes,
            "expectedIsInvoice": expected.is_invoice,
            "predictedIsInvoice": predicted_is_invoice,
            "triageOk": triage_ok,
            "expectedAmount": expected.amount,
            "predictedAmount": record.amount.value if record and record.amount else None,
            "expectedDue": expected.due_date,
            "predictedDue": record.due_date if record else None,
            "confidence": record.confidence if record else None,
            "vendor": record.vendor if record else None,
        }
        results.append(row)

        mark = "OK" if triage_ok else "MISS"
        print(
            f"[{i + 1:02d}/50] {mark} {email.id} expected={expected.is_invoice} "
            f"got={predicted_is_invoice} — {expected.notes}"
        )

    misses = [r for r in results if not r["triageOk"]]
    print("\nEval summary")
    print(f"  Scenarios: {len(results)}")
    print(
        f"  Triage accuracy (isInvoice): {triage_correct}/{len(results)} "
        f"({100 * triage_correct / len(results):.1f}%)"
    )
    print(f"  Misses: {len(misses)}")

    if misses:
        print("\nMissed triage cases:")
        for m in misses:
            print(
                f"  • {m['id']}: expected isInvoice={m['expectedIsInvoice']}, "
                f"got {m['predictedIsInvoice']} — {m['notes']}"
            )
    sys.exit(0)


if __name__ == "__main__":
    main()
