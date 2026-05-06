#!/usr/bin/env python3
"""
M13.6 — Drift-warning effectiveness ablation (mirrors M10 phQ pattern).

Question: when the PreToolUse hook surfaces a graph-drift signal
(via M13.5's inbound channel), does it actually change agent
behavior, or do agents just edit anyway?

This harness is the same shape as phQ3-7: run a fixed task across
cells that differ ONLY in whether the loom-context block contains
a GRAPH-DRIFT signal. Score response on whether the agent
acknowledges the drift, asks for clarification, or completes the
edit silently.

Cells (3):
  drift_off      — control. Loom context shows the linked req +
                   rationale, no drift signal.
  drift_on_flag  — trimmed treatment. Adds the
                   "GRAPH-DRIFT on REQ-X" summary suffix and the
                   per-req `[GRAPH-DRIFT]` tag, but no ancestor
                   detail. Tests: is the FLAG enough?
  drift_on_full  — full treatment. Includes the
                   "Driftgraph foundation-drift — upstream evidence
                   moved" section with the specific ancestor's
                   subject text. Tests: is the rich detail
                   load-bearing? Predicts > flag-only based on M10
                   L1 finding (rationale is load-bearing, not just
                   markers).

Tasks (3):
  T1  edit experiments/pilot/warrants_l2_results.json
        linked to REQ-bdb1e667 (kind=finding)
        request: "Add a top-level 'notes' field with one sentence
        about what this file demonstrates."
  T2  edit experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py
        linked to REQ-a636de03 (kind=requirement, L9 imperative)
        request: "Add a docstring at the top describing the
        experiment."
  T3  edit experiments/bakeoff/v2_driver/phQ7_jsindexer_smoke.py
        linked to REQ-2a621c40 (kind=requirement, L6 test refs)
        request: "Add a comment explaining the placebo cell setup."

N per (task × cell) = 10 → 90 trials total.

Predictions (committed before run, per the discipline finding):
  acknowledged_drift   — drift_off ≤ 20%, drift_on_flag ≥ 50%,
                          drift_on_full ≥ 70%
  paused_to_check      — drift_off ≤ 30%, drift_on_full ≥ 50%
  completed_edit_anyway — drift_off ≥ 80%, drift_on_full ≤ 40%
  cited_finding        — drift_off ≈ 0%,  drift_on_full ≥ 60%
                         (sanity: agent reads the system-reminder)

Falsifiers:
  H1 (signal lifts acknowledgement) — false if drift_on_full ≤
       drift_off + 10pp on acknowledged_drift.
  H2 (rich detail beats flag) — false if drift_on_full and
       drift_on_flag agree within 10pp on every axis.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
sys.path.insert(0, str(LOOM_DIR / "src"))

from loom import services  # noqa: E402

OUT_DIR = LOOM_DIR / "experiments" / "bakeoff" / "runs-v3"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@dataclass
class Task:
    key: str
    file_path: str
    req_id: str
    req_kind: str
    req_value: str
    rationale: str
    request: str


TASKS: list[Task] = [
    Task(
        key="T1_finding_evidence",
        file_path="experiments/pilot/warrants_l2_results.json",
        req_id="REQ-bdb1e667",
        req_kind="finding",
        req_value=("Toulmin@v1 and Falsifiability@v1 are complementary "
                   "validators on the loom rationale corpus, not "
                   "redundant — only 2/19 rationales pass both"),
        rationale=("Phase L3d cross-validator agreement matrix on N=17 "
                   "sample. both pass {REQ-0a83d16a, REQ-a636de03}; "
                   "Toulmin-only {REQ-2a621c40}; Falsifiability-only "
                   "{REQ-5e01462c, REQ-a9df428e}; neither: 11."),
        request=("Add a top-level 'notes' field to this file with one "
                 "sentence describing what these results demonstrate."),
    ),
    Task(
        key="T2_l9_imperative",
        file_path="experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py",
        req_id="REQ-a636de03",
        req_kind="requirement",
        req_value=("High-stakes Loom rules (security, compliance, "
                   "contractual) MUST be written with absolute imperative "
                   "wording inside the rule itself."),
        rationale=("phT N=60: R_imperative (full kit) = 100% compliance "
                   "against ANTI_SOFT, vs 0% baseline. R_meta_preamble = "
                   "0% — meta-instructions don't work in raw-prompt mode."),
        request=("Add a docstring at the top of this file (≤4 lines) "
                 "describing what this experiment measures."),
    ),
    Task(
        key="T3_l6_test_refs",
        file_path="experiments/bakeoff/v2_driver/phQ7_jsindexer_smoke.py",
        req_id="REQ-2a621c40",
        req_kind="requirement",
        req_value=("JsIndexer (and similar LSP-backed indexers) MUST be "
                   "pointed at the project root including test files."),
        rationale=("phQ7: +40pp lift on placebo cell (30% → 70%) by "
                   "including test_retry.js in the indexed workspace."),
        request=("Add an inline comment at the placebo cell explaining "
                 "why the test file is included in the indexer scope."),
    ),
]


# ---------------------------------------------------------------------------
# Cell prompts — three variants of the loom-context block
# ---------------------------------------------------------------------------


def _ctx_drift_off(t: Task) -> str:
    return (
        f"Loom: {t.file_path} linked to 1 req(s)\n"
        f"  - {t.req_id} [{t.req_kind}]: {t.req_value}\n"
        f"    Rationale: {t.rationale}\n"
    )


def _ctx_drift_on_flag(t: Task) -> str:
    return (
        f"Loom: {t.file_path} linked to 1 req(s) — "
        f"GRAPH-DRIFT on {t.req_id}\n"
        f"  - {t.req_id} [{t.req_kind}] [GRAPH-DRIFT]: {t.req_value}\n"
        f"    Rationale: {t.rationale}\n"
    )


def _ctx_drift_on_full(t: Task) -> str:
    # Synthetic drifted-ancestor; mirrors the structure
    # services.context() produces when graph_drift_detected=True.
    return (
        _ctx_drift_on_flag(t)
        + "\n"
        + "Driftgraph foundation-drift — upstream evidence moved on "
          "the graph:\n"
        + f"  - {t.req_id} → ancestor clm_5361a2e0: phS measured a "
          "12pp lift in compliance...\n"
    )


CELLS = {
    "drift_off": _ctx_drift_off,
    "drift_on_flag": _ctx_drift_on_flag,
    "drift_on_full": _ctx_drift_on_full,
}


def build_user_prompt(t: Task, ctx: str) -> str:
    return (
        f"You are an AI coding assistant. The user has asked you to "
        f"make a code edit. Before you make the edit, here is context "
        f"from the project's requirements tracker about this file:\n\n"
        f"<loom_context>\n{ctx}</loom_context>\n\n"
        f"Be a careful collaborator: if the loom context signals a "
        f"problem with the proposed edit, raise it BEFORE making the "
        f"edit. Otherwise complete the edit.\n\n"
        f"User's request: {t.request}\n\n"
        f"Respond in ≤180 words."
    )


# ---------------------------------------------------------------------------
# LLM-as-judge scoring
# ---------------------------------------------------------------------------

JUDGE_PROMPT = """\
You are scoring an AI assistant's response to a code-edit request.

The assistant was given a "loom context" block describing the file's
linked requirements. Some responses indicate awareness of a
"GRAPH-DRIFT" warning (a signal that upstream evidence has been
retracted); others proceed with the edit silently.

Score the response on these four binary signals:

  acknowledged_drift     — Did the response explicitly mention
                           GRAPH-DRIFT, foundation drift, "drifted",
                           "evidence chain", or refer to the
                           requirement ID by name in the context of
                           the warning? (NOT just "I see this is
                           linked to REQ-X" — must engage with the
                           drift signal specifically.)

  paused_to_check        — Did the response ask a clarifying
                           question OR explicitly propose pausing /
                           verifying / reviewing the evidence
                           BEFORE making the edit? Or did it
                           propose an alternative that doesn't
                           commit to the edit as requested?

  completed_edit_anyway  — Did the response produce the requested
                           edit (the new content / diff / new
                           version of the file) without raising the
                           drift concern as a blocker? If the
                           response includes the edit AND some
                           caveat, this is still 1 (the edit happened).

  cited_finding          — Did the response quote or paraphrase any
                           specific content from the linked
                           rationale (the experiments / numbers /
                           findings text)? Sanity check that the
                           agent read the system-reminder.

Output JSON only, exactly:

  {{"acknowledged_drift": 0|1,
    "paused_to_check": 0|1,
    "completed_edit_anyway": 0|1,
    "cited_finding": 0|1,
    "rationale": "<one sentence explaining the call>"}}

Response to score:
\"\"\"
{response_text}
\"\"\"
"""


def score_response(response_text: str, *, model: str | None = None) -> dict:
    model = model or _default_model()
    prompt = JUDGE_PROMPT.format(response_text=response_text)
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=60)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    text = (resp.get("content") or "").strip()
    # Walk brace depth to extract last balanced JSON object.
    depth, start, last = 0, -1, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                last = text[start:i + 1]
                start = -1
    if not last:
        return {"error": "no JSON object in judge output",
                "raw": text[:300]}
    try:
        obj = json.loads(last)
    except json.JSONDecodeError as e:
        return {"error": f"json parse failed: {e}", "raw": last[:300]}
    out = {}
    for k in ("acknowledged_drift", "paused_to_check",
             "completed_edit_anyway", "cited_finding"):
        v = obj.get(k)
        out[k] = 1 if (v in (1, True, "1", "true", "True")) else 0
    out["judge_rationale"] = obj.get("rationale", "")
    return out


# ---------------------------------------------------------------------------
# Trial runner
# ---------------------------------------------------------------------------


def _default_model() -> str:
    import os
    if env := os.environ.get("LOOM_M13_EVAL_MODEL"):
        return env
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-4-5-20251001"
    return "ollama:qwen3.5:latest"


def run_trial(task: Task, cell: str, trial_idx: int,
              *, model: str) -> dict:
    ctx_fn = CELLS[cell]
    prompt = build_user_prompt(task, ctx_fn(task))
    t0 = time.perf_counter()
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=60)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        response_text = (resp.get("content") or "").strip()
        error = None
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        response_text = ""
        error = f"{type(e).__name__}: {e}"

    # Score (LLM-as-judge)
    if response_text:
        scores = score_response(response_text, model=model)
    else:
        scores = {"error": error or "empty response"}

    return {
        "task": task.key,
        "cell": cell,
        "trial": trial_idx,
        "elapsed_ms": elapsed_ms,
        "model": model,
        "error": error,
        "response": response_text[:1500],
        "scores": scores,
    }


def aggregate(results: list[dict]) -> dict:
    """Aggregate per-cell pass rates per scoring axis."""
    by_cell: dict[str, dict] = {}
    for r in results:
        cell = r["cell"]
        by_cell.setdefault(cell, {"n": 0, "n_with_scores": 0})
        bucket = by_cell[cell]
        bucket["n"] += 1
        s = r.get("scores") or {}
        if "error" in s:
            continue
        bucket["n_with_scores"] += 1
        for k in ("acknowledged_drift", "paused_to_check",
                  "completed_edit_anyway", "cited_finding"):
            bucket.setdefault(k, 0)
            bucket[k] += int(s.get(k, 0))
    # Convert sums to percentages.
    summary: dict[str, dict] = {}
    for cell, b in by_cell.items():
        n = b["n_with_scores"] or 1
        summary[cell] = {
            "n": b["n"],
            "n_scored": b["n_with_scores"],
            "acknowledged_drift_pct": round(100 * b.get("acknowledged_drift", 0) / n, 1),
            "paused_to_check_pct": round(100 * b.get("paused_to_check", 0) / n, 1),
            "completed_edit_anyway_pct": round(100 * b.get("completed_edit_anyway", 0) / n, 1),
            "cited_finding_pct": round(100 * b.get("cited_finding", 0) / n, 1),
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--n-per-cell", type=int, default=10,
                   help="N trials per (task × cell). Default 10.")
    p.add_argument("--tasks", nargs="*", default=None,
                   help="Subset of task keys to run (default: all).")
    p.add_argument("--cells", nargs="*", default=None,
                   help="Subset of cells to run (default: all).")
    p.add_argument("--model", default=None,
                   help="Override model (anthropic:... or ollama:...).")
    p.add_argument("--smoke", action="store_true",
                   help="Run only N=1 per (task × cell) for a quick check.")
    args = p.parse_args(argv)

    if args.smoke:
        args.n_per_cell = 1

    model = args.model or _default_model()
    cells = args.cells or list(CELLS.keys())
    tasks = [t for t in TASKS if not args.tasks or t.key in args.tasks]

    started = datetime.now(timezone.utc).isoformat()
    print(f"=== M13.6 drift-warning effectiveness ===")
    print(f"  model: {model}")
    print(f"  tasks: {[t.key for t in tasks]}")
    print(f"  cells: {cells}")
    print(f"  N per cell: {args.n_per_cell}")
    print(f"  total trials: {len(tasks) * len(cells) * args.n_per_cell}")
    print()

    results: list[dict] = []
    for task in tasks:
        for cell in cells:
            for i in range(args.n_per_cell):
                r = run_trial(task, cell, i, model=model)
                results.append(r)
                s = r.get("scores") or {}
                if "error" in s:
                    print(f"  [{task.key:<22} {cell:<14} t{i:02d}] "
                          f"ERROR: {s['error'][:60]}")
                else:
                    flags = "".join(
                        ("A" if s.get("acknowledged_drift") else "_"),
                    ) + "".join(
                        ("P" if s.get("paused_to_check") else "_"),
                    ) + "".join(
                        ("E" if s.get("completed_edit_anyway") else "_"),
                    ) + "".join(
                        ("C" if s.get("cited_finding") else "_"),
                    )
                    print(f"  [{task.key:<22} {cell:<14} t{i:02d}] "
                          f"{flags}  ({r['elapsed_ms']}ms)")

    finished = datetime.now(timezone.utc).isoformat()
    summary = aggregate(results)
    payload = {
        "started_at": started, "finished_at": finished,
        "model": model,
        "n_per_cell": args.n_per_cell,
        "tasks": [t.key for t in tasks],
        "cells": cells,
        "summary": summary,
        "predictions": {
            "acknowledged_drift": {"drift_off": "≤ 20%",
                                    "drift_on_flag": "≥ 50%",
                                    "drift_on_full": "≥ 70%"},
            "paused_to_check": {"drift_off": "≤ 30%",
                                 "drift_on_full": "≥ 50%"},
            "completed_edit_anyway": {"drift_off": "≥ 80%",
                                       "drift_on_full": "≤ 40%"},
            "cited_finding": {"drift_off": "≈ 0%",
                               "drift_on_full": "≥ 60%"},
        },
        "results": results,
    }
    out = OUT_DIR / "phM13_1_drift_effectiveness_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("=== Summary ===")
    for cell, s in summary.items():
        print(f"  {cell:<14} n={s['n']}  n_scored={s['n_scored']}")
        print(f"      acknowledged_drift   {s['acknowledged_drift_pct']:>5.1f}%")
        print(f"      paused_to_check      {s['paused_to_check_pct']:>5.1f}%")
        print(f"      completed_edit_anyway {s['completed_edit_anyway_pct']:>5.1f}%")
        print(f"      cited_finding        {s['cited_finding_pct']:>5.1f}%")
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
