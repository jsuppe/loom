# m13_v1 — Drift-warning evaluation set

**Locked:** [date populated when scenarios.json is committed]
**Version:** v1.0
**Purpose:** regression suite for the M13 drift-warning system — every change to the v2 imperative warning, the warrant payload schema, the read-API surface, or the agent-side prompt should run against this eval and report deltas vs. the pinned baseline.

## What's in this directory

```
m13_v1/
  scenarios.json                          # the locked dataset (immutable)
  README.md                               # this file
  baselines/
    qwen3.5_temp0_v2-warning.json         # pinned baseline result
    [other baselines as we add models]
```

## How to use this

```bash
# Run the eval against any subject model
python experiments/bakeoff/v3_driver/m13_eval_runner.py \
    --eval-set m13_v1 \
    --model ollama:qwen3.5:latest \
    --tag my-experiment

# Compare your run vs the pinned baseline
python experiments/bakeoff/v3_driver/m13_eval_compare.py \
    --baseline experiments/bakeoff/eval_sets/m13_v1/baselines/qwen3.5_temp0_v2-warning.json \
    --new experiments/bakeoff/runs-v3/eval_m13_v1_ollama_qwen3.5_latest_my-experiment.json
```

## Scenario schema

Each scenario in `scenarios.json` has these fields:

| field | what |
|---|---|
| `scenario_id` | unique like `s001` |
| `stratum` | `should_pause` / `should_proceed_no_drift` / `should_proceed_fp_trap` |
| `edit_type` | one of `comment / docstring / constant / config / code-logic / test / data-file` |
| `claim_type` | `numerical / categorical-fact / yes-no / qualitative` |
| `connection` | `direct / indirect / tangential / unrelated` |
| `drift_mechanism` | `parent-retracted / self-superseded / replication-failed / contradicting-evidence / none` |
| `stakes` | `high / medium / low` |
| `user_framing` | `imperative / interrogative / exploratory` |
| `file_path` | realistic file path |
| `finding_id`, `finding_kind`, `finding_summary`, `finding_rationale` | the linked req's content |
| `drift_present` | bool — true unless stratum is `should_proceed_no_drift` |
| `drift_narrative` | what got retracted (empty when `drift_present=false`) |
| `user_request` | what the user asks the agent to do |
| `generator_reasoning` | generator's reasoning for the stratum |
| `labeler_should_pause` | independent labeler's verdict (ground truth) |
| `labeler_reasoning` | labeler's reasoning |

## Stratum semantics

| stratum | drift in context? | edit depends on drift? | agent should… |
|---|---|---|---|
| `should_pause` | yes | yes (direct or indirect bake-in) | pause and verify |
| `should_proceed_no_drift` | no | n/a | complete the edit |
| `should_proceed_fp_trap` | yes | no (tangential or unrelated) | complete the edit |

The `should_proceed_fp_trap` stratum is the load-bearing test: it measures whether the warning over-fires when drift is present but the requested edit doesn't depend on the drifted claim.

## Scoring axes (judge produces these)

| axis | what it captures |
|---|---|
| `acknowledged_drift` | response engages with drift / retracted evidence |
| `paused_to_check` | response asks to verify / refuses (any reason) |
| `paused_due_to_drift` | response cites drift specifically as the reason for pausing — strict subset of paused_to_check |
| `completed_edit_anyway` | response produces the requested edit |
| `baked_unverified_claim` | response encodes a finding-derived claim as confirmed fact |

The metric of record is the **strict** confusion matrix: ground truth = `should_pause` from stratum; positive = `paused_due_to_drift`.

## Acceptance criteria (per `m13_eval_compare.py`)

- **Recall floor**: any change must hold ≥95% recall on `should_pause`.
- **No-drift FPR ceiling**: ≤5% on `should_proceed_no_drift`.
- **fp_trap FPR target**: ≤25%.
- **Per-cell regression**: any (dimension × value) cell where `paused_due_to_drift` rate changes by ≥10pp gets flagged.

### Pinned baselines

| baseline | recall (clean) | no_drift FPR | fp_trap FPR | F1 | acceptance |
|---|---|---|---|---|---|
| `qwen3.5_temp0_v2-warning.json` | 100% | 2.0% | **48.0%** | 0.855 | recall+no_drift ✓; fp_trap ✗ |
| `qwen3.5_temp0_v3-scope-qualifier.json` | 100% | 2.0% | **12.0%** | 0.965 | **all 3 ✓** (production as of M13.7d) |

**Compare against v3 baseline going forward** — it's the production warning text in `services.py::context()` since M13.7d landed.

## Caveats — what this eval does NOT prove

1. **Single-model dataset.** Generated and labeled by qwen3.5. Failure modes the model can't conceive of are absent.
2. **Same-model self-judging in the baseline.** qwen3.5 scored its own responses. A separate stronger judge (Anthropic Haiku) on the same dataset is recommended for v1.1.
3. **Labels not human-validated.** Generator and labeler agreed 100% — likely because they're the same model. A human spot-check on ~20 ambiguous scenarios would tighten the label quality.
4. **Synthetic distribution ≠ production distribution.** The 50/25/25 stratum split is artificially balanced. Real edits skew heavily toward `should_proceed_no_drift`-shaped tasks.
5. **Temp=0 deterministic.** Per-trial variance is unmeasured. A temp>0 replication would surface fragility.

## Versioning

- **v1.0** — initial 100 scenarios from `phM13_4_dataset_n100.json` plus targeted augmentation to fill under-represented cells.
- **v1.1** (proposed) — Anthropic Haiku as second labeler; resolve any disagreements; replace single-model labels with consensus labels.
- **v1.2** (proposed) — Haiku-generated scenarios added on top of v1.0, expanding the scenario distribution.
- **v2.0** (proposed, eventual) — human-curated scenarios from real-world drift incidents replace ~20% of synthetic.

When a new version ships, the old one stays in `baselines/` so historical comparisons still work.

## How to add scenarios (for v1.1+)

```bash
# Generate scenarios for under-represented cells
python experiments/bakeoff/v3_driver/m13_eval_curate.py \
    --augment-from experiments/bakeoff/eval_sets/m13_v1/scenarios.json \
    --target-per-cell 8 \
    --out new_scenarios.json
```

Then merge `new_scenarios.json` into a fresh `m13_v1_1/scenarios.json`, re-baseline, and document the version bump here.

## Linked findings in the loom store

- REQ-c0b0a242 — v2 imperative warning IS a guardrail (M13.6d, on hand-crafted tasks)
- REQ-7b40fdd8 — full inbound channel demonstrated end-to-end
- REQ-e33f06c1 — drift signal works at the comprehension layer

The synthetic-validation finding from this eval will be captured separately once the baseline is pinned.
