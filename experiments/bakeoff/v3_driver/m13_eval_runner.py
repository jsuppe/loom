#!/usr/bin/env python3
"""
M13 eval-set runner — runs subject + judge stages on a locked
eval-set, producing a single results JSON suitable for
comparison against the eval-set's pinned baseline.

This is the production loop: once an eval set (e.g. m13_v1) is
locked, running the eval is one command. No generation, no
labeling — just: load scenarios, ask the subject, score with
the judge, report.

Usage:
    python m13_eval_runner.py \\
        --eval-set experiments/bakeoff/eval_sets/m13_v1/scenarios.json \\
        --model ollama:qwen3.5:latest \\
        --out experiments/bakeoff/runs-v3/myresult.json

    # Or with a tag for the output filename:
    python m13_eval_runner.py --eval-set m13_v1 --tag haiku-fp-fix

The runner is intentionally narrow: it doesn't curate, doesn't
label, doesn't compare. Use m13_eval_curate.py to grow eval
sets and m13_eval_compare.py to diff results.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
sys.path.insert(0, str(LOOM_DIR / "src"))
sys.path.insert(0, str(LOOM_DIR / "experiments" / "bakeoff" / "v3_driver"))

from ph_m13_4_synthetic_validation import (  # noqa: E402
    stage_subject, stage_judge, analyse, _default_model,
)


def _resolve_eval_set(arg: str) -> Path:
    """Accept either a direct path or a v1-style identifier
    that maps to experiments/bakeoff/eval_sets/<id>/scenarios.json."""
    p = Path(arg)
    if p.exists():
        return p
    # Try as eval-set ID
    candidate = (
        LOOM_DIR / "experiments" / "bakeoff" / "eval_sets" / arg
        / "scenarios.json"
    )
    if candidate.exists():
        return candidate
    raise SystemExit(f"eval-set not found: {arg} (tried {p} and {candidate})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--eval-set", required=True,
                   help="Path or ID (e.g. m13_v1) of the locked eval-set")
    p.add_argument("--model", default=None,
                   help="Subject + judge model (default: env-resolved)")
    p.add_argument("--subject-model", default=None,
                   help="Override subject model only")
    p.add_argument("--judge-model", default=None,
                   help="Override judge model only")
    p.add_argument("--out", default=None,
                   help="Output path (default: runs-v3/eval_<id>_<tag>.json)")
    p.add_argument("--tag", default=None,
                   help="Short tag for the output filename")
    args = p.parse_args(argv)

    eval_path = _resolve_eval_set(args.eval_set)
    eval_dir = eval_path.parent
    eval_id = eval_dir.name

    # Load locked scenarios
    eval_data = json.loads(eval_path.read_text(encoding="utf-8"))
    scenarios = eval_data.get("scenarios", [])
    if not scenarios:
        print(f"❌ no scenarios in {eval_path}")
        return 1

    base_model = args.model or _default_model()
    subject_model = args.subject_model or base_model
    judge_model = args.judge_model or base_model

    print(f"=== M13 eval runner ===")
    print(f"  eval_set:      {eval_id} ({eval_path})")
    print(f"  scenarios:     {len(scenarios)}")
    print(f"  subject_model: {subject_model}")
    print(f"  judge_model:   {judge_model}")
    print()

    started = datetime.now(timezone.utc).isoformat()

    # Don't mutate the original scenarios — clone.
    scen_copy = [dict(s) for s in scenarios]

    # Stage 3 + 4
    scen_copy = stage_subject(scen_copy, subject_model)
    scen_copy = stage_judge(scen_copy, judge_model)

    summary = analyse(scen_copy)
    summary["started_at"] = started
    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["eval_set"] = eval_id
    summary["eval_set_path"] = str(eval_path)
    summary["subject_model"] = subject_model
    summary["judge_model"] = judge_model
    summary["scenarios"] = scen_copy

    # Resolve output path
    out_path: Path
    if args.out:
        out_path = Path(args.out)
    else:
        out_dir = LOOM_DIR / "experiments" / "bakeoff" / "runs-v3"
        out_dir.mkdir(parents=True, exist_ok=True)
        tag = args.tag or "run"
        # Sanitize model name for filename
        m_safe = subject_model.replace(":", "_").replace("/", "_")
        out_path = out_dir / f"eval_{eval_id}_{m_safe}_{tag}.json"
    out_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Pretty print summary
    print()
    print("=== Summary ===")
    print(f"  Ambiguous (gen vs labeler disagree): "
          f"{summary['n_ambiguous']} / {summary['n_total']}")
    print()
    cl = summary["confusion_loose"]; ml = summary["metrics_loose"]
    cs = summary["confusion_strict"]; ms = summary["metrics_strict"]
    print(f"  LOOSE:  TP={cl['TP']} FP={cl['FP']} FN={cl['FN']} TN={cl['TN']}  "
          f"P={ml['precision']} R={ml['recall']} F1={ml['f1']} FPR={ml['fpr']}")
    print(f"  STRICT: TP={cs['TP']} FP={cs['FP']} FN={cs['FN']} TN={cs['TN']}  "
          f"P={ms['precision']} R={ms['recall']} F1={ms['f1']} FPR={ms['fpr']}")
    print()
    print("  By stratum (drift_pause / completed / baked):")
    for stratum, s in summary["by_stratum"].items():
        print(f"    {stratum:<28} n={s['n']:>3}  "
              f"drift_pause={s['paused_drift_pct']:>5.1f}%  "
              f"completed={s['completed_pct']:>5.1f}%  "
              f"baked={s['baked_pct']:>5.1f}%")
    print()
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
