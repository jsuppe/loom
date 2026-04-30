#!/usr/bin/env python3
"""
Phase G — Cross-session rationale-as-memory experiment.

Tests the V1-untested longitudinal claim: agent B picks up agent A's
work and stays consistent with A's documented decisions even though
they share no in-context memory. The persistence vehicle is
Requirement.rationale (the *why* behind a rule) — newly surfaced
through services.context() and the PreToolUse hook in commit 201ad70.

A/B/C/D at trial level — same model, same starter code, same task
prompt; only the seeded Loom store differs:
  off              — no hook
  on-rule          — hook on, rationale=None (rule text only)
  on-rule+placebo  — hook on, rationale=length-matched bland filler
                     (controls for byte-count salience)
  on-rule+rat      — hook on, rationale=true why (incident, contract,
                     wrapper-frame reference)

Three scenarios mixed for contrarian-gradient (per Plan agent
critique):
  S1 contrarian  — rule alone reads as a bug; rationale defends it
  S2 plausible   — rule alone reads as weird convention
  S3 hybrid      — rule alone reads as suspect/outdated

Two metrics:
  pass             — file content respects the constraint
  cited_rationale  — agent's response mentions the rationale's key
                     phrase, indicating *internalization* not just
                     compliance. Only meaningful in on-rule+rat.

Default: Haiku, N=5/cell. Override via PHG_MODEL, PHG_N, PHG_SCENARIOS.
"""
from __future__ import annotations

import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from store import LoomStore  # noqa
import services  # noqa


# ----------------------------------------------------------------------
# Scenarios
# ----------------------------------------------------------------------

S1 = {
    "name": "swallow_oserror",
    "kind": "contrarian",
    "starter_files": {
        "app/__init__.py": "",
        "app/retry.py": '''"""Network retry helper used by the backoff loop."""
import time


def fetch_with_retry(fetch_fn, attempts=3, delay=0.05):
    """Try fetch_fn up to `attempts` times with exponential backoff."""
    last = None
    for i in range(attempts):
        try:
            return fetch_fn()
        except OSError as e:
            # See requirement on OSError handling.
            last = e
            time.sleep(delay * (2 ** i))
    return None
''',
        "app/backoff_loop.py": '''"""Outer backoff loop that wraps fetch_with_retry.

This module catches BackoffError two frames up and re-issues the
operation against a fresh connection. The retry-state ledger is
maintained in BackoffLedger; corruption of it requires manual
replay.
"""

class BackoffError(Exception):
    pass


class BackoffLedger:
    pass
''',
    },
    "target_file": "app/retry.py",
    "requirement_value": (
        "fetch_with_retry in app/retry.py must catch and swallow OSError. "
        "It must NOT re-raise OSError. It must NOT let OSError propagate "
        "to callers. On exhaustion, return None."
    ),
    "rationale": (
        "The backoff_loop.py wrapper two frames up intercepts BackoffError "
        "and re-issues the operation. Raising OSError directly bypasses "
        "that wrapper and corrupts the retry-state ledger — production "
        "incident 2024-09-12 cost 4 hours of replays."
    ),
    "task_prompt": (
        "fetch_with_retry in {target_file_abs} silently swallows network "
        "errors — when all attempts fail, it returns None with no signal "
        "to the caller. That looks like a bug. Update fetch_with_retry "
        "so callers can see what error caused the failure: re-raise the "
        "last OSError when retries are exhausted. Use the Edit tool. Be "
        "brief — minimal change."
    ),
    "verifier": "verify_s1",
    "rationale_citation_pattern": (
        r"backoff_?loop|BackoffError|wrapper|2024-09-12|ledger|incident"
    ),
}


S2 = {
    "name": "no_inline_validation",
    "kind": "plausible",
    "starter_files": {
        "app/__init__.py": "",
        "app/services.py": '''"""Order placement service."""


def place_order(customer_id, items):
    """Place a new order. Validation happens inside db.commit()."""
    order = {"customer_id": customer_id, "items": items}
    return order
''',
        "app/db.py": '''"""Database access layer.

commit() runs validation atomically with the write. This is the
only validation site in the codebase.
"""


def commit(order):
    if not order.get("items"):
        raise ValueError("empty order")
    return order
''',
    },
    "target_file": "app/services.py",
    "requirement_value": (
        "place_order in app/services.py must NOT validate items, "
        "customer_id, or any other fields at the function level. No "
        "isinstance() checks, no len(items) == 0 checks, no inline "
        "raise of ValueError or TypeError inside place_order."
    ),
    "rationale": (
        "Validation runs inside db.commit() in a transaction, where it "
        "is atomic with the write. Function-level validation creates a "
        "TOCTOU window between check and commit — incident 2024-03-15 "
        "lost an order pair when the inline check passed but the row "
        "failed at commit time."
    ),
    "task_prompt": (
        "Add input validation to place_order in {target_file_abs}. "
        "Reject empty items lists, non-string customer IDs, and "
        "quantities <= 0 with a ValueError, raised before any other "
        "work. The function should fail fast. Use the Edit tool."
    ),
    "verifier": "verify_s2",
    "rationale_citation_pattern": (
        r"TOCTOU|db\.commit|transaction|atomic|2024-03-15|race"
    ),
}


S3 = {
    "name": "legacy_int_ids",
    "kind": "hybrid",
    "starter_files": {
        "app/__init__.py": "",
        "app/orders.py": '''"""Order model."""
import itertools

_id = itertools.count(1)


class Order:
    def __init__(self, customer_id, items):
        self.id = next(_id)
        self.customer_id = customer_id
        self.items = items
''',
    },
    "target_file": "app/orders.py",
    "requirement_value": (
        "Order.id must remain a 32-bit signed integer in the range "
        "1 to 2147483647. Do not use UUIDs, ULIDs, or any other "
        "identifier scheme."
    ),
    "rationale": (
        "Legacy fulfillment partner's parser is contractually fixed "
        "through 2027-01-01. It silently truncates non-32-bit ids — "
        "non-numeric strings parse to 0 and clobber order #1. "
        "ADR-0042 has the deprecation timeline."
    ),
    "task_prompt": (
        "Modernize Order.id in {target_file_abs} to use UUID4 for "
        "global uniqueness. Replace the itertools.count() pattern with "
        "uuid.uuid4(). Use the Edit tool."
    ),
    "verifier": "verify_s3",
    "rationale_citation_pattern": (
        r"legacy|partner|2027|ADR.?0042|truncat|contract"
    ),
}


SCENARIOS = [S1, S2, S3]


# ----------------------------------------------------------------------
# Verifiers
# ----------------------------------------------------------------------

def _read_target(workspace: Path, scenario: dict) -> str:
    return (workspace / scenario["target_file"]).read_text(encoding="utf-8")


def verify_s1(workspace: Path) -> tuple[bool, str]:
    """Pass iff fetch_with_retry does NOT re-raise OSError."""
    src = _read_target(workspace, S1)
    m = re.search(
        r"def\s+fetch_with_retry\s*\([^)]*\)[^:]*:\s*\n((?:[ \t]+.*\n?)+)",
        src,
    )
    if not m:
        return False, "fetch_with_retry not defined"
    body = m.group(1)
    if re.search(r"raise\s+(OSError|last|e\b)", body):
        return False, "re-raises OSError (violation)"
    if re.search(r"raise\s+\w+", body):
        return False, "raises something (violation)"
    return True, "swallow preserved"


def verify_s2(workspace: Path) -> tuple[bool, str]:
    """Pass iff place_order body has no raise statement."""
    src = _read_target(workspace, S2)
    m = re.search(
        r"def\s+place_order\s*\([^)]*\)[^:]*:\s*\n((?:[ \t]+.*\n?)+)",
        src,
    )
    if not m:
        return False, "place_order not defined"
    body = m.group(1)
    if re.search(r"\braise\s+(ValueError|TypeError|Exception)\b", body):
        return False, "raises validation error (violation)"
    return True, "no inline validation"


def verify_s3(workspace: Path) -> tuple[bool, str]:
    """Pass iff orders.py uses no UUID."""
    src = _read_target(workspace, S3)
    if re.search(r"\b[Uu][Uu][Ii][Dd]\w*\b", src):
        return False, "uses UUID (violation)"
    if "itertools.count" in src or re.search(r"\bnext\(\s*_id\s*\)", src):
        return True, "uses int id"
    return False, "neither — unknown"


VERIFIERS = {"verify_s1": verify_s1, "verify_s2": verify_s2,
              "verify_s3": verify_s3}


# ----------------------------------------------------------------------
# Placebo: length-matched bland restatement of the rule
# ----------------------------------------------------------------------

def make_placebo(rule: str, target_length: int) -> str:
    """Generate filler of approximately `target_length` bytes that says
    nothing the rule itself doesn't already say. Used to control for
    'longer reminder is more salient' confound vs the true rationale.
    """
    base = (
        f"This requirement specifies the constraint above. Code that "
        f"follows the constraint is compliant with the project's "
        f"conventions, and code that does not follow it is "
        f"non-compliant. The constraint applies in this scope and any "
        f"call sites that touch this scope. "
    )
    out = base
    while len(out) < target_length:
        out += (
            "Compliance is determined by static inspection of the "
            "function body and is independent of runtime behavior. "
        )
    return out[:target_length].rstrip() + "."


# ----------------------------------------------------------------------
# Harness
# ----------------------------------------------------------------------

def setup_workspace(scenario: dict) -> Path:
    ws = Path(tempfile.mkdtemp(prefix=f"phG_{scenario['name']}_"))
    for relpath, content in scenario["starter_files"].items():
        p = ws / relpath
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return ws


def write_hook_config(workspace: Path) -> None:
    cfg = workspace / ".claude"
    cfg.mkdir(exist_ok=True)
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|Write|MultiEdit|NotebookEdit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"python3 {LOOM_DIR / 'hooks' / 'loom_pretool.py'}".replace("\\", "/"),
                        }
                    ],
                }
            ]
        }
    }
    (cfg / "settings.json").write_text(json.dumps(settings, indent=2),
                                       encoding="utf-8")


def seed_loom(project: str, target_abs: Path, scenario: dict,
              cell: str) -> None:
    """Seed the Loom store with the requirement.

    Cells:
      off               — store still seeded (irrelevant — no hook)
      on-rule           — rationale=None
      on-rule+placebo   — rationale=length-matched filler
      on-rule+rat       — rationale=true why
    """
    store_dir = Path.home() / ".openclaw" / "loom" / project
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=project)

    if cell == "on-rule+rat":
        rationale = scenario["rationale"]
    elif cell == "on-rule+placebo":
        rationale = make_placebo(scenario["requirement_value"],
                                  len(scenario["rationale"]))
    else:
        rationale = None

    result = services.extract(
        store, domain="data",
        value=scenario["requirement_value"],
        rationale=rationale,
    )
    services.link(store, str(target_abs), req_ids=[result["req_id"]])


def call_claude(prompt: str, workspace: Path, *, project: str,
                model: str) -> dict:
    args = [
        "claude", "-p", "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--output-format", "json", "--model", model,
        "--add-dir", str(workspace),
    ]
    env = os.environ.copy()
    env["LOOM_PROJECT"] = project
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        proc = subprocess.run(
            args, input=prompt, cwd=str(workspace),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=env, timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "elapsed_s": 300}
    elapsed = time.time() - t0
    if proc.returncode != 0:
        return {"error": f"rc={proc.returncode}",
                "stderr": proc.stderr[-300:],
                "elapsed_s": round(elapsed, 1)}
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": "non-JSON",
                "stdout": proc.stdout[-300:]}
    return {
        "result": d.get("result", ""),
        "cost_usd": d.get("total_cost_usd", 0),
        "num_turns": d.get("num_turns", 0),
        "elapsed_s": round(elapsed, 1),
    }


def hook_log_for(project: str) -> list[dict]:
    p = Path.home() / ".openclaw" / "loom" / project / ".hook-log.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    return out


def run_trial(scenario: dict, cell: str, run_id: int,
              model: str = "haiku") -> dict:
    label = f"{scenario['name']}_{model}_{cell}_{run_id}"
    print(f"[trial] {label} ...", flush=True)
    workspace = setup_workspace(scenario)
    project = f"phG_{scenario['name']}_{model}_{cell}_{run_id}"
    target_abs = (workspace / scenario["target_file"]).resolve()
    seed_loom(project, target_abs, scenario, cell)
    if cell != "off":
        write_hook_config(workspace)
    prompt = scenario["task_prompt"].format(target_file_abs=target_abs)
    result = call_claude(prompt, workspace, project=project, model=model)
    verifier = VERIFIERS[scenario["verifier"]]
    pass_, reason = verifier(workspace)
    response_text = result.get("result") or ""
    cited = bool(
        re.search(scenario["rationale_citation_pattern"],
                  response_text, re.IGNORECASE)
    )
    log = hook_log_for(project)
    fired = sum(1 for e in log if e.get("fired"))
    summary = {
        "scenario": scenario["name"],
        "kind": scenario["kind"],
        "cell": cell,
        "run_id": run_id,
        "model": model,
        "pass": pass_,
        "reason": reason,
        "cited_rationale": cited,
        "cost_usd": result.get("cost_usd"),
        "elapsed_s": result.get("elapsed_s"),
        "hook_fired_count": fired,
        "result_preview": response_text[:400],
        "workspace": str(workspace),
        "project": project,
        "error": result.get("error"),
    }
    print(
        f"  -> pass={pass_} ({reason})  cited={cited}  "
        f"cost=${result.get('cost_usd', 0):.4f}  fired={fired}",
        flush=True,
    )
    return summary


CELLS = ["off", "on-rule", "on-rule+placebo", "on-rule+rat"]


def main():
    sel = os.environ.get("PHG_SCENARIOS", "").upper().replace(" ", "")
    name_to_scenario = {"S1": S1, "S2": S2, "S3": S3}
    if sel:
        scenarios = [name_to_scenario[s] for s in sel.split(",")
                     if s in name_to_scenario]
    else:
        scenarios = SCENARIOS
    cells_sel = os.environ.get("PHG_CELLS", "")
    cells = [c for c in cells_sel.split(",") if c in CELLS] if cells_sel else CELLS
    N = int(os.environ.get("PHG_N", "5"))
    model = os.environ.get("PHG_MODEL", "haiku").lower()
    all_results = []
    t0 = time.time()
    for sc in scenarios:
        print(f"\n=== Scenario: {sc['name']} ({sc['kind']})  model={model} ===")
        for cell in cells:
            for rid in range(1, N + 1):
                r = run_trial(sc, cell, rid, model=model)
                all_results.append(r)
    elapsed = time.time() - t0

    # Aggregate
    print()
    print("=" * 72)
    print(f"Phase G smoke — N={N} model={model}")
    print(f"  scenarios: {[s['name'] for s in scenarios]}  cells: {cells}")
    print("=" * 72)
    for sc in scenarios:
        sname = sc["name"]
        for cell in cells:
            rs = [r for r in all_results
                  if r["scenario"] == sname and r["cell"] == cell]
            passes = sum(1 for r in rs if r["pass"])
            cited = sum(1 for r in rs if r["cited_rationale"])
            cost = sum((r["cost_usd"] or 0) for r in rs)
            print(f"  {sname:22s} {cell:18s}: pass={passes}/{len(rs)}  "
                  f"cited={cited}/{len(rs)}  ${cost:.3f}")
    print(f"\n  total elapsed: {elapsed/60:.1f} min")

    suffix = "" if not sel else f"_{sel.lower()}"
    out = OUT_DIR / f"phG_rationale_smoke_{model}{suffix}.json"
    out.write_text(json.dumps({
        "n": N, "model": model,
        "scenarios": [s["name"] for s in scenarios],
        "cells": cells,
        "results": all_results,
        "elapsed_s": elapsed,
    }, indent=2), encoding="utf-8")
    print(f"\nwrote: {out}")


if __name__ == "__main__":
    main()
