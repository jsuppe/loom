#!/usr/bin/env python3
"""
M12 dogfooding closure — exercise the full M12 stack (kind field,
per-kind renderers, kind-aware classifier, evidences link type,
per-kind lifecycle states) on the loom project's own store.

Payload:

  Phase A — Clean up existing captures:
    A1. Archive a junk requirement that crept in via early intake
        ("Implement the m11.3 feature.").
    A2. Reclassify REQ-c0e06e44 ("All experimental findings must be
        retained in github") from kind=requirement → process_rule,
        status=active.
    A3. Reclassify REQ-73a0d7de (meta-finding "Loom's value-add is
        delivering captured rationale...") from kind=requirement →
        finding, status=confirmed.

  Phase B — Capture 5 empirical findings underlying the lessons:
    Each finding is a measured observation from a specific
    experiment, with rationale citing the source. Linked back to
    the corresponding requirement via --derives-from so the chain
    walks from imperative → empirical evidence.

  Phase C — Capture 1 new process_rule from this session:
    "Justify experimental design before running" (from the user's
    'please provide evidence this is a good idea' redirect on phS).

  Phase D — Run sync to populate the new per-kind files, then
    doctor + metrics for visibility.

Output:
  - Console log of every operation (extract / set_kind / set_status / archive)
  - Saved as experiments/pilot/dogfood_m12_results.json with:
      {phase: A|B|C|D, op: ..., outcome: ok|skipped|error, ...}
  - Doctor + metrics JSON snapshots for before/after comparison
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
PROJECT = "loom"
RESULTS_PATH = LOOM_DIR / "experiments" / "pilot" / "dogfood_m12_results.json"

results: list[dict] = []


def loom(*args: str, stdin: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a loom CLI command via the package entry point so the
    venv's installed `loom` command isn't required."""
    cmd = [sys.executable, "-m", "loom.cli", *args, "-p", PROJECT]
    return subprocess.run(
        cmd, cwd=LOOM_DIR, capture_output=True, text=True,
        input=stdin, encoding="utf-8", check=check,
    )


def record(phase: str, op: str, outcome: str, **kw) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "phase": phase, "op": op, "outcome": outcome, **kw,
    }
    results.append(rec)
    icon = {"ok": "✓", "skipped": "⊘", "error": "✗"}.get(outcome, "?")
    detail = " ".join(f"{k}={v}" for k, v in kw.items() if k not in ("stderr",))
    print(f"  {icon} [{phase}] {op}  {detail}")
    if outcome == "error" and "stderr" in kw:
        print(f"      stderr: {kw['stderr'][:160]}")


# ---------------------------------------------------------------------------
# Phase A — clean up existing reqs
# ---------------------------------------------------------------------------

PHASE_A_OPS = [
    # (op, req_id, value, kind|None, status|None)
    ("archive", "REQ-8a9f714b", "Implement the m11.3 feature.", None, "archived"),
    ("set_kind", "REQ-c0e06e44",
     "All experimental findings must be retained in github",
     "process_rule", "active"),
    ("set_kind", "REQ-73a0d7de",
     "Loom's value-add is delivering captured rationale to the agent",
     "finding", "confirmed"),
]


def phase_a() -> None:
    print("\n=== Phase A — clean up existing captures ===\n")
    for op, req_id, _, kind, status in PHASE_A_OPS:
        # Verify the req still exists before touching it.
        check = loom("trace", req_id, "--json", check=False)
        if check.returncode != 0:
            record("A", op, "skipped", req_id=req_id, reason="not_in_store")
            continue
        if op == "archive":
            r = loom("set-status", req_id, "archived", check=False)
            if r.returncode == 0:
                record("A", "archive", "ok", req_id=req_id)
            else:
                record("A", "archive", "error", req_id=req_id, stderr=r.stderr.strip())
            continue
        if op == "set_kind":
            r1 = loom("set-kind", req_id, kind, check=False)
            if r1.returncode != 0:
                record("A", "set_kind", "error", req_id=req_id, kind=kind, stderr=r1.stderr.strip())
                continue
            r2 = loom("set-status", req_id, status, check=False)
            if r2.returncode == 0:
                record("A", "set_kind", "ok", req_id=req_id, kind=kind, status=status)
            else:
                record("A", "set_status", "error", req_id=req_id, status=status, stderr=r2.stderr.strip())


# ---------------------------------------------------------------------------
# Phase B — capture 5 empirical findings
# ---------------------------------------------------------------------------

# (key, domain, value, rationale, derives_from_req_id_or_None)
# The derives_from refs an EXISTING requirement so the chain shows
# requirement → empirical-evidence finding.
FINDINGS = [
    ("F_phQ_bare_vs_rationale", "experimental",
     "M10.3 phQ series measured 0% compliance for bare-rule prompts vs 100% saturation when rationale was added — across multiple contrarian-spec scenarios on qwen3.5:latest.",
     "Source: experiments/bakeoff/v2_driver/phQ3_*, phQ4_*, phQ5_*, phQ7_* harnesses + FINDINGS-bakeoff-v2-pythonfirst-smoke.md. Bare cell N≥10 per condition; rationale cell N≥10 per condition. Reproduced across phQ3/4/5/7 (different rule shapes).",
     "REQ-ec36bd89"),  # the L1_rationale requirement
    ("F_phS_anti_rationale", "experimental",
     "phS anti-rationale ablation: an equivocal 'soft' anti-rationale (ANTI_SOFT, e.g. 'this might be optional under some interpretations') drops compliance to 0% — worse than the 30% placebo baseline. Direct contradiction (ANTI_HARD) scored higher than equivocation.",
     "Source: experiments/bakeoff/v2_driver/phS_anti_rationale_smoke.py + FINDINGS-bakeoff-v2-anti-rationale.md. N=10 per condition. Surprising direction — the model treats hedged disclaimers as more authoritative than direct contradiction.",
     "REQ-ec36bd89"),
    ("F_phT_imperative_kit", "experimental",
     "phT imperative-precedence ablation: combining a rhetorical opener ('STRICT REQUIREMENT — NON-NEGOTIABLE:') with an inline action-verb imperative ('You MUST NOT under any circumstances') restored compliance to 100% against ANTI_SOFT. Either component alone yielded ~60%. Top-of-prompt meta-preamble scored 0% (raw-prompt mode is flat).",
     "Source: experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py + phU_imperative_followups_smoke.py + FINDINGS-bakeoff-v2-rule-precedence.md. N=60 phT, N=50 phU length-control variants. The combined prefix+inline kit is reliable and length-independent.",
     "REQ-a636de03"),  # the L9_imperative_in_rule requirement
    ("F_phQ7_test_files", "experimental",
     "phQ7: including JavaScript test files (test_retry.js with PASS/FAIL labels) in the JsIndexer's workspace produced +40pp compliance lift on the placebo cell (30% → 70%) with no indexer code change.",
     "Source: experiments/bakeoff/v2_driver/phQ7_jsindexer_smoke.py + FINDINGS-bakeoff-v2-jsindexer.md. The test's `console.log('PASS: returns_null_on_failures')` functions as the closest thing to a contract in code form. PASS labels outperform bare assertions.",
     "REQ-2a621c40"),  # the L6_test_refs requirement
    ("F_phQ4_specialist_loses", "experimental",
     "phQ4 measured qwen2.5-coder:32b losing 20-30pp to qwen3.5:latest on contrarian-rule cells WITHOUT rationale (on-rule -20pp; +placebo -30pp at 32b). With rationale present, the 32b specialist outperforms 3.5b general by +20pp on the rat cell — the specialist's training priors hurt without explicit framing-defuser.",
     "Source: experiments/bakeoff/v2_driver/phQ4_executor_choice_smoke.py + FINDINGS-bakeoff-v2-executor-choice.md. N=10 per (model × condition). Implication: executor selection should depend on whether rationale-augmentation is reliable.",
     "REQ-aaa595ca"),  # the L2_bigger_not_better requirement
]


def phase_b() -> None:
    print("\n=== Phase B — capture 5 empirical findings ===\n")
    for key, domain, value, rationale, derives_from in FINDINGS:
        # Use stdin path so emoji/em-dash in value/rationale survive
        # (M12.3 stdin UTF-8 fix).
        stdin_payload = f"REQUIREMENT: {domain} | {value}"
        args = [
            "extract", "--kind", "finding", "--rationale", rationale,
        ]
        if derives_from:
            args.extend(["--derives-from", derives_from])
        r = loom(*args, stdin=stdin_payload, check=False)
        if r.returncode != 0:
            record("B", key, "error", stderr=r.stderr.strip())
            continue
        # Pull the new req's ID from the success line.
        req_id = None
        for line in r.stdout.splitlines():
            if line.startswith("✓ REQ-"):
                req_id = line.split(":", 1)[0].lstrip("✓ ").strip()
                break
        if not req_id:
            record("B", key, "error", reason="no_req_id_in_output", stdout=r.stdout[:200])
            continue
        # Promote to status=confirmed (default for kind=finding is preliminary).
        r2 = loom("set-status", req_id, "confirmed", check=False)
        if r2.returncode != 0:
            record("B", key, "error", req_id=req_id, op="set-status",
                   stderr=r2.stderr.strip())
            continue
        record("B", key, "ok", req_id=req_id, derives_from=derives_from or "none")


# ---------------------------------------------------------------------------
# Phase C — capture 1 new process_rule from this session
# ---------------------------------------------------------------------------

PROCESS_RULES = [
    ("P_justify_design", "operational",
     "Justify experimental design choices (N, conditions, baselines) before running an ablation; defend the choice on epistemic grounds, not just convenience.",
     "Captured from this session's redirect on phS where I initially proposed N=10 without justification. The 'please provide evidence this is a good idea' user feedback established this as a discipline. The cost of a poorly-designed N=10 is wasted compute AND a defended-but-wrong conclusion; the cost of justifying first is one paragraph.",
     ),
]


def phase_c() -> None:
    print("\n=== Phase C — capture 1 new process_rule ===\n")
    for key, domain, value, rationale in PROCESS_RULES:
        stdin_payload = f"REQUIREMENT: {domain} | {value}"
        r = loom(
            "extract", "--kind", "process_rule", "--rationale", rationale,
            stdin=stdin_payload, check=False,
        )
        if r.returncode != 0:
            record("C", key, "error", stderr=r.stderr.strip())
            continue
        req_id = None
        for line in r.stdout.splitlines():
            if line.startswith("✓ REQ-"):
                req_id = line.split(":", 1)[0].lstrip("✓ ").strip()
                break
        if not req_id:
            record("C", key, "error", reason="no_req_id_in_output", stdout=r.stdout[:200])
            continue
        # Default for process_rule is "proposed"; promote to "active".
        r2 = loom("set-status", req_id, "active", check=False)
        if r2.returncode != 0:
            record("C", key, "error", req_id=req_id, op="set-status",
                   stderr=r2.stderr.strip())
            continue
        record("C", key, "ok", req_id=req_id, status="active")


# ---------------------------------------------------------------------------
# Phase D — sync, doctor, metrics
# ---------------------------------------------------------------------------

def phase_d() -> None:
    print("\n=== Phase D — sync + doctor + metrics ===\n")
    # sync
    r = loom("sync", "--output", "./docs", check=False)
    if r.returncode == 0:
        record("D", "sync", "ok", stdout_tail=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "")
    else:
        record("D", "sync", "error", stderr=r.stderr.strip())
    # doctor (json)
    r = loom("doctor", "--json", check=False)
    if r.returncode == 0:
        try:
            d = json.loads(r.stdout)
            record("D", "doctor", "ok",
                   warnings=len(d.get("warnings", [])),
                   ok=d.get("ok"))
        except json.JSONDecodeError:
            record("D", "doctor", "error", reason="parse")
    # metrics (json) — totals
    r = loom("metrics", "--json", check=False)
    if r.returncode == 0:
        try:
            m = json.loads(r.stdout)
            record("D", "metrics", "ok",
                   reqs=m.get("requirements", {}).get("total"),
                   by_kind=m.get("requirements", {}).get("by_kind") or "n/a")
        except json.JSONDecodeError:
            record("D", "metrics", "error", reason="parse")


# ---------------------------------------------------------------------------

def main() -> None:
    phase_a()
    phase_b()
    phase_c()
    phase_d()
    RESULTS_PATH.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    n_ok = sum(1 for r in results if r["outcome"] == "ok")
    n_err = sum(1 for r in results if r["outcome"] == "error")
    n_skip = sum(1 for r in results if r["outcome"] == "skipped")
    print(f"\nResults: {n_ok} ok, {n_err} error, {n_skip} skipped")
    print(f"Saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
