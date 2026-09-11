"""Run the 100-email hard eval corpus through analyze_email on gpt-5.2."""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402

SESSION_ID = "eval-hard-100-2026-08-26"
RESULTS_PATH = Path("/tmp/ledgerline-eval-hard-100.jsonl")
TEACHER_MODEL = "gpt-5.2"


def main() -> None:
    load_env_local()
    require_llm_env()
    os.environ["OPENAI_MODEL"] = TEACHER_MODEL

    from invoice_agent.agent.braintrust_tracing import configure_braintrust, flush_braintrust
    from invoice_agent.agent.galileo_tracing import (
        configure_galileo,
        flush_galileo,
        start_galileo_session,
    )
    from invoice_agent.agent.langfuse_tracing import configure_langfuse, flush_langfuse
    from invoice_agent.agent.llm import get_llm_status
    from invoice_agent.agent.tracing import flush_langsmith
    from invoice_agent.agent.triage import analyze_email
    from invoice_agent.agent import triage as triage_mod
    from invoice_agent.eval_hard_emails import EVAL_HARD_CASES

    status = get_llm_status()
    model = status.get("model")
    if model != TEACHER_MODEL:
        print(
            f"Hard failure: teacher must be {TEACHER_MODEL}, got {model!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    configure_galileo()
    configure_langfuse()
    configure_braintrust()
    start_galileo_session(SESSION_ID)

    captures: list = []
    orig = triage_mod.analyze_email_with_llm

    def _capturing(*args, **kwargs):
        result = orig(*args, **kwargs)
        captures.append(result)
        return result

    triage_mod.analyze_email_with_llm = _capturing

    started = datetime.now(timezone.utc)
    print(
        f"Running {len(EVAL_HARD_CASES)} emails through analyze_email "
        f"({status['provider']}/{model}) session={SESSION_ID} "
        f"started={started.isoformat()}\n"
    )

    rows: list[dict] = []
    t0 = time.time()
    RESULTS_PATH.write_text("", encoding="utf-8")

    for i, case in enumerate(EVAL_HARD_CASES):
        captures.clear()
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                analyze_email(case.email, "demo")
                last_err = None
                break
            except Exception as err:
                last_err = err
                print(
                    f"  retry {attempt + 1} on {case.email.id}: {err}",
                    file=sys.stderr,
                )
                time.sleep(2 * (attempt + 1))
        if last_err is not None:
            print(f"Hard failure on {case.email.id}: {last_err}", file=sys.stderr)
            sys.exit(1)
        if len(captures) != 1:
            print(
                f"Hard failure: expected 1 LLM capture for {case.email.id}, "
                f"got {len(captures)}",
                file=sys.stderr,
            )
            sys.exit(1)

        extraction = captures[0]
        row = {
            "emailId": case.email.id,
            "bucket": case.bucket,
            "ambiguous": case.ambiguous,
            "isInvoice": extraction.is_invoice,
            "vendor": extraction.vendor,
            "amount": extraction.amount,
            "currency": extraction.currency,
            "dueDate": extraction.due_date,
            "invoiceNumber": extraction.invoice_number,
            "confidence": extraction.confidence,
            "summary": extraction.summary,
        }
        rows.append(row)
        with RESULTS_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

        n = i + 1
        if n % 10 == 0 or n == len(EVAL_HARD_CASES):
            elapsed = f"{time.time() - t0:.1f}"
            print(
                f"  [{n}/{len(EVAL_HARD_CASES)}] elapsed={elapsed}s "
                f"last={case.email.id} bucket={case.bucket} "
                f"isInvoice={row['isInvoice']} conf={row['confidence']}"
            )

    flush_galileo()
    flush_langfuse()
    flush_langsmith()
    flush_braintrust()
    confs = [float(r["confidence"]) for r in rows]
    print("\nLocal teacher summary")
    print(f"  rows: {len(rows)}")
    print(f"  isInvoice=false: {sum(1 for r in rows if not r['isInvoice'])}")
    print(f"  dueDate=null: {sum(1 for r in rows if r['dueDate'] is None)}")
    print(f"  currency=null: {sum(1 for r in rows if r['currency'] is None)}")
    print(
        f"  confidence min={min(confs):.2f} max={max(confs):.2f} "
        f"below_0.8={sum(1 for c in confs if c < 0.8)}"
    )
    print(f"  results: {RESULTS_PATH}")
    print(f"  session: {SESSION_ID}")
    print(f"  started_at: {started.isoformat()}")
    sys.exit(0)


if __name__ == "__main__":
    main()
