#!/usr/bin/env python3
"""
Phase U — pyschema-extended R6m: chained-tasks variant of R6.

R6 (phT) showed wiring stayed at 0 % across all cells because
``loom_exec`` only modifies ``files_to_modify[0]`` per task. The
fix this harness tests: decompose the multi-file refactor into 3
chained tasks with ``depends_on``, each one modifying one file,
each with its own gate test. ``loom_exec --loop`` drains the queue
so a successful T1 unblocks T2 unblocks T3.

Pre-registered prediction: D3m wiring goes from 0 % (R6/phT) to
≥80 % (this harness, R6m), confirming the "architectural ceiling"
finding in R6 was a single-task-scope artifact, not a Loom defect.

Tasks:
  T1 — pyschema/fields/strings.py   (add RegexField class)
  T2 — pyschema/fields/__init__.py  (re-export RegexField)        depends_on T1
  T3 — pyschema/__init__.py          (top barrel + __all__)        depends_on T2

Cells (same as R6):
  D1m  qwen-only       (placeholder spec, no context_specs)
  D2m  stored, undelivered (real spec stored, context_specs=[])
  D3m  standard delivery   (real spec stored, context_specs=[spec_id])

Metrics: same 5 as R6 (acceptance, regression, idiom, wiring, import).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
SCENARIO_DIR = (BAKEOFF_DIR / "benchmarks" / "pyschema-extended" / "ground_truth")

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa: E402
from loom import services  # noqa: E402

sys.path.insert(0, str(SCENARIO_DIR / "tests"))
import verify_idiom  # noqa: E402
import verify_wiring  # noqa: E402


# ---------------------------------------------------------------------------
# Aligning task + per-task rules (decomposed from R6's single rule)
# ---------------------------------------------------------------------------

PARENT_TASK = (
    "Add a RegexField type to pyschema-extended that takes a regex "
    "`pattern: str` and validates string inputs against the pattern. "
    "RegexField should integrate with the existing Field hierarchy "
    "and be importable as `from pyschema import RegexField` after "
    "the change."
)

# The full R6 rule, repeated as the spec description (delivered via
# task_build_prompt to D3m tasks). Same text as R6/phT.
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


# Per-task titles. Each focused on its own file.
T1_TITLE = (
    "Step 1 of 3: Add the RegexField class to "
    "pyschema/fields/strings.py. Inherits StrField; takes "
    "`pattern: str` (default ''); overrides validate() to call "
    "super().validate() then re.match(self.pattern, result). Use "
    "@dataclass decorator. Place after the existing UUIDField class."
)

T2_TITLE = (
    "Step 2 of 3: Re-export RegexField from "
    "pyschema/fields/__init__.py. Add `RegexField` to the import "
    "line `from .strings import EmailField, URLField, UUIDField` "
    "(make it `EmailField, RegexField, URLField, UUIDField`) and "
    "add `'RegexField'` to the `__all__` list (alphabetically)."
)

T3_TITLE = (
    "Step 3 of 3: Re-export RegexField from the top-level "
    "pyschema/__init__.py. Add `RegexField` to the multi-line "
    "import from .fields (alphabetically between `IntField` and "
    "`StrField`) and add `'RegexField'` to the `__all__` list "
    "(alphabetically after 'Pattern')."
)


# Gate-test bodies (pre-written into the workspace, one per task)
T1_GATE = '''"""Gate test for T1 — RegexField class added to strings.py."""
import pytest
from pyschema.fields.strings import RegexField
from pyschema.errors import ValidationError


def test_regex_field_construct_with_pattern():
    f = RegexField(pattern=r"^[a-z]+$")
    assert f.pattern == r"^[a-z]+$"


def test_regex_field_validates_matching():
    f = RegexField(pattern=r"^[a-z]+$")
    assert f.validate("abc") == "abc"


def test_regex_field_rejects_nonmatching():
    f = RegexField(pattern=r"^[a-z]+$")
    with pytest.raises(ValidationError):
        f.validate("ABC")
'''


T2_GATE = '''"""Gate test for T2 — RegexField re-exported from pyschema.fields."""
from pyschema.fields import RegexField


def test_regex_field_in_fields_module():
    rf = RegexField(pattern=r".+")
    assert rf.pattern == r".+"


def test_regex_field_in_fields_all():
    import pyschema.fields
    assert "RegexField" in pyschema.fields.__all__
'''


T3_GATE = '''"""Gate test for T3 — RegexField at top-level pyschema."""
from pyschema import RegexField


def test_regex_field_top_level_import():
    rf = RegexField(pattern=r".+")
    assert rf.pattern == r".+"


def test_regex_field_in_top_level_all():
    import pyschema
    assert "RegexField" in pyschema.__all__
'''


# ---------------------------------------------------------------------------
# Workspace setup
# ---------------------------------------------------------------------------

def setup_workspace() -> Path:
    """Pre-write the full pyschema-extended (no RegexField) plus the
    three gate-test files."""
    ws = Path(tempfile.mkdtemp(prefix="phU_r6m_"))
    shutil.copytree(SCENARIO_DIR / "reference" / "pyschema",
                     ws / "pyschema")
    (ws / "tests").mkdir(exist_ok=True)
    # Hidden tests for final grading
    shutil.copy(SCENARIO_DIR / "tests" / "test_pyschema.py",
                 ws / "tests" / "test_pyschema.py")
    shutil.copy(SCENARIO_DIR / "tests" / "test_regexfield.py",
                 ws / "tests" / "test_regexfield.py")
    # Per-task gate tests (read by loom_exec)
    (ws / "tests" / "test_gate_t1.py").write_text(T1_GATE, encoding="utf-8")
    (ws / "tests" / "test_gate_t2.py").write_text(T2_GATE, encoding="utf-8")
    (ws / "tests" / "test_gate_t3.py").write_text(T3_GATE, encoding="utf-8")
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace",
                    "model": "qwen3.5:latest"}, indent=2),
        encoding="utf-8",
    )
    return ws


# ---------------------------------------------------------------------------
# Loom seeding per cell — three chained tasks
# ---------------------------------------------------------------------------

def seed_loom(cell: str, store) -> tuple[str, str, str]:
    """Seed the parent spec + 3 chained tasks. Returns (T1_id, T2_id, T3_id)."""
    if cell == "D1m":
        # qwen-only: placeholder spec; tasks have no spec linkage
        ph_req = services.extract(
            store, domain="behavior",
            value="placeholder",
            rationale="phU D1m — empty Loom; only task titles drive qwen",
        )
        ph_spec = services.spec_add(
            store, ph_req["req_id"],
            "placeholder — D1m cell, no rule delivered",
        )
        spec_id = ph_spec["spec_id"]
        ctx_reqs: list[str] = []
        ctx_specs: list[str] = []
    else:
        # D2m / D3m: real rule spec stored
        req = services.extract(
            store, domain="behavior",
            value=PARENT_TASK,
            rationale=f"phU {cell} — R6m chained refactor",
        )
        spec = services.spec_add(store, req["req_id"], SPEC_RULE)
        spec_id = spec["spec_id"]
        if cell == "D2m":
            # stored, undelivered
            ctx_reqs = []
            ctx_specs = []
        else:  # D3m — standard delivery
            ctx_reqs = [req["req_id"]]
            ctx_specs = [spec_id]

    # T1 — strings.py
    t1 = services.task_add(
        store, parent_spec=spec_id,
        title=T1_TITLE,
        files_to_modify=["pyschema/fields/strings.py"],
        test_to_write="tests/test_gate_t1.py",
        context_reqs=ctx_reqs, context_specs=ctx_specs,
        context_files=[
            "pyschema/fields/strings.py",
            "pyschema/fields/primitives.py",
            "pyschema/fields/base.py",
            "pyschema/errors.py",
        ],
        depends_on=[], size_budget_files=1, size_budget_loc=120,
        created_by=f"phU_{cell.lower()}_t1",
    )

    # T2 — fields/__init__.py (depends on T1)
    t2 = services.task_add(
        store, parent_spec=spec_id,
        title=T2_TITLE,
        files_to_modify=["pyschema/fields/__init__.py"],
        test_to_write="tests/test_gate_t2.py",
        context_reqs=ctx_reqs, context_specs=ctx_specs,
        context_files=[
            "pyschema/fields/__init__.py",
            "pyschema/fields/strings.py",
        ],
        depends_on=[t1["id"]], size_budget_files=1, size_budget_loc=40,
        created_by=f"phU_{cell.lower()}_t2",
    )

    # T3 — top-level __init__.py (depends on T2)
    t3 = services.task_add(
        store, parent_spec=spec_id,
        title=T3_TITLE,
        files_to_modify=["pyschema/__init__.py"],
        test_to_write="tests/test_gate_t3.py",
        context_reqs=ctx_reqs, context_specs=ctx_specs,
        context_files=[
            "pyschema/__init__.py",
            "pyschema/fields/__init__.py",
        ],
        depends_on=[t2["id"]], size_budget_files=1, size_budget_loc=80,
        created_by=f"phU_{cell.lower()}_t3",
    )

    return t1["id"], t2["id"], t3["id"]


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

def parse_pytest(stdout: str) -> tuple[int, int]:
    p = 0; f = 0; e = 0
    m = re.search(r"(\d+)\s+passed", stdout)
    if m: p = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", stdout)
    if m: f = int(m.group(1))
    m = re.search(r"(\d+)\s+error", stdout)
    if m: e = int(m.group(1))
    return p, p + f + e


def grade_test_file(workspace: Path, test_file: str) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phU_grade_{Path(test_file).stem}_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"tests/{test_file}"],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    p, total = parse_pytest(proc.stdout + proc.stderr)
    return {
        "passed": p, "total": total,
        "stdout_tail": (proc.stdout + proc.stderr)[-1500:],
    }


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    project = f"phU_pyschema_r6m_{cell.lower()}_{run_id}"
    print(f"[setup] cell={cell} workspace={workspace}  project={project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    t1_id, t2_id, t3_id = seed_loom(cell, store)
    print(f"[seed] tasks: T1={t1_id} T2={t2_id} T3={t3_id}")

    store.conn.close()

    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",  # drain the queue
         "--model", os.environ.get("PHU_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=900,
    )
    exec_elapsed = time.time() - t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    # Per-task completion: count "result: {...complete...}" entries
    exec_out = exec_proc.stdout
    tasks_complete = exec_out.count('"outcome": "complete"')
    tasks_test_fail = exec_out.count('"outcome": "test_fail"')

    # Five metrics
    g_acc = grade_test_file(workspace, "test_regexfield.py")
    g_reg = grade_test_file(workspace, "test_pyschema.py")
    idiom_checks = verify_idiom.run_all(workspace)
    wiring_checks = verify_wiring.run_all(workspace)
    idiom_score = verify_idiom.score(idiom_checks)
    wiring_score = verify_wiring.score(wiring_checks)
    import_works = wiring_checks.get("top_level_import_works", False)

    print(f"[grade] tasks_complete={tasks_complete}/3 "
          f"acceptance={g_acc['passed']}/{g_acc['total']} "
          f"regression={g_reg['passed']}/{g_reg['total']}  "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4  "
          f"import={import_works}")

    summary = {
        "phase": "U_pyschema_extended_r6m",
        "cell": cell,
        "run_id": run_id,
        "tasks_complete": tasks_complete,
        "tasks_test_fail": tasks_test_fail,
        "acceptance_passed": g_acc["passed"],
        "acceptance_total": g_acc["total"],
        "acceptance_rate": g_acc["passed"] / g_acc["total"] if g_acc["total"] else 0.0,
        "regression_passed": g_reg["passed"],
        "regression_total": g_reg["total"],
        "regression_rate": g_reg["passed"] / g_reg["total"] if g_reg["total"] else 0.0,
        "idiom_checks": idiom_checks,
        "idiom_score": idiom_score,
        "idiom_total": len(idiom_checks),
        "wiring_checks": wiring_checks,
        "wiring_score": wiring_score,
        "wiring_total": len(wiring_checks),
        "import_works": import_works,
        "exec_rc": exec_proc.returncode,
        "exec_duration_s": round(exec_elapsed, 1),
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-100:]),
        "grade_acceptance_tail": g_acc["stdout_tail"],
        "grade_regression_tail": g_reg["stdout_tail"],
    }
    out_path = OUT_DIR / f"phU_pyschema_r6m_{cell.lower()}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} tasks_complete={tasks_complete}/3 "
          f"acc={g_acc['passed']}/{g_acc['total']} "
          f"reg={g_reg['passed']}/{g_reg['total']} "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4 "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phU_pyschema_extended_r6m_smoke.py <cell> [run_id]")
        print("  cell ∈ D1m, D2m, D3m")
        return 1
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in ("D1m", "D2m", "D3m"):
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
