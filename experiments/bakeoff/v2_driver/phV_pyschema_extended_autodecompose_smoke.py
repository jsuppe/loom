#!/usr/bin/env python3
"""
Phase V — pyschema-extended R6 with AUTO-decomposed tasks.

Tests whether the production claim (`Loom's value is in
decomposition`) holds when `loom decompose` produces the tasks,
not when they're hand-authored.

Probe-pass (`phV_inspect_decompose.py`) confirmed the auto-decomposer
produces structurally-correct chained tasks (3 files, dependency
order right) but with COARSE titles ("Define RegexField in
strings.py" vs R6m's 250-char multi-sentence recipe).

Cells (3, parallel to R6m's D1m/D2m/D3m):
  D1d   auto-tasks with context_reqs/specs cleared (no spec delivery)
  D2d   auto-tasks with context_specs cleared (real spec stored, undelivered)
  D3d   auto-tasks as-is (spec delivered to each task — standard pipeline)

If the auto-decomposer's task titles are too coarse, D1d should
fall well below R6m D1m (which hit 95 %). D3d should still be high
because the spec context compensates.
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

# Per-task gate tests (same as R6m phU)
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


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phV_autodecomp_"))
    shutil.copytree(SCENARIO_DIR / "reference" / "pyschema",
                     ws / "pyschema")
    (ws / "tests").mkdir(exist_ok=True)
    shutil.copy(SCENARIO_DIR / "tests" / "test_pyschema.py",
                 ws / "tests" / "test_pyschema.py")
    shutil.copy(SCENARIO_DIR / "tests" / "test_regexfield.py",
                 ws / "tests" / "test_regexfield.py")
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


def patch_tasks_for_cell(cell: str, store, project: str) -> None:
    """After loom decompose --apply persists tasks, patch them per cell.

    Decomposer output:
      - test_to_write points at a generic test → repoint to the right
        per-task gate test.
      - For D1d: clear context_reqs and context_specs.
      - For D2d: clear context_specs only.
      - For D3d: leave as-is (spec delivered).
    """
    tasks = sorted(store.list_tasks(), key=lambda t: t.timestamp)
    # Map files_to_modify to gate test
    file_to_gate = {
        "pyschema/fields/strings.py": "tests/test_gate_t1.py",
        "pyschema/fields/__init__.py": "tests/test_gate_t2.py",
        "pyschema/__init__.py": "tests/test_gate_t3.py",
    }

    for t in tasks:
        target = t.files_to_modify[0] if t.files_to_modify else ""
        gate = file_to_gate.get(target, t.test_to_write)
        updates = {"test_to_write": gate}
        if cell == "D1d":
            updates["context_reqs"] = []
            updates["context_specs"] = []
        elif cell == "D2d":
            updates["context_specs"] = []
        # D3d: leave context_reqs / context_specs alone
        store.update_task(t.id, updates)


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
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phV_grade_{Path(test_file).stem}_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"tests/{test_file}"],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    p, total = parse_pytest(proc.stdout + proc.stderr)
    return {"passed": p, "total": total,
            "stdout_tail": (proc.stdout + proc.stderr)[-1500:]}


def run_one(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    project = f"phV_autodecomp_{cell.lower()}_{run_id}"
    print(f"[setup] cell={cell} workspace={workspace} project={project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    req = services.extract(
        store, domain="behavior",
        value=TASK,
        rationale=f"phV {cell} — auto-decompose validation",
    )
    spec = services.spec_add(store, req["req_id"], SPEC_RULE)
    print(f"[seed] req={req['req_id']} spec={spec['spec_id']}")
    store.conn.close()

    # Run loom decompose --apply
    decompose_t0 = time.time()
    decompose_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom"),
         "decompose", spec["spec_id"], "--apply",
         "-p", project, "--target-dir", str(workspace)],
        capture_output=True, text=True, timeout=600,
        encoding="utf-8", errors="replace",
    )
    decompose_elapsed = time.time() - decompose_t0
    print(f"[decompose] {decompose_elapsed:.1f}s rc={decompose_proc.returncode}")
    if decompose_proc.returncode != 0:
        print(f"decompose failed: {decompose_proc.stdout[-500:]}\n{decompose_proc.stderr[-500:]}")
        return {"error": "decompose_failed",
                "stdout": decompose_proc.stdout[-500:],
                "stderr": decompose_proc.stderr[-500:]}

    # Patch tasks per cell semantics + repoint test_to_write to gate tests
    store2 = LoomStore(project=project)
    patch_tasks_for_cell(cell, store2, project)
    tasks_after = sorted(store2.list_tasks(), key=lambda t: t.timestamp)
    auto_titles = [t.title for t in tasks_after]
    auto_files = [t.files_to_modify for t in tasks_after]
    auto_deps = [t.depends_on for t in tasks_after]
    print(f"[tasks] {len(tasks_after)} auto-decomposed:")
    for t in tasks_after:
        print(f"  {t.id}  files={t.files_to_modify}  ctx_specs={t.context_specs}  title='{t.title[:80]}'")
    store2.conn.close()

    # Drain queue
    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",
         "--model", os.environ.get("PHV_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=900,
    )
    exec_elapsed = time.time() - t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    tasks_complete = exec_proc.stdout.count('"outcome": "complete"')
    tasks_test_fail = exec_proc.stdout.count('"outcome": "test_fail"')

    # Grade with 5 metrics
    g_acc = grade_test_file(workspace, "test_regexfield.py")
    g_reg = grade_test_file(workspace, "test_pyschema.py")
    idiom_checks = verify_idiom.run_all(workspace)
    wiring_checks = verify_wiring.run_all(workspace)
    idiom_score = verify_idiom.score(idiom_checks)
    wiring_score = verify_wiring.score(wiring_checks)
    import_works = wiring_checks.get("top_level_import_works", False)

    print(f"[grade] tasks_complete={tasks_complete}/3 "
          f"acc={g_acc['passed']}/{g_acc['total']} "
          f"reg={g_reg['passed']}/{g_reg['total']}  "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4 "
          f"import={import_works}")

    summary = {
        "phase": "V_pyschema_extended_autodecompose",
        "cell": cell,
        "run_id": run_id,
        "tasks_complete": tasks_complete,
        "tasks_test_fail": tasks_test_fail,
        "auto_task_titles": auto_titles,
        "auto_task_files": auto_files,
        "auto_task_deps": auto_deps,
        "decompose_elapsed_s": round(decompose_elapsed, 1),
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
    out_path = OUT_DIR / f"phV_autodecomp_{cell.lower()}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} tasks={tasks_complete}/3 acc={g_acc['passed']}/{g_acc['total']} "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4 wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phV_pyschema_extended_autodecompose_smoke.py <cell> [run_id]")
        return 1
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in ("D1d", "D2d", "D3d"):
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
