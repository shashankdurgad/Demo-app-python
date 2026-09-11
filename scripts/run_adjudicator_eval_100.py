"""Run Ledgerline Adjudicator over the disjoint 100-claim eval corpus."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402

DEFAULT_SIDECAR = ROOT / "artifacts" / "adjudicator-eval-100.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ledgerline Adjudicator on the disjoint eval corpus."
    )
    parser.add_argument("--limit", type=int, default=100, help="Run only the first N claims.")
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=DEFAULT_SIDECAR,
        help="JSONL path for claim + constructed ground truth.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    load_env_local()
    require_llm_env()

    from invoice_agent.agent.adjudicator import adjudicate_claim
    from invoice_agent.agent.llm import get_adjudicator_llm_status
    from invoice_agent.adjudicator_eval_claims import ADJUDICATOR_EVAL_CASES

    status = get_adjudicator_llm_status()
    model = status.get("model")

    cases = ADJUDICATOR_EVAL_CASES[: max(0, args.limit)]
    if not cases:
        print("Hard failure: --limit produced no cases", file=sys.stderr)
        sys.exit(1)

    sidecar_path: Path = args.sidecar
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text("", encoding="utf-8")

    started = datetime.now(timezone.utc)
    print(
        f"Running {len(cases)} EVAL claims through adjudicate_claim "
        f"({status['provider']}/{model}) started={started.isoformat()}\n"
    )

    rows: list[dict] = []
    t0 = time.time()
    for i, case in enumerate(cases):
        last_err: Exception | None = None
        result = None
        for attempt in range(2):
            try:
                result = adjudicate_claim(case.claim)
                last_err = None
                break
            except Exception as err:
                last_err = err
                print(
                    f"  retry {attempt + 1} on {case.claim.claim_id}: {err}",
                    file=sys.stderr,
                )
                time.sleep(2 * (attempt + 1))
        if last_err is not None or result is None:
            print(f"Hard failure on {case.claim.claim_id}: {last_err}", file=sys.stderr)
            sys.exit(1)

        row = {
            "claim_id": case.claim.claim_id,
            "bucket": case.bucket,
            "input": case.claim.model_dump(),
            "expected": case.expected.model_dump(),
            "model_output": result.model_dump(),
        }
        rows.append(row)
        with sidecar_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")

        n = i + 1
        if n % 10 == 0 or n == len(cases):
            elapsed = f"{time.time() - t0:.1f}"
            print(
                f"  [{n}/{len(cases)}] elapsed={elapsed}s "
                f"last={case.claim.claim_id} bucket={case.bucket} "
                f"expected={case.expected.decision} got={result.decision} "
                f"conf={result.confidence}"
            )

    expected_decisions = Counter(r["expected"]["decision"] for r in rows)
    model_decisions = Counter(r["model_output"]["decision"] for r in rows)
    buckets = Counter(r["bucket"] for r in rows)
    confs = [float(r["model_output"]["confidence"]) for r in rows]
    print("\nAdjudicator EVAL run summary")
    print(f"  rows: {len(rows)}")
    print(f"  buckets: {dict(buckets)}")
    print(f"  constructed decisions: {dict(expected_decisions)}")
    print(f"  model decisions: {dict(model_decisions)}")
    print(
        f"  model confidence min={min(confs):.2f} max={max(confs):.2f} "
        f"below_0.8={sum(1 for c in confs if c < 0.8)}"
    )
    print(f"  sidecar: {sidecar_path}")
    print(f"  started_at: {started.isoformat()}")


if __name__ == "__main__":
    main()
