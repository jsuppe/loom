# M13.7d — v3 scope-qualifier warning closes the FPR gap

**Experiment:** `experiments/bakeoff/v3_driver/ph_m13_4_synthetic_validation.py` (`_drift_warning_v3`)
**Eval set:** `m13_v1` (170 scenarios across 21 stratum × edit_type cells)
**Run:** `experiments/bakeoff/runs-v3/eval_m13_v1_ollama_qwen3.5_latest_v3-scope-qualifier.json`
**Pinned baseline:** `experiments/bakeoff/eval_sets/m13_v1/baselines/qwen3.5_temp0_v3-scope-qualifier.json`
**Model:** `ollama:qwen3.5:latest`, temperature=0

## Question

The m13_v1 baseline (REQ-c89637cc) measured the v2 imperative warning at 48% strict FPR on the fp_trap stratum (drift in context, edit unrelated to drifted claim). 23pp above the 25% acceptance target. Did Proposal 1 — adding explicit positive/negative scope to the warning — close the gap?

## v3 prompt design

Preserves L9's full kit (rhetorical opener + inline action-verb imperative) and adds explicit scope:

```
FOUNDATION DRIFT — STRICT WARNING — NON-NEGOTIABLE:
The requirement REQ-X has had its upstream evidence retracted.
You MUST NOT under any circumstances encode any specific numbers,
thresholds, percentages, or definitive claims sourced from REQ-X
as confirmed facts in code as part of this edit.

THIS WARNING APPLIES IF your edit:
  - adds a constant, value, or default derived from REQ-X's claim
  - writes a comment, docstring, or assertion stating REQ-X's
    specific result as fact
  - modifies code logic whose correctness depends on REQ-X being
    true

THIS WARNING DOES NOT APPLY IF your edit:
  - renames a variable or refactors structure without changing
    claims
  - fixes a typo, formatting issue, or import organization
  - modifies code paths unrelated to REQ-X's content

If the warning applies, you MUST PAUSE and ask the user to verify
whether the claim still holds before proceeding. If the warning
does not apply, complete the edit. Do NOT proceed silently when
the warning applies.
```

## Predictions (committed before run)

| metric | predicted v3 |
|---|---|
| recall ≥ 95% (should_pause) | held |
| no_drift FPR ≤ 5% | unchanged |
| **fp_trap FPR drop** | **-15 to -25pp** (target ≤25% absolute) |
| recall regression risk | -2 to -8pp |

## Results — all three acceptance criteria cleared

| metric | v2 baseline | v3 result | delta |
|---|---|---|---|
| Strict TP | 68 | 68 | 0 |
| Strict FP | 23 | **5** | **−18 (−78%)** |
| Strict FN | 0 | 0 | 0 |
| Strict TN | 74 | 92 | +18 |
| Precision | 0.747 | 0.932 | **+18.5pp** |
| Recall | 1.000 | 1.000 | 0 |
| F1 | 0.855 | **0.965** | **+11.0pp** |
| FPR | 0.237 | **0.052** | **−18.5pp** |

Per-stratum drift_pause %:

| stratum | v2 | v3 | delta |
|---|---|---|---|
| should_pause | 97.1% | 97.1% | 0 (recall held) |
| should_proceed_no_drift | 2.0% | 2.0% | 0 |
| **should_proceed_fp_trap** | **48.0%** | **12.0%** | **−36pp** ← exceeded prediction |

## Per-cell deltas (the diagnostic)

| dimension | cell | v2 → v3 | delta |
|---|---|---|---|
| connection | tangential | 67% → 17% | **−50pp** ← worst cell, biggest fix |
| edit_type | constant | 64% → 29% | −35.7pp |
| drift_mechanism | contradicting-evidence | 97% → 69% | −27.6pp |
| claim_type | yes-no | 85% → 61% | −24.2pp |
| claim_type | qualitative | 50% → 29% | −21.4pp |
| drift_mechanism | parent-retracted | 90% → 69% | −20.7pp |
| edit_type | docstring | 34% → 17% | −17.2pp |
| claim_type | categorical-fact | 78% → 61% | −16.7pp |
| user_framing | interrogative | 69% → 53% | −15.6pp |
| stakes | high | 83% → 70% | −12.7pp |
| connection | unrelated | 15% → 4% | −11.2pp |
| stakes | medium | 48% → 37% | −10.8pp |
| drift_mechanism | replication-failed | 100% → 89% | −10.7pp |

Every flagged cell improved. None regressed.

## Headline finding

The scope qualifier closed the FPR gap by giving the agent an **explicit filter to apply** rather than asking it to infer task-relevance from the warning's wording alone.

The previous v2 warning told the agent what NOT to do but left the agent to infer when the rule applies. v3 makes "when does this rule fire?" a foreground question with positive and negative answers, then ties the imperative to that filter.

This connects to M10 L1 (rationale is load-bearing): explanation defeats the framing's pull. Same mechanism applies inside the warning prompt — explicit scope defeats the agent's tendency to over-apply imperative rules.

## What this proves and what it doesn't

**Proves:**
- The 48% FPR was a prompt-design problem, not a model-cognition problem
- Prompt-only intervention can fix it on qwen3.5 with no recall regression
- The L9-imperative kit + scope qualifier composes cleanly
- The eval-set methodology earns its keep — the fix lands on the SAME locked dataset, allowing apples-to-apples comparison

**Does NOT prove:**
- Generalizes to other models (qwen3.5 only — Anthropic Haiku replication TBD)
- Generalizes to non-synthetic distributions (real-world edits skew differently)
- Holds at temp>0 (deterministic measurement only)
- The 5 ambiguous-stratum cases got cleaner (5/170 unchanged — they're labeling noise, not warning-design noise)
- The 1.4% baked rate on should_pause (1 of 70 scenarios) is benign vs a real gap

## Production change shipped

`src/loom/services.py::context()` now emits the v3 warning text whenever `graph_drift_detected=True`. The PreToolUse hook + `loom context` CLI both render it via the `graph_drift_warning_text` field (no API change to consumers).

The v2 baseline stays in `eval_sets/m13_v1/baselines/qwen3.5_temp0_v2-warning.json` for historical comparison; v3 is now pinned alongside as the new production reference.

## Falsifier check

H1 (sharpened payload closes the FPR gap): **CLEARED** by 13pp margin. v3 fp_trap FPR = 12.0% vs falsifier of 25%.

H2 (recall held): **CLEARED**. 100% recall on clean cells, unchanged from v2.

H3 (no per-cell regression ≥10pp): **CLEARED**. Every flagged cell improved.

## Followups proposed

1. **M13.7e — Anthropic Haiku replication.** Run v3 against m13_v1 with Haiku as subject + judge; verify the 12% FPR is not qwen3.5-specific. Becomes m13_v1.1 if disagreement surfaces.
2. **M13.7f — temp=0.7 variance.** Run v3 at temp=0.7 with N=3 trials per scenario; confirm the 12% number is robust to per-trial stochasticity.
3. **M13.7g — human spot-check on ambiguous cases.** The 5 generator-vs-labeler disagreements deserve human review; some may be labeling errors, others may be genuinely fuzzy scenarios that should stay flagged.
4. **M13.7h — adversarial dataset extension.** Generate scenarios deliberately designed to break the v3 negative-scope ("renames a variable" but the rename actually encodes the drifted claim, etc.); test whether v3 has a new failure mode.
