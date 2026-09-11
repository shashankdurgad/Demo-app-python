"""Run Ledgerline Adjudicator over the 100-claim constructed corpus."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402

TEACHER_MODEL = "gpt-5.6"
DEFAULT_SIDECAR = ROOT / "artifacts" / "adjudicator-100.jsonl"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ledgerline Adjudicator on the constructed 100-claim corpus."
    )
    parser.add_argument("--limit", type=int, default=100, help="Run only the first N claims.")
    parser.add_argument(
        "--sidecar",
        type=Path,
        default=DEFAULT_SIDECAR,
        help="JSONL path for claim + constructed ground truth.",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="Overmind conversation id (defaults to a timestamped id).",
    )
    parser.add_argument(
        "--check-tools",
        action="store_true",
        help="Verify fixture tools are byte-identical across two calls, then exit.",
    )
    return parser.parse_args()


def _check_tools() -> None:
    from invoice_agent.adjudicator_fixtures import (
        get_fx_rate_fixture,
        get_submitter_history_fixture,
        lookup_policy_fixture,
        post_decision_fixture,
    )

    first = json.dumps(lookup_policy_fixture("travel", "US", "2026-07-12"), sort_keys=True)
    second = json.dumps(lookup_policy_fixture("travel", "US", "2026-07-12"), sort_keys=True)
    fx1 = json.dumps(get_fx_rate_fixture("EUR", "USD", "2026-03-15"), sort_keys=True)
    fx2 = json.dumps(get_fx_rate_fixture("EUR", "USD", "2026-03-15"), sort_keys=True)
    hist1 = json.dumps(get_submitter_history_fixture("emp-viol-00"), sort_keys=True)
    hist2 = json.dumps(get_submitter_history_fixture("emp-viol-00"), sort_keys=True)
    post_args = dict(
        claim_id="CLM-0001",
        decision="approve",
        approved_amount=280.0,
        policy_clause="TRV-04",
        rationale="within cap",
    )
    post1 = json.dumps(post_decision_fixture(**post_args), sort_keys=True)
    post2 = json.dumps(post_decision_fixture(**post_args), sort_keys=True)
    if not (first == second and fx1 == fx2 and hist1 == hist2 and post1 == post2):
        print("Hard failure: tool outputs were not byte-identical", file=sys.stderr)
        sys.exit(1)
    print("Tool outputs are byte-identical on a second call.")
    print(f"  lookup_policy: {first}")
    print(f"  get_fx_rate:   {fx1}")
    print(f"  history:       {hist1}")
    print(f"  post_decision: {post1}")


def main() -> None:
    args = _parse_args()
    load_env_local()
    os.environ["ADJUDICATOR_MODEL"] = TEACHER_MODEL

    if args.check_tools:
        _check_tools()
        return

    require_llm_env()
    if not os.environ.get("OVERMIND_API_KEY"):
        print("Hard failure: OVERMIND_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    from invoice_agent.agent.adjudicator import adjudicate_claim
    from invoice_agent.agent.galileo_tracing import (
        configure_galileo,
        flush_galileo,
        start_galileo_session,
    )
    from invoice_agent.agent.braintrust_tracing import configure_braintrust, flush_braintrust
    from invoice_agent.agent.langfuse_tracing import configure_langfuse, flush_langfuse
    from invoice_agent.agent.llm import get_adjudicator_llm_status
    from invoice_agent.agent.overmind_tracing import configure_overmind
    from invoice_agent.agent.tracing import flush_langsmith
    from invoice_agent.adjudicator_claims import ADJUDICATOR_CASES
    import overmind

    status = get_adjudicator_llm_status()
    model = status.get("model")
    if model != TEACHER_MODEL:
        print(
            f"Hard failure: adjudicator teacher must be {TEACHER_MODEL}, got {model!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    cases = ADJUDICATOR_CASES[: max(0, args.limit)]
    if not cases:
        print("Hard failure: --limit produced no cases", file=sys.stderr)
        sys.exit(1)

    session_id = args.session or (
        f"adjudicator-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )

    configure_overmind()
    configure_galileo()
    configure_langfuse()
    configure_braintrust()
    overmind.set_conversation_id(session_id)
    start_galileo_session(session_id)

    sidecar_path: Path = args.sidecar
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text("", encoding="utf-8")

    started = datetime.now(timezone.utc)
    print(
        f"Running {len(cases)} claims through adjudicate_claim "
        f"({status['provider']}/{model}) session={session_id} "
        f"started={started.isoformat()}\n"
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

    overmind.force_flush_traces()
    flush_galileo()
    flush_langfuse()
    flush_langsmith()
    flush_braintrust()

    expected_decisions = Counter(r["expected"]["decision"] for r in rows)
    model_decisions = Counter(r["model_output"]["decision"] for r in rows)
    buckets = Counter(r["bucket"] for r in rows)
    confs = [float(r["model_output"]["confidence"]) for r in rows]
    print("\nAdjudicator run summary")
    print(f"  rows: {len(rows)}")
    print(f"  buckets: {dict(buckets)}")
    print(f"  constructed decisions: {dict(expected_decisions)}")
    print(f"  model decisions: {dict(model_decisions)}")
    print(
        f"  model confidence min={min(confs):.2f} max={max(confs):.2f} "
        f"below_0.8={sum(1 for c in confs if c < 0.8)}"
    )
    print(f"  sidecar: {sidecar_path}")
    print(f"  session: {session_id}")
    print(f"  started_at: {started.isoformat()}")


if __name__ == "__main__":
    main()
