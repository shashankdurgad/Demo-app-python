"""Eval B — 50 additional gold scenarios."""

from __future__ import annotations

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
    from invoice_agent.eval_emails_b import EVAL_SCENARIOS_B_50

    if len(EVAL_SCENARIOS_B_50) != 50:
        print(
            f"Hard failure: expected 50 eval-B scenarios, found {len(EVAL_SCENARIOS_B_50)}",
            file=sys.stderr,
        )
        sys.exit(1)

    status = get_llm_status()
    print(
        f"Running {len(EVAL_SCENARIOS_B_50)} eval-B scenarios "
        f"({status['provider']}/{status['model']})…\n"
    )

    results = []
    triage_correct = 0
    started = time.time()

    for i, scenario in enumerate(EVAL_SCENARIOS_B_50):
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

        results.append(
            {
                "id": email.id,
                "notes": expected.notes,
                "expectedIsInvoice": expected.is_invoice,
                "predictedIsInvoice": predicted_is_invoice,
                "triageOk": triage_ok,
                "confidence": record.confidence if record else None,
                "vendor": record.vendor if record else None,
                "amount": record.amount.raw if record and record.amount else None,
            }
        )

        mark = "OK" if triage_ok else "MISS"
        print(
            f"[{i + 1:02d}/50] {mark} {email.id} expected={expected.is_invoice} "
            f"got={predicted_is_invoice} — {expected.notes}"
        )

    misses = [r for r in results if not r["triageOk"]]
    print("\nEval-B summary")
    print(f"  Scenarios: {len(results)}")
    print(
        f"  Triage accuracy (isInvoice): {triage_correct}/{len(results)} "
        f"({100 * triage_correct / len(results):.1f}%)"
    )
    print(f"  Misses: {len(misses)}")
    print(f"  Elapsed: {time.time() - started:.1f}s")

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
