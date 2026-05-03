#!/usr/bin/env python3
"""
Dogfood the M11 capture mechanism on our own prompt-engineering
lessons. Goals:

  1. Capture each of the 9 lessons (+ meta-takeaway) as Loom
     requirements via the actual `loom extract` CLI.
  2. Chain them via --derives-from so the dependency graph is
     in the store.
  3. Log every friction point hit — inputs that didn't fit the
     existing model, awkward workarounds, missing fields.

Output:
  - {lesson_id → req_id} mapping printed
  - friction notes printed (and saved to companion .md)
  - Records the captured req_ids so a follow-up `loom link` pass
    can wire harness scripts to lessons.
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

# Friction log — captured as we encounter awkwardness in the
# current Loom model.
FRICTION: list[str] = []


# Each lesson: (key, domain, imperative-shaped value, rationale,
# list of dep keys for --derives-from). Dep keys map to other
# lessons in this list.
LESSONS = [
    ("L0_meta", "architecture",
     "Loom's value-add is delivering captured rationale to the agent at the right moment. Storage alone produces zero compliance lift; prompt assembly carries the entire effect.",
     "M8.1 D-smoke (FINDINGS-bakeoff-v2-pythonfirst-smoke.md): D2 (stored, undelivered) = 0% compliance, D3 (stored AND injected via task_build_prompt) = 95%. Same data in store; the 95pp swing was prompt assembly. This is the meta-finding the entire M11 design pattern is built on.",
     []),

    ("L1_rationale", "behavior",
     "Loom requirements MUST include rationale (prose or rationale_links). Bare-rule reqs without rationale produce 0% compliance on contrarian specs. Equivocal rationale is worse than no rationale.",
     "M10.3 phQ3-phQ7 series: bare rule = 0%, rule + rationale = 100% saturation. phS anti-rationale ablation: ANTI_SOFT (equivocal) drops compliance to 0% (worse than 30% placebo baseline). phR rhetorical ablation: the framing-defuser sentence carries 20pp on its own (most leveraged single feature). Three sharpening iterations: M8.1 → phR → phS.",
     ["L0_meta"]),

    ("L7_context_amplifies", "behavior",
     "Loom context-bundle additions (semantic indexers, file refs, type defs) MUST be treated as conditional reinforcement of explicit instructions, not as substitutes for them. Adding context cannot manufacture rule compliance when the rule is missing or weak.",
     "phQ3/phQ4/phQ5 series: indexer alone with bare rule = 0% compliance regardless of richness. Indexer + rationale-augmented prompt = 100%. The indexer's job is amplification, not generation. A weak instruction with rich context still fails; a strong instruction with rich context saturates.",
     ["L1_rationale"]),

    ("L6_test_refs", "behavior",
     "JsIndexer (and similar LSP-backed indexers) MUST be pointed at the project root including test files, not at source-only subsets. Test files are uniquely high-signal context for code-gen prompts.",
     "phQ7: +40pp lift on placebo cell (30% → 70%) by including test_retry.js in the indexed workspace. No indexer code change needed. The test's `console.log('PASS: returns_null_on_failures')` functions as the closest thing to a contract in code form. PASS labels outperform bare assertions.",
     ["L7_context_amplifies"]),

    ("L3_placebo", "behavior",
     "Loom rationale capture should accept anything explanation-shaped; the presence of explanation matters more than its content quality on most scenarios. Don't gate capture on rationale-quality scoring (refining is post-hoc).",
     "phQ3 placebo cell: 90% compliance from length-matched filler text that just paraphrased the rule. Almost matches the 100% from real rationale. The placebo isn't even good prose. Implication: the friction tax of 'wait until rationale is well-written' is empirically not worth paying.",
     ["L1_rationale"]),

    ("L9_imperative_in_rule", "behavior",
     "High-stakes Loom rules (security, compliance, contractual) MUST be written with absolute imperative wording inside the rule itself. Use BOTH a rhetorical opener (e.g., 'STRICT REQUIREMENT — NON-NEGOTIABLE:') AND an inline action-verb imperative (e.g., 'You MUST NOT under any circumstances'). Either alone produces ~60% compliance against anti-rationale; both combined produce 100%.",
     "phT N=60: R_imperative (full kit) = 100% compliance against ANTI_SOFT, vs 0% baseline. R_meta_preamble (top-of-prompt authority hierarchy) = 0% — meta-instructions don't work in raw-prompt mode. phU N=50: length-controlled variants (prefix-only or inline-only) each score 60%, confirming both components contribute and the lift isn't a length effect. Recipe generalizes across anti-rationale shapes (R_imperative + ANTI_HARD = 100%).",
     ["L1_rationale"]),

    ("L8_capture_at_source", "architecture",
     "Rationale capture MUST happen at chat intake (UserPromptSubmit hook), not deferred to manual `loom extract` calls. Users skip manual capture; the discipline must transfer from human to harness.",
     "M11.5 raison d'être. Every lesson on this list says rationale is load-bearing, but users skip capturing it. M11.5 P0 pilot: 95.2% precision on requirement classification = the harness can capture without pulling humans out of flow. The intake hook is the operationalization of this lesson.",
     ["L1_rationale"]),

    ("L2_bigger_not_better", "architecture",
     "Loom executor selection MUST consider spec contrarian-shape, not just language. Code-specialist models (e.g. qwen2.5-coder:32b) lose to general-purpose models (qwen3.5:latest) by 20-30pp on contrarian-rule cells without rationale. The right executor depends on whether the spec aligns with conventional code practice or fights it.",
     "phQ4: qwen2.5-coder:32b vs qwen3.5:latest, both with no stub: on-rule -20pp, +placebo -30pp at 32b. The bigger code-specialist's training priors fight contrarian rules. With rationale present, 32b wins (+20pp on rat). So executor selection should depend on whether rationale-augmentation is reliable (use specialist) or not (use general).",
     []),

    ("L4_guardrails", "architecture",
     "LLM-classified outputs in Loom MUST be wrapped in deterministic guardrails before consumption. Don't try to make the LLM perfect via prompt iteration; build a layered system where deterministic code catches the LLM's predictable mistakes.",
     "M11.5 P0 classifier: 95.2% precision, single false positive on hedge-language ('Make this faster if possible'). The fix was a regex guardrail downstream, NOT prompt iteration. The intake hook ships with five layered guardrails (precision threshold, domain whitelist, softener detection, daily budget, reversibility surface) — together more reliable than any single prompt-engineering pass.",
     []),

    ("L5_schema_advisory", "architecture",
     "Schema enums on LLM output (e.g. classifier domain field) MUST have downstream tolerance for off-enum values. The prompt is a hint, not a contract; treat any structured-output field as 'best-effort with an unknown bucket.'",
     "M11.5 P0: classifier was told domain MUST be one of behavior|ui|data|architecture|terminology, invented `security` 2/20 times on true positives. The fix was downstream routing (out-of-enum → propose branch, not crash), not a stricter prompt. Generalizes to any constrained-output field.",
     ["L4_guardrails"]),
]


def run_extract(domain: str, value: str, rationale: str, links: list[str]) -> dict:
    """Run the actual `loom extract` CLI and parse JSON. This is the
    dogfooding entry point — exercises the user-facing tool, not the
    underlying services.extract."""
    # Loom's extract reads stdin in REQUIREMENT: domain | text shape.
    stdin_text = f"REQUIREMENT: {domain} | {value}"
    args = [
        sys.executable, "-m", "loom.cli",
        "-p", PROJECT,
        "extract",
        "--rationale", rationale,
    ]
    for link in links:
        args.extend(["--derives-from", link])
    proc = subprocess.run(
        args, input=stdin_text, capture_output=True, text=True,
        encoding="utf-8", cwd=str(LOOM_DIR),
    )
    return {
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "returncode": proc.returncode,
        "value": value,
        "domain": domain,
    }


def predicted_req_id(domain: str, value: str) -> str:
    """Mirror the deterministic ID hash so we can resolve mappings
    without --json output (which the extract CLI doesn't emit cleanly)."""
    import hashlib as _h
    return f"REQ-{_h.sha256(f'{domain.strip().lower()}:{value.strip()}'.encode()).hexdigest()[:8]}"


def main() -> int:
    print(f"=== Dogfooding the M11 capture mechanism on prompt-engineering lessons ===")
    print(f"Project: {PROJECT}")
    print(f"Lessons to capture: {len(LESSONS)}")
    print()

    captured: dict[str, str] = {}  # lesson key → req_id

    for key, domain, value, rationale, dep_keys in LESSONS:
        # Resolve dependency keys to req_ids.
        link_ids = []
        for dk in dep_keys:
            if dk not in captured:
                FRICTION.append(
                    f"Lesson {key} declares dependency on {dk} but it "
                    f"hasn't been captured yet. (Fix the order of LESSONS or "
                    f"the chain is broken.)"
                )
                continue
            link_ids.append(captured[dk])

        # FRICTION CHECK: lesson is a finding, not an imperative
        # requirement. We're forced to translate it into "Loom MUST..."
        # imperative shape to fit the current Requirement model.
        if not value.startswith(("Loom requirements MUST",
                                  "Loom rules", "Loom executor",
                                  "Loom context-bundle", "Loom rationale",
                                  "JsIndexer", "Rationale capture",
                                  "LLM-classified outputs",
                                  "Schema enums",
                                  "High-stakes Loom rules",
                                  "Loom's value-add")):
            # Unlikely with our crafted values, but flagged in principle.
            FRICTION.append(
                f"Lesson {key}'s value text doesn't start with an imperative "
                f"about Loom — current model assumes requirements direct system "
                f"behavior, not findings about it."
            )

        result = run_extract(domain, value, rationale, link_ids)
        if result["returncode"] != 0:
            print(f"ERROR capturing {key}:")
            print(f"  stderr: {result['stderr'][-500:]}")
            FRICTION.append(
                f"Lesson {key} failed to capture: {result['stderr'][-200:]}"
            )
            continue

        # Get the actual req_id from the deterministic hash.
        req_id = predicted_req_id(domain, value)
        captured[key] = req_id

        # Look at stdout for the warnings we expect.
        out = result["stdout"]
        if "rationale_needed" in out:
            FRICTION.append(
                f"Lesson {key} captured as rationale_needed despite passing "
                f"--rationale — that's the gate logic working but might be "
                f"unexpected."
            )

        marker = "✓"
        print(f"  {marker} {key}: {req_id}  [{domain}]")
        if link_ids:
            print(f"      derives from: {', '.join(link_ids)}")
        print(f"      value: {value[:100]}{'...' if len(value) > 100 else ''}")

    print()
    print("=== Captured mapping ===")
    for key, req_id in captured.items():
        print(f"  {key:<25} {req_id}")

    if FRICTION:
        print()
        print("=== Friction encountered ===")
        for f in FRICTION:
            print(f"  • {f}")

    # Save the mapping for the linker pass.
    out_path = LOOM_DIR / "experiments" / "pilot" / "dogfood_lessons_mapping.json"
    out_path.write_text(json.dumps(captured, indent=2), encoding="utf-8")
    print()
    print(f"Mapping written to: {out_path}")

    # Save friction notes.
    friction_path = LOOM_DIR / "experiments" / "pilot" / "dogfood_friction.md"
    friction_path.write_text(
        "# Dogfooding friction log\n\n"
        + "Encountered while capturing 9 prompt-engineering lessons + meta-takeaway "
        + "as Loom requirements.\n\n"
        + "\n".join(f"- {f}" for f in FRICTION)
        + "\n",
        encoding="utf-8",
    )
    print(f"Friction notes written to: {friction_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
