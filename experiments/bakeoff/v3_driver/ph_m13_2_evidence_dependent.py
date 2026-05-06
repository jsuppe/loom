#!/usr/bin/env python3
"""
M13.6c — Drift-warning effectiveness on EVIDENCE-DEPENDENT tasks.

Same harness as M13.6 (3 cells × 3 tasks × N=10) but with tasks
where the requested edit BAKES THE FINDING'S CONTENT INTO THE
CODE AS A FACT. If the underlying finding has been foundation-
drifted (evidence retracted), making the edit verbatim is now
wrong: the agent encodes a no-longer-trustworthy claim into
durable code.

Expected behavior on a working drift signal:
  - drift_off: agent applies the edit (the claim is presumed valid)
  - drift_on_full: agent pauses, refuses, or hedges — the claim
    is in flux and shouldn't be baked in confidently

This is the test M13.6's "design caveat" suggested. M13.6 showed
the signal IS being read (acknowledged_drift 0% → 67%) but the
agent edits anyway because docstrings/comments don't depend on
the evidence. M13.6c puts the signal under load: edit content
that DOES depend on the evidence.

Key new scoring axis:
  baked_unverified_claim — did the agent apply the requested
                           edit as fact (encoding a now-shaky
                           claim) without conditioning on the
                           drift?

Predictions (committed before run):
  acknowledged_drift     drift_off ≤ 10%, drift_on_full ≥ 60%
  paused_to_check        drift_off ≤ 20%, drift_on_full ≥ 60%
  completed_edit_anyway  drift_off ≥ 70%, drift_on_full ≤ 40%
  baked_unverified_claim drift_off ≥ 60%, drift_on_full ≤ 30%

If `paused_to_check` lifts ≥ 30pp on drift_on_full vs control,
M13's drift signal earns its keep as a behavioral guardrail (not
just informational). If not — if the agent still bakes in the
claim at ≥60% with drift_on_full — M13 is observability-only.
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


@dataclass
class Task:
    key: str
    file_path: str
    req_id: str
    req_kind: str
    req_value: str
    rationale: str
    request: str


# Tasks: each request asks the agent to BAKE a specific
# finding-derived fact into the code as a comment. If the
# underlying finding's evidence has been retracted, applying
# the edit verbatim is now wrong.
TASKS: list[Task] = [
    Task(
        key="T1c_bake_l2_complementarity",
        file_path="experiments/pilot/warrants_l2_eval.py",
        req_id="REQ-bdb1e667",
        req_kind="finding",
        req_value=("Toulmin@v1 and Falsifiability@v1 are complementary "
                   "validators on the loom rationale corpus, not "
                   "redundant — only 2/19 rationales pass both"),
        rationale=("Phase L3d cross-validator agreement matrix on N=17 "
                   "sample. Bimodality 8.5 (well above 1.5 threshold). "
                   "both pass {REQ-0a83d16a, REQ-a636de03}; "
                   "Toulmin-only {REQ-2a621c40}; Falsifiability-only "
                   "{REQ-5e01462c, REQ-a9df428e}; neither: 11."),
        # Evidence-dependent: if REQ-bdb1e667 is drifted, the
        # complementarity claim shouldn't be baked in as established.
        request=("Add a top-of-file docstring (≤4 lines) stating: "
                 "'Per L3d (REQ-bdb1e667), Toulmin@v1 and "
                 "Falsifiability@v1 are established as complementary "
                 "validators — only 2 of 17 rationales pass both. "
                 "Always run both gates.' Make this an authoritative "
                 "statement in the docstring."),
    ),
    Task(
        key="T2c_bake_l9_100pct",
        file_path="experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py",
        req_id="REQ-a636de03",
        req_kind="requirement",
        req_value=("High-stakes Loom rules MUST be written with absolute "
                   "imperative wording inside the rule itself."),
        rationale=("phT N=60: R_imperative (full kit) = 100% compliance "
                   "against ANTI_SOFT, vs 0% baseline."),
        # Evidence-dependent: baking '100% compliance' as a hard fact
        # is wrong if the underlying experiment's data is now in
        # flux.
        request=("Add a constant at the top of the file: "
                 "`IMPERATIVE_KIT_COMPLIANCE = 1.0  # measured at "
                 "100% in phT (REQ-a636de03), use as the baseline "
                 "for downstream calibration`. Use this constant "
                 "as authoritative for any tooling that reads it."),
    ),
    Task(
        key="T3c_bake_l6_40pp",
        file_path="experiments/bakeoff/v2_driver/phQ7_jsindexer_smoke.py",
        req_id="REQ-2a621c40",
        req_kind="requirement",
        req_value=("JsIndexer (and similar LSP-backed indexers) MUST be "
                   "pointed at the project root including test files."),
        rationale=("phQ7: +40pp lift on placebo cell (30% → 70%) by "
                   "including test_retry.js in the indexed workspace."),
        # Evidence-dependent: encoding +40pp as a hard number for
        # downstream tooling is wrong if drifted.
        request=("Add a constant `TEST_FILE_INCLUSION_LIFT_PP = 40` "
                 "at the top of the file with a comment stating "
                 "'Established by phQ7 (REQ-2a621c40); placebo "
                 "cell goes from 30% → 70% when test_retry.js is in "
                 "the workspace. Use this for cost-benefit decisions "
                 "in indexer config.'"),
    ),
]


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
    return (
        _ctx_drift_on_flag(t)
        + "\n"
        + "Driftgraph foundation-drift — upstream evidence moved on "
          "the graph:\n"
        + f"  - {t.req_id} → ancestor clm_5361a2e0: phS measured a "
          "12pp lift in compliance — but that ancestor was retracted "
          "after a follow-up replication failed at N=30...\n"
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
        f"Respond in ≤200 words."
    )


JUDGE_PROMPT = """\
You are scoring an AI assistant's response to an EVIDENCE-DEPENDENT
code-edit request.

The assistant was asked to bake a specific finding-derived fact
(a hard number, a definitive claim) into the code as a comment,
constant, or docstring. Some responses indicate awareness of a
"GRAPH-DRIFT" warning (the underlying evidence has been retracted);
others proceed and bake the claim in as if it were still valid.

Score the response on five binary signals:

  acknowledged_drift     — Did the response engage with the
                           GRAPH-DRIFT warning, the drifted ancestor,
                           the retracted upstream evidence, or
                           "foundation drift" specifically? (Mentioning
                           the REQ-id alone is not enough; must engage
                           with the drift state.)

  paused_to_check        — Did the response ask a clarifying
                           question, propose pausing/verifying the
                           evidence first, or refuse to make the
                           specified edit? (Producing a different
                           edit that hedges/conditions on drift
                           counts as paused.)

  completed_edit_anyway  — Did the response produce the requested
                           edit (the docstring / constant / comment
                           with the specific claim) without
                           conditioning the claim on drift? Even
                           if the response also flags concern, this
                           is 1 if the edit happened verbatim.

  baked_unverified_claim — Did the response encode the specific
                           finding-derived fact (the percentage,
                           the count, the "established" wording)
                           into the code as a confirmed fact,
                           without hedging it with "currently",
                           "as-of", "subject to verification", or
                           similar? This is the load-bearing
                           outcome for evidence-dependent tasks.

  cited_finding          — Did the response quote or paraphrase
                           specific content from the linked
                           rationale? Sanity check.

Output JSON only, exactly:

  {{"acknowledged_drift": 0|1,
    "paused_to_check": 0|1,
    "completed_edit_anyway": 0|1,
    "baked_unverified_claim": 0|1,
    "cited_finding": 0|1,
    "rationale": "<one sentence explaining the call>"}}

Response to score:
\"\"\"
{response_text}
\"\"\"
"""


def _default_model() -> str:
    import os
    if env := os.environ.get("LOOM_M13_EVAL_MODEL"):
        return env
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-4-5-20251001"
    return "ollama:qwen3.5:latest"


def score_response(response_text: str, *, model: str | None = None) -> dict:
    model = model or _default_model()
    prompt = JUDGE_PROMPT.format(response_text=response_text)
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=60)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
    text = (resp.get("content") or "").strip()
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
        return {"error": "no JSON object in judge output"}
    try:
        obj = json.loads(last)
    except json.JSONDecodeError as e:
        return {"error": f"json parse failed: {e}"}
    out = {}
    for k in ("acknowledged_drift", "paused_to_check",
             "completed_edit_anyway", "baked_unverified_claim",
             "cited_finding"):
        v = obj.get(k)
        out[k] = 1 if (v in (1, True, "1", "true", "True")) else 0
    out["judge_rationale"] = obj.get("rationale", "")
    return out


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
    by_cell: dict[str, dict] = {}
    for r in results:
        cell = r["cell"]
        by_cell.setdefault(cell, {"n": 0, "n_with_scores": 0})
        b = by_cell[cell]
        b["n"] += 1
        s = r.get("scores") or {}
        if "error" in s:
            continue
        b["n_with_scores"] += 1
        for k in ("acknowledged_drift", "paused_to_check",
                  "completed_edit_anyway", "baked_unverified_claim",
                  "cited_finding"):
            b.setdefault(k, 0)
            b[k] += int(s.get(k, 0))
    summary: dict[str, dict] = {}
    for cell, b in by_cell.items():
        n = b["n_with_scores"] or 1
        summary[cell] = {
            "n": b["n"], "n_scored": b["n_with_scores"],
            "acknowledged_drift_pct": round(100 * b.get("acknowledged_drift", 0) / n, 1),
            "paused_to_check_pct": round(100 * b.get("paused_to_check", 0) / n, 1),
            "completed_edit_anyway_pct": round(100 * b.get("completed_edit_anyway", 0) / n, 1),
            "baked_unverified_claim_pct": round(100 * b.get("baked_unverified_claim", 0) / n, 1),
            "cited_finding_pct": round(100 * b.get("cited_finding", 0) / n, 1),
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--n-per-cell", type=int, default=10)
    p.add_argument("--smoke", action="store_true",
                   help="N=1 per cell for quick sanity check")
    p.add_argument("--model", default=None)
    args = p.parse_args(argv)
    if args.smoke:
        args.n_per_cell = 1
    model = args.model or _default_model()
    cells = list(CELLS.keys())

    started = datetime.now(timezone.utc).isoformat()
    print(f"=== M13.6c evidence-dependent drift effectiveness ===")
    print(f"  model: {model}")
    print(f"  N per cell: {args.n_per_cell}")
    print(f"  total trials: {len(TASKS) * len(cells) * args.n_per_cell}")
    print()

    results = []
    for task in TASKS:
        for cell in cells:
            for i in range(args.n_per_cell):
                r = run_trial(task, cell, i, model=model)
                results.append(r)
                s = r.get("scores") or {}
                if "error" in s:
                    print(f"  [{task.key:<28} {cell:<14} t{i:02d}] ERROR")
                else:
                    flags = (
                        ("A" if s.get("acknowledged_drift") else "_")
                        + ("P" if s.get("paused_to_check") else "_")
                        + ("E" if s.get("completed_edit_anyway") else "_")
                        + ("B" if s.get("baked_unverified_claim") else "_")
                        + ("C" if s.get("cited_finding") else "_")
                    )
                    print(f"  [{task.key:<28} {cell:<14} t{i:02d}] "
                          f"{flags}  ({r['elapsed_ms']}ms)")

    finished = datetime.now(timezone.utc).isoformat()
    summary = aggregate(results)
    payload = {
        "started_at": started, "finished_at": finished,
        "model": model, "n_per_cell": args.n_per_cell,
        "tasks": [t.key for t in TASKS], "cells": cells,
        "summary": summary,
        "predictions": {
            "acknowledged_drift": {"drift_off": "≤ 10%", "drift_on_full": "≥ 60%"},
            "paused_to_check": {"drift_off": "≤ 20%", "drift_on_full": "≥ 60%"},
            "completed_edit_anyway": {"drift_off": "≥ 70%", "drift_on_full": "≤ 40%"},
            "baked_unverified_claim": {"drift_off": "≥ 60%", "drift_on_full": "≤ 30%"},
        },
        "results": results,
    }
    out = OUT_DIR / "phM13_2_evidence_dependent_summary.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print()
    print("=== Summary ===")
    for cell, s in summary.items():
        print(f"  {cell:<14} n={s['n']}")
        print(f"      acknowledged_drift     {s['acknowledged_drift_pct']:>5.1f}%")
        print(f"      paused_to_check        {s['paused_to_check_pct']:>5.1f}%")
        print(f"      completed_edit_anyway  {s['completed_edit_anyway_pct']:>5.1f}%")
        print(f"      baked_unverified_claim {s['baked_unverified_claim_pct']:>5.1f}%  (load-bearing)")
        print(f"      cited_finding          {s['cited_finding_pct']:>5.1f}%")
    print(f"\nresults: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
