#!/usr/bin/env python3
"""
Phase T — pyschema-extended R6 ALIGNING refactor smoke.

Tests the production claim: *qwen completes complex multi-file
refactors correctly when given structured spec context, in the
common case where rule and task align (rather than contradict).*

R6 task: add a `RegexField(StrField)` to the existing pyschema-extended
library. Rule and task agree on what to do; the rule provides
structural shape (which file, which base class, which pattern).
This is distinct from R1's contrarian setup — here the question
is whether stored spec context helps qwen produce *idiomatic and
well-wired* code, not whether it overrides task instinct.

Cells (4):
  D0 greenfield      — empty workspace, full 10-task chain build
  D1 qwen-only       — pre-written 10 files, bare task title
  D2 stored-only     — pre-written, Loom seeded, context_specs=[]
  D3 standard        — pre-written, Loom seeded, context_specs=[spec_id]

Five metrics per trial:
  1. acceptance      — RegexField behaves correctly (5 tests)
  2. regression      — existing 38 tests still pass
  3. idiom           — 4 ast-based checks (placement, base, decorator, super-call)
  4. wiring          — 4 cross-file checks (re-exports, __all__, live import)
  5. compile/import  — does the package import after qwen's edit?

N=20 per cell × 4 cells = 80 trials. ~3 hours compute.
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

# Make verifier modules importable
sys.path.insert(0, str(SCENARIO_DIR / "tests"))
import verify_idiom  # noqa: E402
import verify_wiring  # noqa: E402


# ---------------------------------------------------------------------------
# Aligning task + rule (no contradiction — both want the same thing)
# ---------------------------------------------------------------------------

TASK = (
    "Add a RegexField type to pyschema-extended that takes a regex "
    "`pattern: str` and validates that string inputs match the "
    "pattern. RegexField should integrate with the existing Field "
    "hierarchy and be importable as `from pyschema import RegexField` "
    "after the change."
)

RULE = (
    "Constraint for adding RegexField:\n"
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
    "existing dataclass field-ordering rules are not violated."
)


# ---------------------------------------------------------------------------
# Workspace + Loom seeding per cell
# ---------------------------------------------------------------------------

REFACTOR_TARGETS = ["pyschema/fields/strings.py"]


def setup_refactor_workspace() -> Path:
    """Pre-write the full pyschema-extended (no RegexField)."""
    ws = Path(tempfile.mkdtemp(prefix="phT_pyschema_ext_"))
    # Copy reference tree
    shutil.copytree(SCENARIO_DIR / "reference" / "pyschema",
                     ws / "pyschema")
    # Set up tests dir + copy hidden tests for grading
    (ws / "tests").mkdir(exist_ok=True)
    shutil.copy(SCENARIO_DIR / "tests" / "test_pyschema.py",
                 ws / "tests" / "test_pyschema.py")
    shutil.copy(SCENARIO_DIR / "tests" / "test_regexfield.py",
                 ws / "tests" / "test_regexfield.py")
    # conftest so pytest finds the package
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    # Use replace mode so qwen rewrites the whole strings.py
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace",
                    "model": "qwen3.5:latest"}, indent=2),
        encoding="utf-8",
    )
    return ws


def seed_loom(cell: str, store) -> str:
    """Seed Loom for the given cell. Returns task_id."""
    target_file = REFACTOR_TARGETS[0]
    # All cells need a task; D0 is greenfield (different harness path —
    # not implemented in this driver, see note below).

    if cell == "D1":
        # qwen-only: placeholder spec to satisfy task_add API
        ph_req = services.extract(
            store, domain="behavior",
            value="placeholder",
            rationale="phT D1 — empty Loom; task title only",
        )
        ph_spec = services.spec_add(
            store, ph_req["req_id"],
            "placeholder — D1 cell, contents not delivered",
        )
        result = services.task_add(
            store, parent_spec=ph_spec["spec_id"],
            title=TASK, files_to_modify=[target_file],
            test_to_write="tests/test_regexfield.py",
            context_reqs=[], context_specs=[],
            context_files=[
                "pyschema/fields/strings.py",
                "pyschema/fields/primitives.py",
                "pyschema/fields/base.py",
                "pyschema/fields/__init__.py",
                "pyschema/__init__.py",
                "pyschema/errors.py",
            ],
            depends_on=[], size_budget_files=3, size_budget_loc=300,
            created_by="phT_d1",
        )
        return result["id"]

    # D2/D3 — Loom seeded with the rule spec
    req = services.extract(
        store, domain="behavior",
        value=TASK,
        rationale=f"phT {cell} — R6 aligning refactor smoke",
    )
    spec = services.spec_add(store, req["req_id"], RULE)

    if cell == "D2":
        # Stored but not delivered
        ctx_reqs: list[str] = []
        ctx_specs: list[str] = []
    else:  # D3
        ctx_reqs = [req["req_id"]]
        ctx_specs = [spec["spec_id"]]

    result = services.task_add(
        store, parent_spec=spec["spec_id"],
        title=TASK, files_to_modify=[target_file],
        test_to_write="tests/test_regexfield.py",
        context_reqs=ctx_reqs, context_specs=ctx_specs,
        context_files=[
            "pyschema/fields/strings.py",
            "pyschema/fields/primitives.py",
            "pyschema/fields/base.py",
            "pyschema/fields/__init__.py",
            "pyschema/__init__.py",
            "pyschema/errors.py",
        ],
        depends_on=[], size_budget_files=3, size_budget_loc=300,
        created_by=f"phT_{cell.lower()}",
    )
    return result["id"]


# ---------------------------------------------------------------------------
# Grading — run each test suite + idiom + wiring checks
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
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phT_grade_{Path(test_file).stem}_"))
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
    if cell == "D0":
        raise NotImplementedError("D0 greenfield not yet implemented in phT")

    t0 = time.time()
    workspace = setup_refactor_workspace()
    project = f"phT_pyschema_ext_{cell.lower()}_{run_id}"
    print(f"[setup] cell={cell} workspace={workspace}  project={project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    task_id = seed_loom(cell, store)
    print(f"[seed] task_id={task_id}")

    # Close store so subprocess sees a consistent SQLite WAL state
    store.conn.close()

    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next",
         "--model", os.environ.get("PHT_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    exec_elapsed = time.time() - t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    # Five metrics
    g_acc = grade_test_file(workspace, "test_regexfield.py")
    g_reg = grade_test_file(workspace, "test_pyschema.py")
    idiom_checks = verify_idiom.run_all(workspace)
    wiring_checks = verify_wiring.run_all(workspace)

    idiom_score = verify_idiom.score(idiom_checks)
    wiring_score = verify_wiring.score(wiring_checks)

    # Did the package even import? (subset of wiring)
    import_works = wiring_checks.get("top_level_import_works", False)

    print(f"[grade] acceptance={g_acc['passed']}/{g_acc['total']} "
          f"regression={g_reg['passed']}/{g_reg['total']}  "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4  "
          f"import_works={import_works}")

    summary = {
        "phase": "T_pyschema_extended_r6",
        "cell": cell,
        "run_id": run_id,
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
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-60:]),
        "grade_acceptance_tail": g_acc["stdout_tail"],
        "grade_regression_tail": g_reg["stdout_tail"],
    }
    out_path = OUT_DIR / f"phT_pyschema_ext_{cell.lower()}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} acc={g_acc['passed']}/{g_acc['total']} "
          f"reg={g_reg['passed']}/{g_reg['total']} "
          f"idiom={idiom_score}/4 wiring={wiring_score}/4 "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phT_pyschema_extended_r6_smoke.py <cell> [run_id]")
        print("  cell ∈ D1, D2, D3 (D0 greenfield not yet implemented)")
        return 1
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell not in ("D1", "D2", "D3"):
        print(f"unknown or unimplemented cell: {cell}", file=sys.stderr)
        return 1
    run_one(cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
