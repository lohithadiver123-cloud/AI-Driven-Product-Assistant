"""
Remove benchmark rows that were written into the live fallback store.

Background
----------
`backend/tests/test_10k_benchmark.py` seeds 10,000 generated rows under the workspace id
`test_10k_ws` into the JSON fallback database. Across repeated runs that left 110,000
rows — 54.4 MB — inside `backend/.demo_data/feedback.json`, against 110 rows of real data.

No workspace with the id `test_10k_ws` exists, so those rows are invisible in the product:
they are pure weight. Every fallback operation re-parsed the whole file before the
modification-time cache was added, and every fallback write re-serialised all 54 MB.

This script removes rows for the given workspace ids, backing the file up first.
It is safe to re-run: a second run finds nothing to do.

Usage
-----
    cd backend
    ./.venv/Scripts/python.exe purge_benchmark_feedback.py             # dry run
    ./.venv/Scripts/python.exe purge_benchmark_feedback.py --apply
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".demo_data")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")
BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".migrations")

# Workspace ids that only ever existed inside tests.
BENCHMARK_WORKSPACE_IDS = {"test_10k_ws"}


def _size_mb(path: str) -> float:
    return os.path.getsize(path) / 1024 / 1024 if os.path.exists(path) else 0.0


def purge(apply: bool) -> None:
    if not os.path.exists(FEEDBACK_FILE):
        print(f"No fallback feedback file at {FEEDBACK_FILE}; nothing to do.")
        return

    before_mb = _size_mb(FEEDBACK_FILE)
    with open(FEEDBACK_FILE, "r") as handle:
        rows = json.load(handle)

    def is_benchmark(row):
        return isinstance(row, dict) and row.get("workspace_id") in BENCHMARK_WORKSPACE_IDS

    doomed = [row for row in rows if is_benchmark(row)]
    kept = [row for row in rows if not is_benchmark(row)]

    print(f"{FEEDBACK_FILE}")
    print(f"  size before : {before_mb:.1f} MB")
    print(f"  rows total  : {len(rows)}")
    print(f"  benchmark   : {len(doomed)}  (workspace ids: {sorted(BENCHMARK_WORKSPACE_IDS)})")
    print(f"  rows kept   : {len(kept)}")

    if not doomed:
        print("Nothing to remove.")
        return

    if not apply:
        print("\nDry run. Re-run with --apply to rewrite the file.")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"feedback-before-purge-{stamp}.json")
    shutil.copy2(FEEDBACK_FILE, backup_path)
    print(f"\nBacked up the original to {backup_path}")

    with open(FEEDBACK_FILE, "w") as handle:
        json.dump(kept, handle, indent=2, default=str)

    print(f"Rewrote {FEEDBACK_FILE}")
    print(f"  size after  : {_size_mb(FEEDBACK_FILE):.3f} MB  (was {before_mb:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default is a dry run)")
    args = parser.parse_args()
    purge(args.apply)
