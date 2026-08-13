"""Themes stress corpus runner with concurrency."""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts._env import load_env_local, require_llm_env  # noqa: E402


def main() -> None:
    load_env_local()
    require_llm_env()

    # Prefer local Ollama when configured (cost). OpenAI remains default otherwise.
    if os.environ.get("OLLAMA_BASE_URL"):
        os.environ.pop("OPENAI_API_KEY", None)

    from invoice_agent.agent.llm import get_llm_status
    from invoice_agent.themes_corpus import (
        analyze_themes_email,
        generate_themes_corpus,
        tally_modes,
    )

    count = int(os.environ.get("THEMES_EMAIL_COUNT") or 1200)
    concurrency = max(1, int(os.environ.get("THEMES_CONCURRENCY") or 8))

    items, mode_by_email_id = generate_themes_corpus(count)
    if len(items) != count:
        print(
            f"Hard failure: expected {count} themes emails, found {len(items)}",
            file=sys.stderr,
        )
        sys.exit(1)

    planned = tally_modes(items)
    status = get_llm_status()
    print(
        f"Themes corpus: {len(items)} emails, concurrency={concurrency} "
        f"({status['provider']}/{status['model']})\n"
    )
    print("Planned mode mix:")
    for mode in sorted(planned.keys()):
        print(f"  {mode}: {planned[mode]}")
    print("")

    started = time.time()
    results: list = [None] * len(items)
    completed = 0

    def work(i: int):
        return i, analyze_themes_email(items[i])

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(work, i) for i in range(len(items))]
        for fut in as_completed(futures):
            i, outcome = fut.result()
            results[i] = outcome
            completed += 1
            if completed % 25 == 0 or completed == len(items):
                failed = sum(1 for r in results[:completed] if r and not r.ok)
                # Count failed among completed slots (may be sparse with as_completed)
                failed = sum(1 for r in results if r is not None and not r.ok)
                elapsed_sec = f"{time.time() - started:.1f}"
                item = items[i]
                print(
                    f"  [{completed}/{len(items)}] failed={failed} "
                    f"elapsed={elapsed_sec}s last={item.email.id} "
                    f"mode={item.mode} ok={outcome.ok}"
                )

    elapsed_sec = f"{time.time() - started:.1f}"
    by_mode: dict[str, int] = {}
    for row in results:
        if not row:
            continue
        mode = mode_by_email_id.get(row.email_id) or row.mode
        by_mode[mode] = by_mode.get(mode, 0) + 1

    ok_count = sum(1 for r in results if r and r.ok)
    fail_count = sum(1 for r in results if r and not r.ok)

    print("\nThemes corpus summary")
    print(f"  Provider/model: {status['provider']}/{status['model']}")
    print(f"  Total attempted: {len(results)}")
    print(f"  Completed ok (no throw): {ok_count}")
    print(f"  Completed with error status: {fail_count}")
    print(f"  Elapsed: {elapsed_sec}s")
    print("\nPer-mode tally (intended tags):")
    for mode in sorted(by_mode.keys()):
        print(f"  {mode}: {by_mode[mode]}")
    sys.exit(0)


if __name__ == "__main__":
    main()
