#!/usr/bin/env python3
"""
Phase J — pubsub refactor smoke (R2 = rename Bus.subscribe → Bus.register_handler).

5-cell harness mirroring phI_pyschema_refactor_smoke.py but targeting
a different refactor type (signature_mismatch / rename) on a different
domain (pub/sub messaging). Tests whether the D2 vs D3 +95pp lift
observed on R1 generalizes to a different refactor shape.

Cells:
  D0 — greenfield baseline: empty workspace, build pubsub from scratch
       using the new method name (register_handler).
  D1 — qwen-only refactor: pre-written pubsub (with subscribe) +
       a single task title to rename. No Loom seeding.
  D2 — Loom seeded, delivery suppressed (context_specs=[]).
  D3 — Loom seeded + standard delivery.

Grading: single hidden test suite (test_pubsub.py). Pre-refactor:
1/12 (only the topic-not-found test passes). Post-refactor: 12/12.
There is no separate "regression" suite — a pure rename eliminates
the old method, so old-name tests would fail by design.
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
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "pubsub" / "ground_truth"
REFERENCE_DIR = BENCHMARK_DIR / "reference" / "pubsub"
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
# Greenfield (D0)
# ---------------------------------------------------------------------------

GREENFIELD_TARGETS = [
    "pubsub/errors.py",
    "pubsub/topic.py",
    "pubsub/subscription.py",
    "pubsub/bus.py",
]
BARREL_PATH = "pubsub/__init__.py"
BARREL_CHAIN = '"""pubsub — populated at grading time."""\n'
BARREL_FULL = (REFERENCE_DIR / "__init__.py").read_text(encoding="utf-8")

GATING_TESTS_GREENFIELD = {
    "pubsub/errors.py": '''
from pubsub.errors import PubSubError, TopicNotFoundError, SubscriptionClosedError, HandlerError
def test_error_hierarchy():
    assert issubclass(TopicNotFoundError, PubSubError)
    assert issubclass(SubscriptionClosedError, PubSubError)
    assert issubclass(HandlerError, PubSubError)
def test_handler_error_carries_cause():
    e = HandlerError("x", cause=ValueError("inner"))
    assert isinstance(e.cause, ValueError)
''',
    "pubsub/topic.py": '''
import pytest
from pubsub.topic import Topic
def test_topic_create():
    t = Topic(name="orders")
    assert t.name == "orders"
def test_topic_empty_name_raises():
    with pytest.raises(ValueError):
        Topic(name="")
def test_topic_hashable():
    s = {Topic(name="a"), Topic(name="a"), Topic(name="b")}
    assert len(s) == 2
''',
    "pubsub/subscription.py": '''
from pubsub.subscription import Subscription
def test_subscription_construct():
    s = Subscription(id="sub-1", topic_name="orders", handler=lambda e: None)
    assert not s.closed
def test_subscription_close():
    s = Subscription(id="sub-1", topic_name="orders", handler=lambda e: None)
    s.close()
    assert s.closed
''',
    "pubsub/bus.py": '''
from pubsub.bus import Bus
from pubsub.topic import Topic
def test_bus_register_handler_returns_subscription():
    bus = Bus()
    sub = bus.register_handler("topic", lambda e: None)
    assert sub.topic_name == "topic"
def test_bus_publish_delivers():
    bus = Bus()
    seen = []
    bus.register_handler("topic", lambda e: seen.append(e))
    bus.publish("topic", "evt")
    assert seen == ["evt"]
''',
}

GATING_TEST_TARGETS_GREENFIELD = {
    tf: f"tests/test_gate_{tf.replace('/', '_').replace('.py', '')}.py"
    for tf in GREENFIELD_TARGETS
}

PLANNER_SYSTEM = """\
You are a senior Python architect writing an implementation
specification for a small in-memory pub/sub library called `pubsub`.
The downstream executor is a small local model (qwen3.5, 9.7B
parameters) that will write each file in a single replace-mode pass.

The library is split across 4 implementation files (the barrel
pubsub/__init__.py is pre-written; do NOT include a section for it):

  pubsub/errors.py        — PubSubError hierarchy
  pubsub/topic.py         — Topic value type
  pubsub/subscription.py  — Subscription token
  pubsub/bus.py           — Bus class (registration + dispatch)

Cross-file commitments:
  - All errors derive from PubSubError(Exception). Subclasses:
    TopicNotFoundError, SubscriptionClosedError, HandlerError.
    HandlerError additionally holds a .cause attribute (Optional[Exception]).
  - Topic is @dataclass(frozen=True) with name: str. Validates
    name is non-empty in __post_init__.
  - Subscription is @dataclass with id, topic_name, handler fields
    plus _closed flag. close() method, .closed property.
  - Bus class: register_topic(name), topics(), register_handler(topic, handler),
    unsubscribe(sub), publish(topic, event).
    register_handler is the public method name (we are using the
    new naming convention). publish raises TopicNotFoundError on
    unknown topic and HandlerError if any handler raises (delivering
    to remaining handlers first).

CONTRACT BLOCKS — each `### pubsub/<path>.py` section MUST end with a
```python-contract
…
```
fenced block containing declaration-only Python code: every public
class, dataclass field, method signature, property, and exception
class with full signatures and types but no bodies (use `...`).

Output the spec as raw markdown — do NOT wrap in any outer fenced
block. Organize as 4 sections each labeled exactly
`### pubsub/<path>.py` in the listed order. The python-contract
fences must be the ONLY fenced code blocks in the output.
"""

REFACTOR_PLANNER_SYSTEM = """\
You are a senior Python architect authoring a REFACTOR specification.
A small local executor (qwen3.5) needs to apply a specific renaming
change to an existing Python library.

The change: in `pubsub/bus.py`, rename the public method
`Bus.subscribe(topic, handler) -> Subscription` to
`Bus.register_handler(topic, handler) -> Subscription`.

CRITICAL constraints:
  - This is a PURE RENAME. The signature, return type, and behavior
    are identical — only the method name changes.
  - The old name `subscribe` MUST NOT exist after the refactor.
    Do not add it as a deprecated alias. The acceptance test
    explicitly checks `not hasattr(bus, "subscribe")`.
  - File scope: `pubsub/bus.py` only. The other library files do
    not change.

The acceptance test imports `from pubsub.bus import Bus` directly
and calls `bus.register_handler(...)`. There are no `__init__.py`
re-exports to update; only bus.py.

Write the spec as raw markdown — do NOT wrap in any outer fenced
block. The spec should focus only on `pubsub/bus.py`. The section
MUST end with a `python-contract` fenced code block showing the
post-refactor public surface of Bus (every public method with full
signature). The python-contract block must be the ONLY fenced code
block in the output.

Be concrete: the contract becomes a hard commitment.
"""


# ---------------------------------------------------------------------------
# Refactor (D1-D3)
# ---------------------------------------------------------------------------

REFACTOR_TARGETS = ["pubsub/bus.py"]

REFACTOR_TASK_TITLE = (
    "Rename Bus.subscribe to Bus.register_handler in pubsub/bus.py. "
    "This is a pure rename — the signature, return type, and behavior "
    "are identical, only the method name changes. The old name "
    "`subscribe` must NOT exist after the refactor (no deprecated alias). "
    "Modify only pubsub/bus.py."
)


# ---------------------------------------------------------------------------
# Common utilities (lifted from phI)
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
    pattern = re.compile(r"^### (pubsub/\S+\.py)\s*$", re.MULTILINE)
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
    pattern = re.compile(r"^### (pubsub/\S+\.py)\s*$", re.MULTILINE)
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
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phJ_grade_{Path(test_file).stem}_"))
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
# D0 — greenfield
# ---------------------------------------------------------------------------

def setup_greenfield_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phJ_pubsub_d0_"))
    (ws / "pubsub").mkdir()
    (ws / "tests").mkdir()
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
    req = services.extract(
        store, domain="behavior",
        value="Implement the pubsub in-memory pub/sub library.",
        rationale="phJ R2 D0 greenfield baseline — replicates pyschema D0 "
                  "pattern on a different domain (messaging).",
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
            created_by="phJ_pubsub_d0",
        )
        task_ids.append(result["id"])
    return req, task_ids


# ---------------------------------------------------------------------------
# D1-D3 — refactor
# ---------------------------------------------------------------------------

def setup_refactor_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phJ_pubsub_d14_"))
    (ws / "pubsub").mkdir()
    (ws / "tests").mkdir()
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace", "model": "qwen3.5:latest"},
                   indent=2),
        encoding="utf-8",
    )
    for ref_file in REFERENCE_DIR.iterdir():
        if ref_file.is_file() and ref_file.suffix == ".py":
            shutil.copy(ref_file, ws / "pubsub" / ref_file.name)
    shutil.copy(TESTS_DIR / "test_pubsub.py",
                ws / "tests" / "test_pubsub.py")
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    return ws


def seed_loom_refactor(cell: str, store, refactor_spec_text: str) -> tuple[Any, str]:
    if cell == "D1":
        ph_req = services.extract(
            store, domain="behavior",
            value="placeholder",
            rationale="phJ R2 D1 — empty-Loom cell, contents not delivered "
                      "to executor.",
        )
        ph_spec = services.spec_add(
            store, ph_req["req_id"],
            "placeholder — D1 cell, contents not delivered to executor",
        )
        result = services.task_add(
            store,
            parent_spec=ph_spec["spec_id"],
            title=REFACTOR_TASK_TITLE,
            files_to_modify=["pubsub/bus.py"],
            test_to_write="tests/test_pubsub.py",
            context_reqs=[],
            context_specs=[],
            context_files=["pubsub/bus.py"],
            depends_on=[],
            size_budget_files=1,
            size_budget_loc=200,
            created_by="phJ_pubsub_d1",
        )
        return None, result["id"]

    req = services.extract(
        store, domain="behavior",
        value=REFACTOR_TASK_TITLE,
        rationale=f"phJ R2 {cell} — refactor spec for renaming Bus.subscribe.",
    )
    spec = services.spec_add(store, req["req_id"], refactor_spec_text)

    if cell == "D2":
        ctx_reqs: list[str] = []
        ctx_specs: list[str] = []
    else:
        ctx_reqs = [req["req_id"]]
        ctx_specs = [spec["spec_id"]]

    parent_spec = spec["spec_id"]
    result = services.task_add(
        store,
        parent_spec=parent_spec,
        title=REFACTOR_TASK_TITLE,
        files_to_modify=["pubsub/bus.py"],
        test_to_write="tests/test_pubsub.py",
        context_reqs=ctx_reqs,
        context_specs=ctx_specs,
        context_files=["pubsub/bus.py"],
        depends_on=[],
        size_budget_files=1,
        size_budget_loc=200,
        created_by=f"phJ_pubsub_{cell.lower()}",
    )
    return req, result["id"]


# ---------------------------------------------------------------------------
# Per-cell run
# ---------------------------------------------------------------------------

def run_d0(run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_greenfield_workspace()
    project = f"phJ_pubsub_d0_{run_id}"
    print(f"[setup] D0 workspace: {workspace}  project: {project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    readme = README.read_text(encoding="utf-8")
    planner_prompt = (
        f"Below is a benchmark README for a 4-file Python pub/sub "
        f"library called `pubsub`. Write a complete implementation "
        f"spec, organized as 4 `### pubsub/...py` sections. Each "
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

    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",
         "--model", os.environ.get("PHJ_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=1800,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    (workspace / BARREL_PATH).write_text(BARREL_FULL, encoding="utf-8")
    g = grade_test_file(workspace, "test_pubsub.py")
    print(f"[grade] passed={g['passed']}/{g['total']}")

    summary = {
        "phase": "J_pubsub_d0_greenfield",
        "cell": "D0",
        "run_id": run_id,
        "passed": g["passed"],
        "total": g["total"],
        "pass_rate": g["pass_rate"],
        "spec_chars": len(spec_text),
        "contracts_initial": len(contracts),
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_resp["cost_usd"],
        "exec_duration_s": round(exec_elapsed, 1),
        "exec_rc": exec_proc.returncode,
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-80:]),
        "grade_stdout_tail": g["stdout_tail"],
    }
    out_path = OUT_DIR / f"phJ_pubsub_d0_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: D0 pass={g['passed']}/{g['total']}  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def run_d_refactor(cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_refactor_workspace()
    project = f"phJ_pubsub_{cell.lower()}_{run_id}"
    print(f"[setup] {cell} workspace: {workspace}  project: {project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    spec_text = ""
    contracts: dict[str, str] = {}
    opus_elapsed = 0.0
    opus_cost = 0.0
    if cell in ("D2", "D3"):
        existing_code = []
        for ref_file in sorted(REFERENCE_DIR.iterdir()):
            if ref_file.is_file() and ref_file.suffix == ".py":
                rel = f"pubsub/{ref_file.name}"
                existing_code.append(f"### {rel} (current contents)\n```python\n"
                                      f"{ref_file.read_text(encoding='utf-8')}\n```")
        existing_listing = "\n\n".join(existing_code)
        refactor_prompt = (
            f"The change to apply: rename `Bus.subscribe` to "
            f"`Bus.register_handler` in pubsub/bus.py. Pure rename — "
            f"signature and behavior are identical, only the method "
            f"name changes. The old name `subscribe` must NOT exist "
            f"after the refactor.\n\n"
            f"Below is the current state of the library. Author a "
            f"refactor specification with one section labeled "
            f"`### pubsub/bus.py` containing the prose description "
            f"and a `python-contract` fenced block showing the new "
            f"public surface of Bus. Output raw markdown — no outer "
            f"wrap.\n\n"
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

    req, task_id = seed_loom_refactor(cell, store, spec_text)
    print(f"[seed] cell={cell} task_id={task_id} "
          f"loom_seeded={cell != 'D1'} delivery={cell not in ('D1','D2')}")

    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next",
         "--model", os.environ.get("PHJ_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    g = grade_test_file(workspace, "test_pubsub.py")
    print(f"[grade] passed={g['passed']}/{g['total']}")

    tail = exec_proc.stdout

    summary = {
        "phase": f"J_pubsub_{cell.lower()}_refactor",
        "cell": cell,
        "run_id": run_id,
        "passed": g["passed"],
        "total": g["total"],
        "pass_rate": g["pass_rate"],
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
        "grade_stdout_tail": g["stdout_tail"],
    }
    out_path = OUT_DIR / f"phJ_pubsub_{cell.lower()}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']}  "
          f"wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: phJ_pubsub_refactor_smoke.py <cell> [run_id]")
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
