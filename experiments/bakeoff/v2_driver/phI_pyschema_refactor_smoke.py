#!/usr/bin/env python3
"""
Phase I — pyschema refactor smoke (D smoke).

5-cell harness comparing greenfield vs refactor with varying levels
of Loom assistance. Smoke scope: 1 domain (pyschema), 1 refactor task
(R1: add RegexField), 5 trials per cell.

Cells:
  D0 — greenfield baseline: empty workspace, Loom seeded from the
       README, 5-task chain to build pyschema from scratch. Grades
       against regression suite only.
  D1 — qwen-only refactor: pre-written pyschema (no RegexField) +
       a single task whose title says to add RegexField. No Loom
       seeding. Bare prompt + existing file context.
  D2 — Loom seeded, delivery suppressed: same as D3 but the task is
       created with context_specs=[] so the spec is in the store
       but not injected into the executor's prompt.
  D3 — Loom seeded + standard delivery: refactor spec authored by
       Opus, stored, linked to the task via context_specs. Standard
       Loom pipeline.

Grading:
  D0     → regression test suite (test_pyschema.py, 26 tests)
  D1-D3  → regression + acceptance (test_pyschema.py + test_regexfield.py)
           Both rates reported separately so we can distinguish
           "broke existing behavior" from "didn't add new behavior."

Default executor: qwen3.5:latest. Override via PHI_EXEC_MODEL.
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
from typing import Any

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "pyschema" / "ground_truth"
REFERENCE_DIR = BENCHMARK_DIR / "reference" / "pyschema"
TESTS_DIR = BENCHMARK_DIR / "tests"
README = BENCHMARK_DIR / "README.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa: E402
from loom import services  # noqa: E402


# ---------------------------------------------------------------------------
# Greenfield (D0) — 5-task chain over the pyschema source files
# ---------------------------------------------------------------------------

GREENFIELD_TARGETS = [
    "pyschema/errors.py",
    "pyschema/coercion.py",
    "pyschema/validators.py",
    "pyschema/field.py",
    "pyschema/schema.py",
]
BARREL_PATH = "pyschema/__init__.py"
BARREL_CHAIN = '"""pyschema — populated at grading time."""\n'
BARREL_FULL = (REFERENCE_DIR / "__init__.py").read_text(encoding="utf-8")

# Lightweight per-task gating tests. Each verifies the basic public symbol.
GATING_TESTS_GREENFIELD = {
    "pyschema/errors.py": '''
from pyschema.errors import SchemaError, ValidationError, CoercionError, SchemaDefinitionError
def test_error_hierarchy():
    assert issubclass(ValidationError, SchemaError)
    assert issubclass(CoercionError, SchemaError)
    assert issubclass(SchemaDefinitionError, SchemaError)
''',
    "pyschema/coercion.py": '''
import pytest
from pyschema.coercion import coerce_int, coerce_str, coerce_bool
from pyschema.errors import CoercionError
def test_coerce_int_accepts_int(): assert coerce_int(42) == 42
def test_coerce_int_refuses_bool():
    with pytest.raises(CoercionError):
        coerce_int(True)
def test_coerce_str_int(): assert coerce_str(42) == "42"
def test_coerce_bool_yes(): assert coerce_bool("yes") is True
''',
    "pyschema/validators.py": '''
import pytest
from pyschema.validators import MinLength, MaxLength, MinValue, MaxValue, Choice
from pyschema.errors import ValidationError
def test_min_length():
    with pytest.raises(ValidationError):
        MinLength(3).check("ab")
def test_choice_in():
    Choice(["a", "b"]).check("a")
def test_choice_out():
    with pytest.raises(ValidationError):
        Choice(["a", "b"]).check("c")
''',
    "pyschema/field.py": '''
import pytest
from pyschema.field import IntField, StrField, BoolField, EmailField
from pyschema.errors import ValidationError
def test_int_field(): assert IntField().validate(42) == 42
def test_str_field(): assert StrField().validate("x") == "x"
def test_bool_field(): assert BoolField().validate(True) is True
def test_email_field_valid(): assert EmailField().validate("a@x.com") == "a@x.com"
def test_email_field_invalid():
    with pytest.raises(ValidationError):
        EmailField().validate("noat")
''',
    "pyschema/schema.py": '''
from pyschema.schema import Schema
from pyschema.field import StrField, IntField
from pyschema.errors import SchemaDefinitionError
import pytest
def test_schema_validates():
    class S(Schema):
        name = StrField()
        age = IntField()
    out = S().validate({"name": "A", "age": 1})
    assert out == {"name": "A", "age": 1}
def test_empty_schema_raises():
    class E(Schema): pass
    with pytest.raises(SchemaDefinitionError):
        E()
''',
}

GATING_TEST_TARGETS_GREENFIELD = {
    tf: f"tests/test_gate_{tf.replace('/', '_').replace('.py', '')}.py"
    for tf in GREENFIELD_TARGETS
}

PLANNER_SYSTEM = """\
You are a senior Python architect writing an implementation specification
for a small declarative validation library called `pyschema`. The
downstream executor is a small local model (qwen3.5, 9.7B parameters)
that will write each file in a single replace-mode pass. Your spec
must be self-contained and explicit about which symbols live in which
file.

The library is split across 5 implementation files (the barrel
pyschema/__init__.py re-exporting these is pre-written by the harness;
do NOT include a section for it):

  pyschema/errors.py        — SchemaError + ValidationError + CoercionError + SchemaDefinitionError
  pyschema/coercion.py      — coerce_int / coerce_str / coerce_bool
  pyschema/validators.py    — MinLength, MaxLength, MinValue, MaxValue, Choice
  pyschema/field.py         — Field base + IntField + StrField + BoolField + EmailField
  pyschema/schema.py        — Schema class

Cross-file commitments to fix early in the spec:
  - All errors derive from SchemaError(Exception).
  - ValidationError carries .message: str and .field: str (default "").
  - coerce_int REFUSES bool (raises CoercionError on True/False).
  - Field is a @dataclass with required: bool=True, default: Any=None,
    validators: List[Any] (default_factory=list).
  - Field.validate(value) is the entry point: None+required raises
    ValidationError, None+optional returns default; otherwise coerce
    then run all validators.
  - StrField/IntField __post_init__ append MinValue/MaxValue/MinLength/
    MaxLength validators when set.
  - EmailField inherits StrField; validate() runs super then matches
    against r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" and raises ValidationError
    on mismatch.
  - Schema discovers Field instances via dir(type(self)). Empty
    Schema (no fields) raises SchemaDefinitionError.
  - Schema.validate attaches the field name to any ValidationError
    raised by an underlying field.
  - Schema.fields property returns a COPY of the internal dict.

CONTRACT BLOCKS — each `### pyschema/<path>.py` section MUST end with a
```python-contract
…
```
fenced block containing declaration-only Python code: every public
class, dataclass field, method signature, property, and exception
class that the executor must produce, with full signatures and types
but no method bodies (use `...` or `raise NotImplementedError`).

The contract block is the BINDING for the executor — every named
parameter, field, method signature, and property in the contract
becomes a hard commitment.

Output the spec as raw markdown — do not wrap the whole response in
any outer fenced block. Organize as 5 sections each labeled exactly
`### pyschema/<path>.py` in the listed order. Each section has the
prose description followed by its `python-contract` fenced code
block. The inner `python-contract` blocks must be the ONLY fenced
code blocks in the output, since 3-backtick fences cannot nest.
"""

REFACTOR_PLANNER_SYSTEM = """\
You are a senior Python architect authoring a REFACTOR specification.
A small local executor (qwen3.5) needs to apply a specific change to
an existing Python library. Your job is to write the change spec —
exactly which files to modify and what the public surface should look
like after the change.

The change: add a new `RegexField` type to `pyschema/field.py`.
RegexField:
  - Inherits from StrField (so it gets length validators and str
    coercion).
  - Adds a single `pattern: str` attribute. IMPORTANT: in a Python
    @dataclass, fields with defaults must come AFTER fields without
    defaults — but `Field` (the parent) declares `required: bool=True`,
    `default: Any=None`, `validators: List[Any]=...` (all defaulted),
    and StrField adds `min_length: Optional[int]=None`,
    `max_length: Optional[int]=None`. The new `pattern: str` field
    therefore MUST also have a default value to keep dataclass
    construction valid (use `pattern: str = ""` or similar).
  - Overrides `validate(value)` to apply the parent's check, then
    reject any value that does not match the pattern using `re.match`.

The acceptance test imports `from pyschema.field import RegexField`
directly. You only need to modify `pyschema/field.py`. Do NOT
include sections for files that are not modified.

Write the spec as raw markdown — do NOT wrap in any outer fenced
block. Each section MUST end with a `python-contract` fenced code
block showing the new (post-refactor) public surface for that file.
The python-contract blocks must be the ONLY fenced code blocks in
the output.

Be concrete: every named class/method signature in the contract
becomes a hard commitment.
"""


# ---------------------------------------------------------------------------
# Refactor (D1-D3) — single task that adds RegexField
# ---------------------------------------------------------------------------

REFACTOR_TARGETS = [
    "pyschema/field.py",
    "pyschema/__init__.py",
]

REFACTOR_TASK_TITLE = (
    "Add a RegexField type to pyschema/field.py. "
    "RegexField inherits from StrField, takes a `pattern: str`, and "
    "overrides validate() to additionally check that the value matches "
    "the pattern via re.match (raising ValidationError on mismatch). "
    "Modify only pyschema/field.py — the test imports directly from "
    "pyschema.field so __init__.py changes are out of scope for this task."
)


# ---------------------------------------------------------------------------
# Common utilities
# ---------------------------------------------------------------------------

def call_opus(prompt: str, system: str, model: str = "opus") -> dict:
    args = [
        "claude", "-p",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", system,
    ]
    t0 = time.time()
    proc = subprocess.run(
        args, input=prompt,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p rc={proc.returncode}\n"
                           f"stderr: {proc.stderr[-500:]}")
    data = json.loads(proc.stdout)
    return {
        "content": data.get("result", ""),
        "duration_ms": data.get("duration_ms", int(elapsed * 1000)),
        "cost_usd": data.get("total_cost_usd") or data.get("cost_usd", 0),
    }


def extract_spec(opus_response: str) -> str:
    text = opus_response.strip()
    m = re.match(r"^```(?:text|markdown)\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def split_spec_by_file(spec_text: str, targets: list[str]) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"^### (pyschema/\S+\.py)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(spec_text))
    if not matches:
        return {f: spec_text for f in targets}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        sections[m.group(1)] = spec_text[start:end].strip()
    for f in targets:
        sections.setdefault(f, spec_text)
    return sections


def extract_python_contracts(spec_text: str) -> dict[str, str]:
    contracts: dict[str, str] = {}
    pattern = re.compile(r"^### (pyschema/\S+\.py)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(spec_text))
    fence_re = re.compile(r"```python-contract\s*\n(.*?)\n```", re.DOTALL)
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        section = spec_text[start:end]
        cm = fence_re.search(section)
        if cm:
            contracts[m.group(1)] = cm.group(1).rstrip()
    return contracts


def parse_pytest(stdout: str) -> tuple[int, int]:
    p = 0
    f = 0
    e = 0
    m = re.search(r"(\d+)\s+passed", stdout)
    if m: p = int(m.group(1))
    m_fail = re.search(r"(\d+)\s+failed", stdout)
    if m_fail: f = int(m_fail.group(1))
    m_err = re.search(r"(\d+)\s+error", stdout)
    if m_err: e = int(m_err.group(1))
    return p, p + f + e


def grade_test_file(workspace: Path, test_file: str) -> dict:
    """Run a single hidden test file. Returns {passed, total, stdout_tail}."""
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phI_grade_{Path(test_file).stem}_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    (grade_dir / "tests").mkdir(exist_ok=True)
    shutil.copy(TESTS_DIR / test_file, grade_dir / "tests" / test_file)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", f"tests/{test_file}"],
        cwd=grade_dir, capture_output=True, text=True, timeout=120,
        encoding="utf-8", errors="replace",
    )
    p, total = parse_pytest(proc.stdout + proc.stderr)
    return {
        "passed": p, "total": total,
        "pass_rate": p / total if total else 0.0,
        "stdout_tail": (proc.stdout + proc.stderr)[-2000:],
        "grade_dir": str(grade_dir),
    }


# ---------------------------------------------------------------------------
# D0 — greenfield workspace + 5-task chain
# ---------------------------------------------------------------------------

def setup_greenfield_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phI_pyschema_d0_"))
    (ws / "pyschema").mkdir()
    (ws / "tests").mkdir()
    # Replace mode for greenfield too: qwen outputs the whole file
    # content per task, mirroring how D1-D4 (refactor) works. Append
    # mode silently omits imports/setup that qwen "expected" to be
    # already present from prior tasks.
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace", "model": "qwen3.5:latest"},
                   indent=2),
        encoding="utf-8",
    )
    for tf in GREENFIELD_TARGETS:
        (ws / tf).write_text("", encoding="utf-8")
    (ws / BARREL_PATH).write_text(BARREL_CHAIN, encoding="utf-8")
    for tf, gate_path in GATING_TEST_TARGETS_GREENFIELD.items():
        (ws / gate_path).write_text(GATING_TESTS_GREENFIELD[tf], encoding="utf-8")
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    return ws


def seed_loom_greenfield(store, spec_text: str) -> tuple[dict, list[str]]:
    """Seed the build spec for D0. Returns (req, [task_ids])."""
    req = services.extract(
        store, domain="behavior",
        value="Implement the pyschema declarative validation library.",
        rationale="D0 greenfield baseline — verifies python-inventory-shape pattern "
                  "replicates on a different domain (validation library).",
    )
    spec = services.spec_add(store, req["req_id"], spec_text)
    task_ids: list[str] = []
    for i, tf in enumerate(GREENFIELD_TARGETS):
        depends = [task_ids[i - 1]] if task_ids else []
        result = services.task_add(
            store,
            parent_spec=spec["spec_id"],
            title=f"Implement {tf} per the section labeled `### {tf}` in the spec",
            files_to_modify=[tf],
            test_to_write=GATING_TEST_TARGETS_GREENFIELD[tf],
            context_reqs=[req["req_id"]],
            context_specs=[spec["spec_id"]],
            context_files=[tf],
            depends_on=depends,
            size_budget_files=1,
            size_budget_loc=200,
            created_by="phI_pyschema_d0",
        )
        task_ids.append(result["id"])
    return req, task_ids


# ---------------------------------------------------------------------------
# D1-D3 — refactor workspace + single task
# ---------------------------------------------------------------------------

def setup_refactor_workspace() -> Path:
    """Pre-write the pyschema reference files (no RegexField).

    Also pre-writes the acceptance test (test_regexfield.py) so that
    loom_exec's per-task gate test points at a real file. The test
    will fail until qwen actually adds RegexField — which is the
    refactor's success criterion.
    """
    ws = Path(tempfile.mkdtemp(prefix="phI_pyschema_d14_"))
    (ws / "pyschema").mkdir()
    (ws / "tests").mkdir()
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace", "model": "qwen3.5:latest"},
                   indent=2),
        encoding="utf-8",
    )
    # Copy reference files (pre-refactor state).
    for ref_file in REFERENCE_DIR.iterdir():
        if ref_file.is_file() and ref_file.suffix == ".py":
            shutil.copy(ref_file, ws / "pyschema" / ref_file.name)
    # Pre-write the acceptance test so loom_exec's gate runs it.
    shutil.copy(TESTS_DIR / "test_regexfield.py",
                ws / "tests" / "test_regexfield.py")
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    return ws


def seed_loom_refactor(cell: str, store, refactor_spec_text: str) -> tuple[Any, str]:
    """Seed Loom for D2/D3. D1 returns (None, "") since no seeding.

    Returns (req_obj, task_id).
    """
    if cell == "D1":
        # qwen-only: minimal placeholder req+spec to satisfy task_add
        # API, but the task does NOT link them — executor sees only
        # the task title + file context, no spec injection.
        ph_req = services.extract(
            store, domain="behavior",
            value="placeholder",
            rationale="phI D1 — empty-Loom cell, contents intentionally not "
                      "delivered to executor.",
        )
        ph_spec = services.spec_add(
            store, ph_req["req_id"],
            "placeholder — D1 cell, contents not delivered to executor",
        )
        result = services.task_add(
            store,
            parent_spec=ph_spec["spec_id"],
            title=REFACTOR_TASK_TITLE,
            files_to_modify=["pyschema/field.py"],
            test_to_write="tests/test_regexfield.py",
            context_reqs=[],          # suppress req delivery
            context_specs=[],         # suppress spec delivery
            context_files=["pyschema/field.py", "pyschema/__init__.py"],
            depends_on=[],
            size_budget_files=2,
            size_budget_loc=200,
            created_by="phI_pyschema_d1",
        )
        return None, result["id"]

    # D2/D3: seed req + spec.
    req = services.extract(
        store, domain="behavior",
        value=REFACTOR_TASK_TITLE,
        rationale=f"phI {cell} — refactor spec for adding RegexField.",
    )
    spec = services.spec_add(store, req["req_id"], refactor_spec_text)

    # D2 suppresses delivery: spec is in store but task does NOT link it.
    if cell == "D2":
        ctx_reqs: list[str] = []
        ctx_specs: list[str] = []
    else:  # D3
        ctx_reqs = [req["req_id"]]
        ctx_specs = [spec["spec_id"]]

    # parent_spec must exist; D2 still uses the seeded spec_id even
    # though context_specs is empty (parent_spec is bookkeeping; only
    # context_specs drives prompt assembly via task_build_prompt).
    parent_spec = spec["spec_id"]

    result = services.task_add(
        store,
        parent_spec=parent_spec,
        title=REFACTOR_TASK_TITLE,
        files_to_modify=["pyschema/field.py"],
        test_to_write="tests/test_regexfield.py",
        context_reqs=ctx_reqs,
        context_specs=ctx_specs,
        context_files=["pyschema/field.py", "pyschema/__init__.py"],
        depends_on=[],
        size_budget_files=2,
        size_budget_loc=200,
        created_by=f"phI_pyschema_{cell.lower()}",
    )
    return req, result["id"]


# ---------------------------------------------------------------------------
# Per-cell top-level run
# ---------------------------------------------------------------------------

def run_d0(run_id: str) -> dict:
    """D0 greenfield: replicate python-inventory-shape on pyschema."""
    t0 = time.time()
    workspace = setup_greenfield_workspace()
    project = f"phI_pyschema_d0_{run_id}"
    print(f"[setup] D0 workspace: {workspace}  project: {project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    # Step 1: Opus authors build spec.
    readme = README.read_text(encoding="utf-8")
    planner_prompt = (
        f"Below is a benchmark README for a 5-file Python validation "
        f"library called `pyschema`. Write a complete implementation "
        f"spec, organized as 5 `### pyschema/...py` sections. Each "
        f"section MUST end with a ```python-contract``` fenced block "
        f"per the system instructions. Output raw markdown — no outer "
        f"wrap.\n\n---README---\n{readme}\n---END README---"
    )
    opus_t0 = time.time()
    opus_resp = call_opus(planner_prompt, PLANNER_SYSTEM)
    opus_elapsed = time.time() - opus_t0

    spec_text = extract_spec(opus_resp["content"])
    sections = split_spec_by_file(spec_text, GREENFIELD_TARGETS)
    contracts = extract_python_contracts(spec_text)
    print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_resp['cost_usd']:.4f}  "
          f"spec_chars={len(spec_text)}  contracts={len(contracts)}/{len(GREENFIELD_TARGETS)}")

    req, task_ids = seed_loom_greenfield(store, spec_text)

    # Step 3: loom_exec drains queue.
    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",
         "--model", os.environ.get("PHI_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=1800,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    # Step 4: grade. Swap in full barrel before running tests.
    (workspace / BARREL_PATH).write_text(BARREL_FULL, encoding="utf-8")
    g_reg = grade_test_file(workspace, "test_pyschema.py")
    print(f"[grade] regression={g_reg['passed']}/{g_reg['total']}")

    summary = {
        "phase": "I_pyschema_d0_greenfield",
        "cell": "D0",
        "run_id": run_id,
        "regression_passed": g_reg["passed"],
        "regression_total": g_reg["total"],
        "regression_rate": g_reg["pass_rate"],
        "acceptance_passed": None,
        "acceptance_total": None,
        "spec_chars": len(spec_text),
        "contracts_initial": len(contracts),
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_resp["cost_usd"],
        "exec_duration_s": round(exec_elapsed, 1),
        "exec_rc": exec_proc.returncode,
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-80:]),
        "grade_regression_tail": g_reg["stdout_tail"],
    }
    out_path = OUT_DIR / f"phI_pyschema_d0_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: D0 reg={g_reg['passed']}/{g_reg['total']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def run_d_refactor(cell: str, run_id: str) -> dict:
    """D1/D2/D3 refactor cells."""
    t0 = time.time()
    workspace = setup_refactor_workspace()
    project = f"phI_pyschema_{cell.lower()}_{run_id}"
    print(f"[setup] {cell} workspace: {workspace}  project: {project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    # Step 1: For D2/D3, Opus authors a refactor spec.
    spec_text = ""
    contracts: dict[str, str] = {}
    opus_elapsed = 0.0
    opus_cost = 0.0
    if cell in ("D2", "D3"):
        existing_code = []
        for ref_file in sorted(REFERENCE_DIR.iterdir()):
            if ref_file.is_file() and ref_file.suffix == ".py":
                rel = f"pyschema/{ref_file.name}"
                existing_code.append(f"### {rel} (current contents)\n```python\n"
                                      f"{ref_file.read_text(encoding='utf-8')}\n```")
        existing_listing = "\n\n".join(existing_code)
        refactor_prompt = (
            f"The change to apply: add a `RegexField` type to pyschema. "
            f"RegexField inherits from StrField, takes a `pattern: str`, "
            f"and overrides validate() to additionally check that the "
            f"value matches the pattern via re.match (raise "
            f"ValidationError on mismatch). Export RegexField from "
            f"pyschema/__init__.py and list it in __all__.\n\n"
            f"Below is the current state of the library. Author a "
            f"refactor specification organized as `### pyschema/<file>.py` "
            f"sections covering only the files that change. Each section "
            f"MUST end with a ```python-contract``` fenced block showing "
            f"the new (post-refactor) public surface for that file. "
            f"Output raw markdown — no outer wrap.\n\n"
            f"---EXISTING---\n{existing_listing}\n---END EXISTING---"
        )
        opus_t0 = time.time()
        opus_resp = call_opus(refactor_prompt, REFACTOR_PLANNER_SYSTEM)
        opus_elapsed = time.time() - opus_t0
        spec_text = extract_spec(opus_resp["content"])
        contracts = extract_python_contracts(spec_text)
        opus_cost = opus_resp["cost_usd"]
        print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_cost:.4f}  "
              f"refactor_spec_chars={len(spec_text)}  contracts={len(contracts)}")

    # Step 2: Seed Loom per cell.
    req, task_id = seed_loom_refactor(cell, store, spec_text)
    print(f"[seed] cell={cell} task_id={task_id} "
          f"loom_seeded={cell != 'D1'} delivery={cell not in ('D1','D2')}")

    # Step 3: loom_exec.
    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next",  # single task, no --loop needed
         "--model", os.environ.get("PHI_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    # Step 4: grade both suites separately.
    g_reg = grade_test_file(workspace, "test_pyschema.py")
    g_acc = grade_test_file(workspace, "test_regexfield.py")
    print(f"[grade] regression={g_reg['passed']}/{g_reg['total']}  "
          f"acceptance={g_acc['passed']}/{g_acc['total']}")

    summary = {
        "phase": f"I_pyschema_{cell.lower()}_refactor",
        "cell": cell,
        "run_id": run_id,
        "regression_passed": g_reg["passed"],
        "regression_total": g_reg["total"],
        "regression_rate": g_reg["pass_rate"],
        "acceptance_passed": g_acc["passed"],
        "acceptance_total": g_acc["total"],
        "acceptance_rate": g_acc["pass_rate"],
        "spec_chars": len(spec_text),
        "contracts_initial": len(contracts),
        "loom_seeded": cell != "D1",
        "spec_delivered": cell not in ("D1", "D2"),
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_cost,
        "exec_duration_s": round(exec_elapsed, 1),
        "exec_rc": exec_proc.returncode,
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-80:]),
        "grade_regression_tail": g_reg["stdout_tail"],
        "grade_acceptance_tail": g_acc["stdout_tail"],
    }
    out_path = OUT_DIR / f"phI_pyschema_{cell.lower()}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} reg={g_reg['passed']}/{g_reg['total']}  "
          f"acc={g_acc['passed']}/{g_acc['total']}  "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phI_pyschema_refactor_smoke.py <cell> [run_id]")
        print("  cell ∈ D0, D1, D2, D3")
        return 1
    cell = argv[1]
    run_id = argv[2] if len(argv) > 2 else "smoke"
    if cell == "D0":
        run_d0(run_id)
    elif cell in ("D1", "D2", "D3"):
        run_d_refactor(cell, run_id)
    else:
        print(f"unknown cell: {cell}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
