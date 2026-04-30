#!/usr/bin/env python3
"""
Phase K — cross-session memory smoke.

Tests Loom's longitudinal claim: agent B (a fresh process with no
in-context memory) reads agent A's documented rationale via Loom and
respects a constraint it would otherwise contradict.

3 scenarios × 4 cells × N=5 = 60 trials.

Scenarios (all designed so the qwen-facing task contradicts the
constraint encoded in the requirement):
  S1 swallow_oserror      — task: "fix the swallow bug"  rule: "must swallow"
  S2 no_inline_validation — task: "add validation"       rule: "no inline validation"
  S3 legacy_int_ids       — task: "modernize to UUID4"   rule: "must stay 32-bit int"

Cells:
  off                — qwen sees task only (no Loom seeding)
  on-rule            — req(value=rule, rationale="")
  on-rule+placebo    — req(value=rule, rationale=length-matched filler that
                        verbosely restates the rule with no new info)
  on-rule+rat        — req(value=rule, rationale=true rationale)

Two metrics per trial:
  pass             — does the modified file still satisfy the constraint?
  cited_rationale  — does the modified file mention a rationale key phrase?
                      (tests internalization vs mere compliance)

Default executor: qwen3.5:latest. Override via PHK_EXEC_MODEL.

No Opus calls — specs are fixed text per scenario, so the cell
comparison is pure (no spec-quality variance).
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
SCENARIOS_DIR = BAKEOFF_DIR / "benchmarks" / "crosssession"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa: E402
from loom import services  # noqa: E402


# ---------------------------------------------------------------------------
# Scenario configs — fixed text per scenario, never Opus-authored
# ---------------------------------------------------------------------------

SCENARIOS = {
    "S1": {
        "dir": SCENARIOS_DIR / "s1_swallow_oserror",
        "target_file": "app/retry.py",
        "test_file": "test_retry.py",
        "task": (
            "The retry loop in app/retry.py swallows network errors silently. "
            "That looks like a bug — callers can't tell what failed when "
            "_do_fetch raises OSError, the function just continues to the "
            "next attempt. Modify fetch_with_retry to properly propagate "
            "OSError so callers can see what went wrong."
        ),
        "rule": (
            "Constraint for app/retry.py::fetch_with_retry: catch and "
            "swallow OSError on every attempt. Do NOT propagate OSError "
            "from this function. Return None when all attempts fail."
        ),
        "rationale": (
            "The retry wrapper in app/backoff_loop.py two frames up "
            "intercepts BackoffError and re-issues. Raising OSError "
            "directly from fetch_with_retry breaks the wrapper contract — "
            "production incident 2024-09-12 lost three hours while ops "
            "chased a propagation bug that was actually working as "
            "intended. The current swallow-and-return-None behavior is "
            "load-bearing for the BackoffError wrapper above us."
        ),
        "rationale_keyphrases": [
            "wrapper", "BackoffError", "incident", "load-bearing",
        ],
    },
    "S2": {
        "dir": SCENARIOS_DIR / "s2_no_inline_validation",
        "target_file": "app/orders.py",
        "test_file": "test_orders.py",
        "task": (
            "place_order in app/orders.py is missing input validation. "
            "Add validation at the function entry: empty items list, "
            "negative quantities, non-string customer IDs should all "
            "raise ValueError immediately. Validation should happen at "
            "the start of place_order, before any other logic runs."
        ),
        "rule": (
            "Constraint for app/orders.py::place_order: do NOT validate "
            "at function level. All validation runs only via _commit. "
            "place_order builds the order dict and delegates to _commit "
            "without any pre-checks of its own."
        ),
        "rationale": (
            "Validation runs at db.commit() inside a transaction. "
            "Function-level validation in place_order creates a TOCTOU "
            "window — incident 2024-03-15 lost an order pair because "
            "two concurrent place_order calls passed function-level "
            "validation simultaneously, then both succeeded at commit "
            "and produced duplicate fulfillment requests. The single-"
            "validation-point invariant inside _commit is what closes "
            "that window."
        ),
        "rationale_keyphrases": [
            "TOCTOU", "transaction", "incident", "concurrent",
        ],
    },
    "S3": {
        "dir": SCENARIOS_DIR / "s3_legacy_int_ids",
        "target_file": "app/ids.py",
        "test_file": "test_ids.py",
        "task": (
            "Modernize the order ID generation in app/ids.py. Use UUID4 "
            "(uuid.uuid4()) for global uniqueness instead of bounded "
            "random integers. Random ints in a 32-bit range collide far "
            "too often and are not suitable for distributed systems. "
            "Update generate_order_id accordingly."
        ),
        "rule": (
            "Constraint for app/ids.py::generate_order_id: must return a "
            "32-bit signed positive integer (1 to 2_147_483_647 "
            "inclusive). Do NOT use UUIDs. Return type must be int."
        ),
        "rationale": (
            "The legacy fulfillment partner's parser is contractually "
            "fixed through 2027-01-01 and silently truncates non-32-bit "
            "IDs to their lower 32 bits. Switching to UUID would mean "
            "every order ID we send the partner gets silently mapped to "
            "a colliding 32-bit value — duplicate fulfillment requests "
            "without any error surface. ADR-0042 has the full timeline "
            "of when we can drop this constraint (2027-01-01)."
        ),
        "rationale_keyphrases": [
            "legacy", "partner", "ADR-0042", "truncate", "2027",
        ],
    },
}


# Length-matched placebo. The original Phase G plan: filler that
# verbosely restates the rule with no new content. We generate it
# per-scenario to roughly match the rationale length.
def make_placebo(rule: str, target_length: int) -> str:
    """Return a length-matched verbose restatement of the rule."""
    base = (
        f"This requirement specifies that {rule.lower()} "
        f"Code that complies with this requirement is correct. "
        f"Code that does not comply with this requirement is incorrect. "
        f"The compliant pattern follows the requirement; the non-compliant "
        f"pattern does not. Applying this requirement is the goal. "
        f"Failing to apply this requirement violates the goal. "
        f"Compliance with this requirement is the deliverable. "
        f"Non-compliance with this requirement is the failure mode."
    )
    while len(base) < target_length - 50:
        base += " " + (
            "The compliance pattern is that the requirement applies. "
            "The non-compliance pattern is that the requirement does not apply. "
        )
    return base[:target_length].rstrip() + "."


# ---------------------------------------------------------------------------
# Workspace setup + Loom seeding per cell
# ---------------------------------------------------------------------------

def setup_workspace(scenario_id: str) -> Path:
    cfg = SCENARIOS[scenario_id]
    ws = Path(tempfile.mkdtemp(prefix=f"phK_{scenario_id.lower()}_"))
    # Copy reference code
    ref = cfg["dir"] / "reference"
    shutil.copytree(ref, ws, dirs_exist_ok=True)
    (ws / "tests").mkdir(exist_ok=True)
    # Copy hidden test under tests/ in the workspace
    shutil.copy(cfg["dir"] / "tests" / cfg["test_file"],
                 ws / "tests" / cfg["test_file"])
    # Conftest so pytest finds the package
    (ws / "conftest.py").write_text(
        "import sys, pathlib\n"
        "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
        encoding="utf-8",
    )
    # Loom config — replace mode so qwen rewrites the whole file
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "pytest_replace",
                    "model": "qwen3.5:latest"}, indent=2),
        encoding="utf-8",
    )
    return ws


def seed_loom(scenario_id: str, cell: str, store) -> tuple[Any, str]:
    """Seed Loom for the given cell. Returns (req_or_none, task_id)."""
    cfg = SCENARIOS[scenario_id]
    target_file = cfg["target_file"]
    test_file = f"tests/{cfg['test_file']}"

    if cell == "off":
        # No Loom seeding — placeholder spec to satisfy task_add API.
        ph_req = services.extract(
            store, domain="behavior",
            value="placeholder",
            rationale="phK off cell — Loom store empty",
        )
        ph_spec = services.spec_add(
            store, ph_req["req_id"],
            "placeholder — off cell, contents not delivered",
        )
        result = services.task_add(
            store,
            parent_spec=ph_spec["spec_id"],
            title=cfg["task"],
            files_to_modify=[target_file],
            test_to_write=test_file,
            context_reqs=[],
            context_specs=[],
            context_files=[target_file],
            depends_on=[],
            size_budget_files=1,
            size_budget_loc=200,
            created_by=f"phK_{scenario_id}_off",
        )
        return None, result["id"]

    # All other cells: rule is in req.value; rationale varies by cell.
    if cell == "on-rule":
        rationale = ""
    elif cell == "on-rule+placebo":
        rationale = make_placebo(cfg["rule"], len(cfg["rationale"]))
    elif cell == "on-rule+rat":
        rationale = cfg["rationale"]
    else:
        raise ValueError(f"unknown cell: {cell}")

    req = services.extract(
        store, domain="behavior",
        value=cfg["rule"],
        rationale=rationale,
    )
    # Spec is required by task_add API — minimal spec just pointing at the file.
    spec = services.spec_add(
        store, req["req_id"],
        f"Constraint applies to {target_file}.",
    )

    result = services.task_add(
        store,
        parent_spec=spec["spec_id"],
        title=cfg["task"],
        files_to_modify=[target_file],
        test_to_write=test_file,
        context_reqs=[req["req_id"]],
        context_specs=[spec["spec_id"]],
        context_files=[target_file],
        depends_on=[],
        size_budget_files=1,
        size_budget_loc=200,
        created_by=f"phK_{scenario_id}_{cell}",
    )
    return req, result["id"]


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

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


def read_exec_log_outcome(project: str) -> dict:
    """Read the most recent loom_exec gate-test outcome from the
    project's .exec-log.jsonl. This is what qwen's *output* scored on
    the gate test in scratch — before any promote-or-not decision.

    For this experiment, the gate result is the experimental outcome:
    "did qwen produce code that satisfied the constraint?" If we
    instead grade the post-promotion workspace, failed promotions
    leave the original (compliant) code in place and falsely report
    pass — masking the cell signal.
    """
    log_path = Path.home() / ".openclaw" / "loom" / project / ".exec-log.jsonl"
    if not log_path.exists():
        return {"passed": 0, "total": 0, "outcome": "no_log",
                "stdout_tail": "no exec log produced"}
    last = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    if last is None:
        return {"passed": 0, "total": 0, "outcome": "empty_log",
                "stdout_tail": "exec log empty"}
    return {
        "passed": last.get("passed", 0),
        "total": last.get("total", 0),
        "outcome": last.get("outcome", "unknown"),
        "elapsed_s": last.get("elapsed_s", 0),
        "input_tokens": last.get("input_tokens", 0),
        "output_tokens": last.get("output_tokens", 0),
        "stdout_tail": json.dumps(last, indent=2),
    }


def check_cited_rationale(workspace: Path, scenario_id: str) -> dict:
    """Check whether the modified file mentions any rationale key phrase."""
    cfg = SCENARIOS[scenario_id]
    target = workspace / cfg["target_file"]
    if not target.exists():
        return {"cited": False, "matched": []}
    text = target.read_text(encoding="utf-8")
    matched = [kp for kp in cfg["rationale_keyphrases"]
                if kp.lower() in text.lower()]
    return {"cited": bool(matched), "matched": matched}


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run_one(scenario_id: str, cell: str, run_id: str) -> dict:
    t0 = time.time()
    workspace = setup_workspace(scenario_id)
    project = f"phK_{scenario_id.lower()}_{cell.replace('+', '_').replace('-', '_')}_{run_id}"
    print(f"[setup] scenario={scenario_id} cell={cell} project={project}")

    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    req, task_id = seed_loom(scenario_id, cell, store)
    # services.extract returns a dict ({req_id, ...}); fetch the
    # Requirement object so we can read its rationale length for
    # logging. For the off cell req is None.
    rationale_len = 0
    if req is not None:
        req_obj = store.get_requirement(req["req_id"])
        if req_obj and req_obj.rationale:
            rationale_len = len(req_obj.rationale)
    print(f"[seed] task_id={task_id} rationale_len={rationale_len}")

    exec_env = {**os.environ}
    exec_env.setdefault("LOOM_EXEC_CONTRACT", "1")
    # Close the parent's connection so the subprocess sees a consistent
    # WAL state (not strictly needed with WAL, but cheap insurance).
    store.conn.close()

    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next",
         "--model", os.environ.get("PHK_EXEC_MODEL", "qwen3.5:latest"),
         "-p", project, "--target-dir", str(workspace)],
        env=exec_env,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    exec_elapsed = time.time() - t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")

    g = read_exec_log_outcome(project)
    cite = check_cited_rationale(workspace, scenario_id)
    print(f"[grade] pass={g['passed']}/{g['total']}  outcome={g.get('outcome')}  "
          f"cited_rationale={cite['cited']} matched={cite['matched']}")

    summary = {
        "phase": "K_crosssession_smoke",
        "scenario": scenario_id,
        "cell": cell,
        "run_id": run_id,
        "passed": g["passed"],
        "total": g["total"],
        "pass_rate": (g["passed"] / g["total"]) if g["total"] else 0.0,
        "outcome": g.get("outcome"),
        "cited_rationale": cite["cited"],
        "rationale_keyphrases_matched": cite["matched"],
        "rationale_len": rationale_len,
        "input_tokens": g.get("input_tokens", 0),
        "output_tokens": g.get("output_tokens", 0),
        "exec_rc": exec_proc.returncode,
        "exec_duration_s": round(exec_elapsed, 1),
        "workspace": str(workspace),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-60:]),
        "grade_log_entry": g["stdout_tail"],
    }
    cell_slug = cell.replace("+", "_").replace("-", "_")
    out_path = OUT_DIR / f"phK_{scenario_id.lower()}_{cell_slug}_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {scenario_id} {cell} pass={g['passed']}/{g['total']}  "
          f"cited={cite['cited']}")
    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage: phK_crosssession_smoke.py <scenario> <cell> [run_id]")
        print("  scenario ∈ S1, S2, S3")
        print("  cell     ∈ off, on-rule, on-rule+placebo, on-rule+rat")
        return 1
    scenario = argv[1]
    cell = argv[2]
    run_id = argv[3] if len(argv) > 3 else "smoke"
    if scenario not in SCENARIOS:
        print(f"unknown scenario: {scenario}", file=sys.stderr)
        return 1
    if cell not in ("off", "on-rule", "on-rule+placebo", "on-rule+rat"):
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(scenario, cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
