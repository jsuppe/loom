#!/usr/bin/env python3
"""
Pass 2 of the dogfooding: link experimental harness scripts to the
lesson reqs they validate.

Each harness script is the empirical evidence for one (or several)
lessons. `loom link` should record this so `loom trace` and `loom
chain` can navigate from a lesson to its supporting code, and
drift-detection can flag if a harness changes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
PROJECT = "loom"

FRICTION: list[str] = []

# Load the lesson_id → req_id mapping from pass 1.
mapping = json.loads(
    (LOOM_DIR / "experiments" / "pilot" / "dogfood_lessons_mapping.json")
    .read_text(encoding="utf-8")
)

# (harness path, [lesson_keys it validates])
HARNESS_LINKS = [
    ("experiments/bakeoff/v2_driver/phQ3_crosssession_js_stub_clean_smoke.py",
     ["L7_context_amplifies", "L1_rationale"]),
    ("experiments/bakeoff/v2_driver/phQ4_crosssession_js_no_stub_32b_smoke.py",
     ["L2_bigger_not_better", "L1_rationale"]),
    ("experiments/bakeoff/v2_driver/phQ7_crosssession_js_with_test_refs_smoke.py",
     ["L6_test_refs", "L7_context_amplifies"]),
    ("experiments/bakeoff/v2_driver/phR_rhetorical_ablation_smoke.py",
     ["L1_rationale"]),
    ("experiments/bakeoff/v2_driver/phS_anti_rationale_smoke.py",
     ["L1_rationale"]),
    ("experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py",
     ["L9_imperative_in_rule"]),
    ("experiments/bakeoff/v2_driver/phU_imperative_followups_smoke.py",
     ["L9_imperative_in_rule"]),
    ("experiments/pilot/intake_classifier_pilot.py",
     ["L4_guardrails", "L5_schema_advisory", "L8_capture_at_source"]),
    ("hooks/loom_intake.py",
     ["L8_capture_at_source", "L4_guardrails"]),
    ("src/loom/intake.py",
     ["L8_capture_at_source"]),
    ("src/loom/indexers_js.py",
     ["L6_test_refs", "L7_context_amplifies"]),
]


def link_one(file_path: str, req_ids: list[str]) -> dict:
    """Run `loom link <file> --req REQ-x [--req REQ-y ...]`."""
    args = [
        sys.executable, "-m", "loom.cli",
        "-p", PROJECT,
        "link", file_path,
    ]
    for rid in req_ids:
        args.extend(["--req", rid])
    proc = subprocess.run(
        args, capture_output=True, text=True,
        encoding="utf-8", cwd=str(LOOM_DIR),
    )
    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "file": file_path,
        "req_ids": req_ids,
    }


def main() -> int:
    print(f"=== Linking experimental harnesses to lesson reqs ===")
    print(f"Project: {PROJECT}")
    print(f"Harness files: {len(HARNESS_LINKS)}")
    print()

    success_count = 0
    for file_rel, lesson_keys in HARNESS_LINKS:
        file_abs = LOOM_DIR / file_rel
        if not file_abs.exists():
            FRICTION.append(
                f"{file_rel}: file does not exist — skipping link."
            )
            print(f"  ✗ {file_rel}: missing")
            continue

        # Resolve lesson keys to req_ids.
        req_ids = []
        for lk in lesson_keys:
            if lk not in mapping:
                FRICTION.append(
                    f"{file_rel}: lesson key {lk} not in mapping. Skipped."
                )
                continue
            req_ids.append(mapping[lk])

        if not req_ids:
            print(f"  ✗ {file_rel}: no resolvable lesson keys")
            continue

        # FRICTION: linking research-evidence files (harness scripts)
        # uses the same `loom link` mechanism designed for code that
        # IMPLEMENTS a requirement. Conceptually, harness scripts
        # PROVIDE EVIDENCE FOR a finding-shaped requirement. The
        # current model conflates these.
        result = link_one(str(file_abs), req_ids)
        if result["returncode"] != 0:
            print(f"  ✗ {file_rel}: link failed")
            print(f"      stderr: {result['stderr'][-200:]}")
            FRICTION.append(
                f"{file_rel}: link returned {result['returncode']}: "
                f"{result['stderr'][-200:]}"
            )
            continue

        print(f"  ✓ {file_rel}")
        print(f"      → {', '.join(req_ids)}  ({', '.join(lesson_keys)})")
        success_count += 1

    print()
    print(f"=== Linked {success_count}/{len(HARNESS_LINKS)} harnesses ===")

    if FRICTION:
        print()
        print("=== Friction encountered ===")
        for f in FRICTION:
            print(f"  • {f}")

    # Append friction notes to the existing log.
    friction_path = LOOM_DIR / "experiments" / "pilot" / "dogfood_friction.md"
    existing = friction_path.read_text(encoding="utf-8") if friction_path.exists() else ""
    extra = "\n## Pass 2: linking harnesses\n\n" + "\n".join(
        f"- {f}" for f in FRICTION
    ) + "\n"
    friction_path.write_text(existing + extra, encoding="utf-8")
    print()
    print(f"Friction log appended to: {friction_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
