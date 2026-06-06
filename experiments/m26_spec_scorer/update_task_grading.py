"""M26 Q.2 — re-point each task's grading test at a task-appropriate
smoke (workaround for F6).

Default decomp put the full TestSpecScoring on every task. Tasks 1-4
cannot pass it until task 3 produces the implementation. This script
swaps in per-task smoke tests so loom_exec gets honest per-task signal.

Run once. Verify with `loom task list -p loom --json`.
"""
from __future__ import annotations

from pathlib import Path

from loom.store import LoomStore


# Task ID → grading test target (M26 task-to-smoke mapping)
TASK_GRADING: dict[str, str] = {
    # task 1 — author prompt file
    "d4089f1b7d1aeef8": "tests/test_spec_scoring.py::TestSmokePromptFile",
    # task 2 — add score_specification signature
    "4af75bf4f5a41a2b": "tests/test_spec_scoring.py::TestSmokeSignatureImportable",
    # task 3 — implement core logic (THE feature; full grading)
    "44170545b4395a3d": "tests/test_spec_scoring.py::TestSpecScoring",
    # task 4 — CLI command
    "d9090815104385d1": "tests/test_spec_scoring.py::TestSmokeCliSpecScore",
    # task 5 — in-band scoring on `loom spec` create
    "9f1835d47cb29e0a": "tests/test_spec_scoring.py::TestSmokeInBandScoring",
}


def main() -> int:
    store = LoomStore(
        project="loom",
        data_dir=Path.home() / ".openclaw" / "loom" / "loom",
    )

    for task_id, new_test in TASK_GRADING.items():
        existing = store.get_task(task_id)
        if existing is None:
            print(f"SKIP {task_id} — not found in store")
            continue
        store.update_task(task_id, {"test_to_write": new_test})
        print(f"OK   {task_id}  test_to_write = {new_test}")

    print()
    print(f"Updated {len(TASK_GRADING)} task(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
