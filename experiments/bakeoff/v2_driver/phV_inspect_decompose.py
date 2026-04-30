#!/usr/bin/env python3
"""
Phase V probe — inspect what `loom decompose` produces for the R6 spec.

Goal: compare auto-decomposed task titles against R6m's hand-authored
titles. The R6m result showed 95 % pass rate even WITHOUT a spec, when
task titles were precise multi-sentence recipes. The question this
probe answers: does the actual decomposer produce titles that precise?

Sets up:
  1. Temp workspace with pyschema-extended ground_truth files (so
     decompose's validator sees real files for files_to_modify).
  2. Loom project with REQ + SPEC seeded; SPEC text = the same R6
     rule text used in phT/phU.
  3. Runs `loom decompose --apply` and prints the produced tasks.

No grading here — this is a one-shot inspection. If the auto-tasks
look R6m-precise, we follow up with phV harness using them. If they
look coarser, we capture that as the gap.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "pyschema-extended" / "ground_truth")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from store import LoomStore  # noqa: E402
import services  # noqa: E402


# Same R6 rule text used in phT/phU
TASK = (
    "Add a RegexField type to pyschema-extended that takes a regex "
    "`pattern: str` and validates string inputs against the pattern. "
    "RegexField should integrate with the existing Field hierarchy "
    "and be importable as `from pyschema import RegexField` after "
    "the change."
)

SPEC_RULE = (
    "Constraint for adding RegexField (multi-step refactor):\n"
    "- Place the new class in `pyschema/fields/strings.py` "
    "(alongside EmailField/URLField/UUIDField, all string-typed "
    "specializations of StrField).\n"
    "- Inherit from `StrField` so it gets length validators + str "
    "coercion for free.\n"
    "- Decorate with `@dataclass` to match the sibling field types.\n"
    "- Override `validate()` to call `super().validate(value)` first, "
    "then apply `re.match(self.pattern, result)` — raise "
    "ValidationError on mismatch.\n"
    "- Re-export RegexField from `pyschema/fields/__init__.py` and "
    "add it to that file's `__all__`.\n"
    "- Re-export RegexField from `pyschema/__init__.py` and add it "
    "to its `__all__` (alphabetically after `Pattern`).\n"
    "- Default for `pattern: str` should be empty string \"\" so "
    "existing dataclass field-ordering rules are not violated.\n"
)


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phV_decompose_inspect_"))
    shutil.copytree(SCENARIO_DIR / "reference" / "pyschema",
                     ws / "pyschema")
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace",
                    "model": "qwen3.5:latest"}, indent=2),
        encoding="utf-8",
    )
    return ws


def main() -> int:
    project = "phV_decompose_inspect"
    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)
    workspace = setup_workspace()
    print(f"[setup] workspace={workspace}  project={project}")

    req = services.extract(
        store, domain="behavior",
        value=TASK,
        rationale="phV — auto-decompose inspection probe",
    )
    spec = services.spec_add(store, req["req_id"], SPEC_RULE)
    print(f"[seed] req={req['req_id']}  spec={spec['spec_id']}")

    # Close store so subprocess sees a consistent SQLite WAL state
    store.conn.close()

    # Run loom decompose --apply
    cmd = [
        sys.executable,
        str(LOOM_DIR / "scripts" / "loom"),
        "decompose", spec["spec_id"], "--apply",
        "-p", project,
        "--target-dir", str(workspace),
    ]
    print(f"[decompose] running: {' '.join(cmd[:7])} ...")
    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    print(f"[decompose] rc={proc.returncode}")
    print("--- stdout ---")
    print(proc.stdout)
    if proc.stderr:
        print("--- stderr ---")
        print(proc.stderr[:3000])

    # Read the persisted tasks back from the store and dump them
    store2 = LoomStore(project=project)
    print()
    print("=== Auto-generated tasks (read back from store) ===")
    tasks = store2.list_tasks()
    for i, t in enumerate(tasks, 1):
        print(f"\n--- Task {i}: {t.id} ---")
        print(f"title: {t.title}")
        print(f"files_to_modify: {t.files_to_modify}")
        print(f"depends_on: {t.depends_on}")
        print(f"context_files: {t.context_files}")
        print(f"size_budget: {t.size_budget_files} files / {t.size_budget_loc} LoC")
    store2.conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
