# M26 Pilot — Spec Quality Scorer on Loom-self

**Date:** 2026-06-06
**Pilot question:** Can the asymmetric pipeline (`loom decompose` + `loom_exec`) ship a real feature — a spec-quality scorer — into the loom repo itself, using only locally-runnable models?
**Verdict:** **Halted at dry-run inspection.** Seven concrete product gaps surfaced before a single LLM execution call, all reproducible and tracked as findings in the loom store. The pilot delivered substantial v2 design intel; the asymmetric-pipeline claim remains undertested pending Q-path.

## Pre-registration

- **REQ-6dec889f** — Loom must score Specification information-density on a 0-100 scale across four sub-dimensions and warn at create-time when below threshold.
- **SPEC-85e02906** — three-band contract: `median(high) > median(mid) > median(low)` strictly; separations high-low ≥ 50, high-mid ≥ 15, mid-low ≥ 15; canary 0 high <60, 0 low >60.
- **Calibration locked:** `tests/data/spec_scoring_calibration.json` (sha256 `28ba28d4ea83f72f8a40fa1ab66faa0af53fba78b41dae4829cfc6d06d3333a4`), 41 specs — 10 high hand-authored elaborating M11.5/M14/M15/M16/M16.3/M17.1/M20.1/M23/M24/M25; 21 mid sourced verbatim from the M25 LLM-migration corpus (naturally-occurring "concrete but thin"); 10 low hand-authored across distinct antipattern categories.
- **Grading test locked:** `tests/test_spec_scoring.py::TestSpecScoring` (7 assertions, α-mode eval-as-grading-test).
- **Commit:** `3fa829f` — landed BEFORE the scorer module existed; the import in the grading test fails as designed until `loom_exec` produces it.

## Methodology (per REQ-3896db58)

1. **Independent design review:** PARTIAL — the user (sole human reviewer) accepted the three-band redesign after I surfaced the empirical-corpus problem (21 of 22 existing specs have 0 acceptance criteria). The original binary good/bad design was killed pre-launch.
2. **Pre-registration:** locked in commit `3fa829f` with sha256 + explicit thresholds + ordering constraint.
3. **Independent taxonomy check:** N/A — taxonomy is the four 0-25 scoring dimensions, fixed by SPEC.
4. **Cross-vendor judge calibration:** DEFERRED — would have run on the actual scorer in Q-path.
5. **Honest falsifier verdict:** APPLIED — this document captures a "halted before exec" verdict, not "passed/failed."

## What ran

| Step | Result |
|---|---|
| M26.0 Lock SPEC v2 + supersede v1 | ✓ SPEC-85e02906 active, SPEC-b225215a superseded via store API |
| M26.1 Author high band (sub-agent) | ✓ 9 specs, plus 1 inline exemplar = 10 |
| M26.2 Author low band (sub-agent) | ✓ 9 antipatterns, plus 1 inline exemplar = 10 |
| M26.3 Materialize mid band | ✓ 21 M25-migration specs pulled |
| M26.4 Commit calibration JSON | ✓ commit `3fa829f` |
| M26.5 Write grading test | ✓ fails at import (designed) |
| M26.6 `loom decompose` | ✓ ran, produced 6 tasks — **with 3 structural errors** |
| M26.6.5 Hand-edit decomp YAML | ✓ saved original as evidence, fixed paths, dropped pre-reg-violating tasks, added the missing prompt-file task |
| M26.6.6 Apply hand-edited tasks | ✓ 5 tasks materialized into store |
| M26.7 `loom_exec --next --dry-run` | ✗ uncovered output-contract mismatch — **halted** |

## Findings — seven product gaps surfaced

Each captured as `kind=finding`, status `confirmed`, in the loom store. All derive from REQ-3896db58 (methodology) and REQ-6dec889f (M26 architecture req).

| # | REQ-ID | Domain | Headline |
|---|---|---|---|
| F1 | [REQ-cc95b9a1](#) | operational | `loom decompose` silently falls back to qwen when `ANTHROPIC_API_KEY` not exported to Python process. The asymmetric pipeline degenerated to single-model with no warning. |
| F2 | [REQ-de46b751](#) | architecture | qwen2.5-coder:32b decomposer emitted `src/cli.py` (pre-M9 layout) — wrong for 2 of 6 tasks. Confirms M22c hallucination finding (REQ-7e2d6518) extends to decomposer use. |
| F3 | [REQ-7f307ab7](#) | architecture | Decomposer emitted 2 tasks that would have modified pre-registration-locked artifacts (calibration JSON + grading test). No mechanism told it those files were frozen. |
| F4 | [REQ-ae1c6bab](#) | architecture | Decomposer skipped `src/loom/prompts/spec_score.txt` despite the SPEC naming it explicitly. Filename-shaped tokens with non-`.py` extension fall off the decomposer's radar. |
| F5 | [REQ-25c75b6f](#) | architecture | `loom_exec`'s assembled prompt hard-codes "Reply with ONE python code block" and APPEND mode regardless of target file extension. Authoring a `.txt` prompt file via this path produces garbage. |
| F6 | [REQ-75d6f16c](#) | architecture | Decomposer used a single full grading test (`TestSpecScoring`) as `test_to_write` for all 5 tasks. The test imports a not-yet-built symbol; tasks 1-4 cannot pass until task 5 produces the implementation. Each early task wastes attempts indefinitely. |
| F7 | [REQ-73b5ff3e](#) | operational | `loom supersede <SPEC-id>` is hinted by error messages (cli.py:2257) but not implemented — `supersede` only accepts Requirement IDs. The M26.0 SPEC v2 lock had to drop to the Python store API. |

### Severity bucketing

- **Pipeline-blocking** (must fix before any team-mode execution): F1 (silent fallback), F5 (Python-only prompt), F6 (shared grading test).
- **Quality-affecting** (failures cascade silently): F2 (wrong paths), F3 (pre-reg violations), F4 (missing files).
- **Friction-affecting** (workflow gap): F7 (hint-but-not-implemented CLI).

## What was NOT learned

- Whether `qwen3.5:latest` (the executor model) can actually produce a working `services.score_specification` given a clean task list. Answer awaits Q-path.
- Whether the three-band calibration would separate at the locked thresholds with a real LLM judge. Answer awaits a working scorer.
- Whether `claude-opus-4-7` produces materially different decomposition for this SPEC. Answer requires `ANTHROPIC_API_KEY` set + a re-run.

## What v2 needs (in priority order)

1. **Loud warning on model fallback** (F1) — fail-fast when `--model anthropic:*` requested but key missing; warn when defaulting from anthropic to ollama.
2. **Per-extension output contract** (F5) — `loom_exec` prompt template selects fence + apply-mode by target file extension. Non-Python uses replace mode by default.
3. **Per-task grading scope** (F6) — decomposer should emit smoke tests for early tasks (does the file exist? does the symbol import?), full grading reserved for the final integration task. Or: SPEC supports an explicit `grading_pipeline` field that loom_exec uses to graduate test scope.
4. **Decomposer repo-layout grounding** (F2, F4) — pass a one-page repo-tree summary into the decomposer prompt; post-decompose path-existence check rejects non-existent parent directories.
5. **Pre-reg protection** (F3) — `Specification` dataclass gains an optional `protected_files: list[str]` field; `loom decompose` refuses to emit tasks targeting any file in that list.
6. **CLI `supersede` accepts SPEC IDs** (F7) — dispatch on id prefix in `cmd_supersede`.

## Q-path follow-up (next session)

The pilot stopped at M26.7 dry-run. The Q-path plan if/when we resume:
1. Hand-patch task 1 (the prompt-file task): inline the prompt text inside a Python module so `loom_exec`'s Python-only contract works. Document as a workaround, not a fix.
2. Hand-write per-task smoke grading tests for tasks 1-4; keep `TestSpecScoring` only on task 5.
3. Run `loom_exec --loop` and capture the per-attempt outputs to `.exec-log.jsonl`.
4. If the scorer module materializes, run the full calibration sweep and capture the ordering + separation result against the pre-reg.
5. Honest verdict: did qwen3.5:latest produce a passing scorer? At what attempt count? What was the per-attempt cost in tokens / seconds?

## Artifacts

- `experiments/m26_spec_scorer/proposed_tasks.original.yaml` — raw decompose output (qwen2.5-coder:32b), preserved as evidence.
- `experiments/m26_spec_scorer/proposed_tasks.yaml` — hand-edited version (the 3 fixes documented in `notes:`).
- `experiments/m26_spec_scorer/apply_tasks.py` — one-shot script to materialize the hand-edited YAML into the store.
- `experiments/m26_spec_scorer/capture_findings.py` — one-shot script that captured F1-F6.
- `experiments/m26_spec_scorer/merge_calibration.py` — earlier one-shot for the calibration fixture lock.
- `tests/data/spec_scoring_calibration.json` — pre-registration artifact.
- `tests/test_spec_scoring.py` — grading test (fails at import until M26.7-Q ships the scorer).

## Pointer back to the workplace pitch

The headline thesis the workplace pitch will rest on is "loom built loom with a small local model." This pilot did NOT validate that — it validated that **the pipeline isn't team-ready in its current shape**. That's a useful negative result: shipping the v2 fixes from the priority list above is now a concrete sprint roadmap. The asymmetric-pipeline claim graduates from "validated on benchmarks" to "validated on benchmarks AND has a known v2 gap list."

The seven captured findings are themselves a deliverable: they grade the product against its own headline claim, with reproducible evidence.
