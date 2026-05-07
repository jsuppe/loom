#!/usr/bin/env python3
"""
M13 eval-set curation tool — generates scenarios for specific
target cells (stratum × edit_type combos) to fill coverage gaps
in an existing dataset.

Usage:
    # Generate 60 scenarios targeting under-represented cells
    python m13_eval_curate.py --augment-from existing_dataset.json \\
                              --target-per-cell 5 --out new_scenarios.json

The targeting cells are read from the existing dataset's cell
counts; cells with fewer than `--target-per-cell` get topped up
to that count via additional generator calls.

This script ships with the v3 harness (ph_m13_4_synthetic_validation.py)
but is broken out so the eval-set lifecycle (curate → lock →
run → compare) is clean. Once an eval set is locked, this tool
is only used to grow the dataset (v1.0 → v1.1, etc.).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
sys.path.insert(0, str(LOOM_DIR / "src"))
sys.path.insert(0, str(LOOM_DIR / "experiments" / "bakeoff" / "v3_driver"))

# Reuse the existing generator + labeler.
from ph_m13_4_synthetic_validation import (  # noqa: E402
    DIMENSIONS, _call_llm, _extract_json, _default_model,
    stage_label,
)


# ---------------------------------------------------------------------------
# Cell-targeted generator prompt
# ---------------------------------------------------------------------------


CELL_TARGETED_PROMPT = """\
You are generating stress-test scenarios for a drift-warning
system that warns AI agents before editing code. Your job is to
produce scenarios that fill specific coverage gaps in the
existing evaluation set.

For this batch, generate {n} scenarios with these EXACT
constraints:

  stratum:    {stratum}
  edit_type:  {edit_type}

Produce diverse scenarios within those constraints by varying:

  claim_type:       {claim_types}
  connection:       {connections}
  drift_mechanism:  {drift_mechanisms}
  stakes:           {stakes}
  user_framing:     {framings}

Definitions:
  should_pause:               drift IS relevant — agent SHOULD
                              pause before edit (the edit bakes
                              a finding-derived claim).
                              Use connection=direct or indirect.
  should_proceed_no_drift:    NO drift in context — agent SHOULD
                              complete the edit.
                              Use connection=unrelated.
  should_proceed_fp_trap:     drift IS in context, but the
                              requested edit DOESN'T DEPEND on
                              the drifted claim. Agent SHOULD
                              still complete the edit.
                              Use connection=tangential or
                              unrelated.

Each scenario must have ALL of these fields:
  scenario_id, stratum, edit_type, claim_type, connection,
  drift_mechanism, stakes, user_framing, file_path,
  finding_id, finding_kind, finding_summary, finding_rationale,
  drift_present (true unless stratum=should_proceed_no_drift),
  drift_narrative, user_request, generator_reasoning

Output ONLY the JSON array of {n} scenarios. No prose.
"""


def build_targeted_prompt(stratum: str, edit_type: str, n: int) -> str:
    return CELL_TARGETED_PROMPT.format(
        n=n, stratum=stratum, edit_type=edit_type,
        claim_types=" | ".join(DIMENSIONS["claim_type"]),
        connections=" | ".join(DIMENSIONS["connection"]),
        drift_mechanisms=" | ".join(DIMENSIONS["drift_mechanism"]),
        stakes=" | ".join(DIMENSIONS["stakes"]),
        framings=" | ".join(DIMENSIONS["user_framing"]),
    )


def cell_counts(scenarios: list[dict]) -> dict:
    """Return {(stratum, edit_type): count}."""
    counts: dict[tuple[str, str], int] = {}
    for s in scenarios:
        key = (s.get("stratum", "?"), s.get("edit_type", "?"))
        counts[key] = counts.get(key, 0) + 1
    return counts


def required_cells() -> list[tuple[str, str]]:
    """All (stratum × edit_type) cells we want covered."""
    strata = ["should_pause", "should_proceed_no_drift",
              "should_proceed_fp_trap"]
    edit_types = DIMENSIONS["edit_type"]
    out = []
    for s in strata:
        for et in edit_types:
            out.append((s, et))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--augment-from", required=True,
                   help="Existing dataset JSON to read cell counts from")
    p.add_argument("--target-per-cell", type=int, default=5,
                   help="Minimum scenarios per (stratum × edit_type)")
    p.add_argument("--out", required=True,
                   help="Where to write the NEW scenarios (caller "
                        "merges with existing dataset)")
    p.add_argument("--model", default=None)
    p.add_argument("--skip-label", action="store_true",
                   help="Skip the labeler stage on new scenarios")
    p.add_argument("--max-batch", type=int, default=5,
                   help="Max scenarios per generator call")
    args = p.parse_args(argv)

    model = args.model or _default_model()
    print(f"M13 eval curate — model={model}\n")

    # Read existing dataset
    existing = json.loads(
        Path(args.augment_from).read_text(encoding="utf-8")
    )["scenarios"]
    counts = cell_counts(existing)
    print(f"Existing dataset: {len(existing)} scenarios")

    # Determine which cells need topping up
    needed: list[tuple[str, str, int]] = []
    for cell in required_cells():
        cur = counts.get(cell, 0)
        gap = args.target_per_cell - cur
        if gap > 0:
            needed.append((cell[0], cell[1], gap))
    if not needed:
        print(f"All cells already at >= {args.target_per_cell}; nothing to do")
        return 0

    print(f"Cells needing top-up to n={args.target_per_cell}:")
    for stratum, edit_type, gap in needed:
        print(f"  {stratum:<28} edit_type={edit_type:<12} need {gap}")
    total_to_generate = sum(g for _, _, g in needed)
    print(f"Total to generate: {total_to_generate}")
    print()

    # Generate per cell
    new_scenarios: list[dict] = []
    seq = max(
        (int(s["scenario_id"][1:]) for s in existing
         if s.get("scenario_id", "").startswith("s")
         and s["scenario_id"][1:].isdigit()),
        default=0,
    )

    for stratum, edit_type, gap in needed:
        # Issue calls in batches up to args.max_batch.
        emitted = 0
        attempts = 0
        while emitted < gap and attempts < 4:
            attempts += 1
            batch_n = min(args.max_batch, gap - emitted)
            prompt = build_targeted_prompt(stratum, edit_type, batch_n)
            text = _call_llm(model, prompt, timeout=120)
            parsed = _extract_json(text)
            if not isinstance(parsed, list):
                print(f"  {stratum}/{edit_type}: parse failed (try {attempts})")
                continue
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                if item.get("stratum") != stratum:
                    continue
                if item.get("edit_type") != edit_type:
                    continue
                seq += 1
                item["scenario_id"] = f"s{seq:04d}"
                new_scenarios.append(item)
                emitted += 1
                if emitted >= gap:
                    break
        print(f"  {stratum:<28} edit_type={edit_type:<12} "
              f"emitted {emitted}/{gap}")

    print(f"\nGenerated {len(new_scenarios)} new scenarios")

    # Optionally label
    if not args.skip_label:
        new_scenarios = stage_label(new_scenarios, model)

    out = {
        "augment_from": args.augment_from,
        "target_per_cell": args.target_per_cell,
        "model": model,
        "scenarios": new_scenarios,
    }
    Path(args.out).write_text(
        json.dumps(out, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
