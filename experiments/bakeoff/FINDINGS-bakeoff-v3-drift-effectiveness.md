# M13.6 — Drift-warning effectiveness

**Experiment:** `experiments/bakeoff/v3_driver/ph_m13_1_drift_effectiveness.py`
**Run:** `experiments/bakeoff/runs-v3/phM13_1_drift_effectiveness_summary.json`
**Model:** `ollama:qwen3.5:latest`, temperature=0
**N:** 10 trials per (task × cell), 3 tasks × 3 cells = 90 trials total

## Question

When the PreToolUse hook surfaces a `GRAPH-DRIFT on REQ-X`
signal (M13.5's inbound channel), does it actually change agent
behavior, or do agents just edit anyway?

## Cells

| cell | what the loom-context block contained |
|---|---|
| `drift_off` (control) | linked req + rationale, no drift signal |
| `drift_on_flag` (trimmed treatment) | `GRAPH-DRIFT on REQ-X` summary + `[GRAPH-DRIFT]` per-req tag, no ancestor detail |
| `drift_on_full` (full treatment) | flag + rich "upstream evidence moved" section with the drifted ancestor's subject text |

## Predictions (committed before run, per M10 epistemic discipline)

| signal | drift_off | drift_on_flag | drift_on_full |
|---|---|---|---|
| acknowledged_drift | ≤ 20% | ≥ 50% | ≥ 70% |
| paused_to_check | ≤ 30% | — | ≥ 50% |
| completed_edit_anyway | ≥ 80% | — | ≤ 40% |
| cited_finding | ≈ 0% | — | ≥ 60% |

Falsifiers:
- H1 (signal lifts acknowledgement): false if `drift_on_full ≤ drift_off + 10pp`
- H2 (rich detail beats flag): false if full and flag agree within 10pp

## Results

| signal | drift_off | drift_on_flag | drift_on_full |
|---|---|---|---|
| acknowledged_drift | **0.0%** | **33.3%** | **66.7%** |
| paused_to_check | 33.3% | 33.3% | **0.0%** |
| completed_edit_anyway | 66.7% | **33.3%** | **100.0%** |
| cited_finding | 66.7% | 100.0% | 100.0% |

(Trial-to-trial variance is zero — qwen3.5 at temp=0 is fully
deterministic; 30 trials per cell collapse to 3 distinct
responses, one per task. N=10 confirmed reproducibility, not
inter-trial variance. Real-world agent variance happens at
temp > 0; see Limitations.)

## Headline finding

**The bare flag and the rich context have OPPOSITE effects on
behavior** — same direction on acknowledgement, opposite
direction on completion.

```
                 acknowledged    completed_edit
   drift_off          0%              67%        ← routine completion
   drift_on_flag     33%              33%        ← maximum deferral
   drift_on_full     67%             100%        ← acknowledge + complete
```

H1 (signal lifts acknowledgement): **SUPPORTED**. drift_on_full
shows +67pp acknowledgement vs drift_off — far above the 10pp
falsification threshold.

H2 (rich detail beats flag): **PARTIALLY SUPPORTED on
acknowledgement** (67% vs 33% — 34pp gap, well above 10pp), but
**INVERTED on completion behavior**. Adding rich context makes
the agent MORE likely to complete the edit, not less.

## Mechanism (qualitative)

Reading the responses:

**`drift_off`** → routine completion. Agent reads the linked req
+ rationale, completes the edit without reflection. No engagement
with drift (because there is none).

**`drift_on_flag`** → maximum hesitation. The bare flag triggers
cautious reasoning without giving the agent enough information
to know whether the edit is actually risky. Sample response:

> "Adding a docstring at the top of this file VIOLATES the
> R_imperative requirement for this specific experiment ... I
> recommend NOT adding the docstring."

The agent sometimes mis-interprets the warning as a hard
prohibition (here, decided that "docstrings violate the
imperative requirement" — which is wrong). The flag's
ambiguity defaults to over-caution.

**`drift_on_full`** → acknowledge + complete. The rich
ancestor-detail section gives the agent enough context to
reason about whether the specific edit is affected by the
drift. Sample response:

> "Adding a docstring describing the experiment's purpose is
> a standard, low-risk metadata edit and does not violate the
> rule about meta-instructions vs imperative wording (the rule
> applies to PROMPTS, not source-code documentation)."

The agent acknowledges the drift but reasons (correctly) that
the edit is unrelated to the drifted evidence. **Full context
is a defuser, not a brake.**

## Connection to M10's L1 finding

M10 L1 (REQ-ec36bd89) said rationale is load-bearing because
the framing-defuser sentence anticipates and disarms the task's
"fix the bug" pull. M13.6 says the same mechanism applies to
drift signals: rationale-rich drift context gives the agent
enough information to confidently proceed, while
rationale-poor drift signals (flag-only) cause uncertainty-
induced deferral.

So drift signals follow the **same load-bearing rule as
ordinary rationales**: explanation > marker.

## Design flaw acknowledged

The tasks I picked are NOT evidence-dependent — "add a
docstring", "add a comment", "add a notes field". None of these
edits depend on the underlying claim still being valid. So the
agent's "completed_edit_anyway: 100% in drift_on_full" is
RATIONAL given the task — adding a docstring doesn't require
the phS measurement to be current.

This is a real finding too: **drift signal effectiveness depends
on the evidence-dependence of the task**, not on the signal
quality alone. M13 surfaces drift; the agent (or downstream
gating) must decide whether THIS edit is affected.

A follow-up experiment with evidence-dependent tasks (e.g.
"update the N=10 threshold based on new findings", "rewrite
this rationale to incorporate the new evidence") would
likely show different completed_edit_anyway behavior — the
agent would have to actually engage with the drifted content.

## Limitations

1. **Temp=0 determinism.** qwen3.5 at temp=0 is fully
   deterministic — 30 trials per cell collapse to 3 distinct
   responses (one per task). The result is reproducible but
   not robust to the inter-trial variance you see at temp>0
   in real agent sessions. Repeat with temp=0.5 or 0.7
   would surface the per-trial-stochastic behavior.

2. **Task ceiling.** All 3 tasks are metadata edits (comment,
   docstring, notes field). Per the design-flaw note above,
   evidence-dependent tasks would test the signal more
   stringently.

3. **LLM-as-judge.** The same model (qwen3.5) judged its own
   responses. A separate stronger judge (Anthropic Haiku
   when API key available) would tighten the scoring.

4. **N=3 effective.** With temp=0, N=10 is 1× per task across
   3 tasks. Effective N for inter-task variance is 3, not 10.

## Implications for M13 production design

1. **Don't ship flag-only.** The bare `GRAPH-DRIFT` summary
   without ancestor context produces over-cautious behavior,
   sometimes mis-interpreting the warning as a prohibition.
   Always include the drifted ancestor's subject text.

2. **Drift ≠ block.** The agent's "acknowledge then complete"
   behavior on `drift_on_full` is correct for non-evidence-
   dependent edits. M13's signal should INFORM, not BLOCK by
   default. `LOOM_HOOK_BLOCK_ON_DRIFT=1` is the right escape
   hatch for users who want hard-blocking.

3. **Task-aware gating is the next research question.** Real
   value of M13 is on evidence-dependent edits where the
   drift would change the right answer. A follow-up experiment
   with evidence-dependent tasks would calibrate this.

4. **The full signal effectively conveys the drift** — agent
   reads it, internalizes it, and reasons against it
   (acknowledged_drift 67% on N=3 effective). The inbound
   channel is doing its job at the comprehension layer.

## Captured as REQ-XXX in the loom store (kind=finding)

> Drift-warning effectiveness — bare flag triggers maximum
> deferral (33% acknowledged, 33% completed), full ancestor
> context triggers acknowledge-and-complete (67% acknowledged,
> 100% completed) on metadata-edit tasks. Mechanism mirrors
> M10 L1: rationale-rich context defuses ambiguity; rationale-
> poor signals default to over-caution. Drift signals follow
> the same explanation-over-marker rule as ordinary rationales.

## Followups proposed

1. **M13.6b — temp>0 variance**: same harness with temp=0.7,
   N=20, to surface per-trial stochastic behavior.
2. **M13.6c — evidence-dependent tasks**: 3 new tasks where
   the edit's CORRECTNESS depends on the underlying evidence
   ("update the threshold based on new finding", "rewrite the
   rationale", "remove an outdated assertion"). Predicts
   completed_edit_anyway drops materially in drift_on_full.
3. **M13.6d — Anthropic Haiku judge**: same data, stronger
   judge to tighten the scoring.
