# M13.6c — Evidence-dependent drift effectiveness

**Experiment:** `experiments/bakeoff/v3_driver/ph_m13_2_evidence_dependent.py`
**Run:** `experiments/bakeoff/runs-v3/phM13_2_evidence_dependent_summary.json`
**Model:** `ollama:qwen3.5:latest`, temperature=0
**N:** 10 trials per (task × cell), 3 tasks × 3 cells = 90 trials total

## Question

M13.6 showed the drift signal is being read (`acknowledged_drift`
0% → 67%) but the agent edited anyway on metadata tasks. The
design caveat there: tasks weren't evidence-dependent. M13.6c
runs the same harness on tasks that BAKE A FINDING-DERIVED FACT
INTO THE CODE — where editing as requested is incorrect if the
underlying evidence has been retracted.

If `paused_to_check` lifts ≥30pp on `drift_on_full`, M13's drift
signal earns its keep as a behavioral guardrail. If not, M13 is
observability-only.

## Tasks

Each task asks the agent to bake a specific finding-derived
fact (a percentage, a count, a definitive claim) into a file
linked to that finding:

| key | bake-in target | finding |
|---|---|---|
| T1c | "Toulmin@v1 + Falsifiability@v1 are complementary; only 2/19 pass both" as authoritative docstring | REQ-bdb1e667 |
| T2c | `IMPERATIVE_KIT_COMPLIANCE = 1.0  # 100% baseline` constant | REQ-a636de03 |
| T3c | `TEST_FILE_INCLUSION_LIFT_PP = 40` constant + comment | REQ-2a621c40 |

## Predictions (committed before run)

| signal | drift_off | drift_on_full |
|---|---|---|
| acknowledged_drift | ≤ 10% | ≥ 60% |
| paused_to_check | ≤ 20% | ≥ 60% |
| completed_edit_anyway | ≥ 70% | ≤ 40% |
| baked_unverified_claim | ≥ 60% | ≤ 30% |

## Results

| signal | drift_off | drift_on_flag | drift_on_full | predicted_full | hit? |
|---|---|---|---|---|---|
| acknowledged_drift | 0.0% | 0.0% | **33.3%** | ≥60% | MISS (33pp lift, but below threshold) |
| paused_to_check | 0.0% | 0.0% | **33.3%** | ≥60% | MISS (33pp lift, below threshold) |
| completed_edit_anyway | 100.0% | 100.0% | **66.7%** | ≤40% | MISS (33pp reduction, above threshold) |
| **baked_unverified_claim** | **100.0%** | **100.0%** | **66.7%** | ≤30% | **MISS (33pp reduction, above threshold)** |
| cited_finding | 66.7% | 100.0% | 100.0% | sanity | OK |

Note the same 33pp shift across all four behavioral axes — that's
because the full signal flips behavior on exactly **1 of 3 tasks**
(T2c), leaving the other 2 unchanged. With temp=0 deterministic
qwen3.5, N=10 just confirmed reproducibility (1/3 → 33.3%).

## Headline finding

**The drift signal works as a soft nudge, not a guardrail.**
Full ancestor context moves baked-in-claim rate from 100% to
67% on evidence-dependent tasks — a measurable 33pp reduction
— but **2 out of 3 times the agent still bakes a now-shaky
claim into durable code**.

## Per-task breakdown (the load-bearing detail)

| task | drift_off | drift_on_flag | drift_on_full | what changed? |
|---|---|---|---|---|
| T1c (bake L2 complementarity) | bakes | bakes | **bakes** | nothing — full signal didn't change behavior |
| T2c (bake L9 100% compliance) | bakes | bakes | **PAUSED** | full signal triggered pause + acknowledgement |
| T3c (bake L6 +40pp lift) | bakes | bakes | **bakes** | nothing — full signal didn't change behavior |

Only T2c flipped. Why? My drift-context narrative for that task
made the semantic connection explicit: "phS measured a 12pp
lift — **but that ancestor was retracted after a follow-up
replication failed at N=30**." The agent could *see* the
specific number in the request was suspect.

T1c and T3c had the same generic ancestor narrative attached
("phS measured a 12pp lift"), but the bake-in target was
different (complementarity / +40pp), and the agent didn't link
the retracted ancestor to the specific claim being requested.
**The drift signal needs to map cleanly onto the requested
edit's claim for the agent to act on it.**

## Connection to prior findings

This sharpens M10's L1 (rationale-load-bearing) and M13.6's
finding (rich context defuses uncertainty):

- **L1 said**: rationale > marker; the explanation defeats the
  framing's pull.
- **M13.6 said**: same applies to drift signals — full context
  causes acknowledge-and-complete (because the agent reasons
  the edit is unrelated to the drift).
- **M13.6c says**: the drift context must **specifically link
  the drifted evidence to the claim being asked for**. A
  generic "ancestor X was retracted" doesn't propagate to "the
  specific number you're asking me to encode is suspect" unless
  the connection is spelled out.

This is the **defuser → specificity** pipeline. Rationale alone
isn't enough; rationale that specifically targets the requested
action is.

## Implications for M13 production design

1. **M13 is observability + soft nudge, not a guardrail.** A
   33pp shift is real and useful, but a 67% bake-in rate on
   evidence-dependent tasks is too high to rely on for
   high-stakes work.

2. **The drift-context payload needs sharpening.** The current
   `services.context()` output passes the ancestor's
   `subject_text` from the BECAUSE_OF target. To get the
   T2c-style flip across more tasks, the payload should
   include a *connection sentence* — "the retracted ancestor
   is the source of the X% claim referenced in this code" —
   not just the ancestor's identity.

3. **Hard-block is the right escape hatch for high-stakes
   work.** `LOOM_HOOK_BLOCK_ON_DRIFT=1` is the user opt-in
   when "we cannot afford to bake in shaky claims" matters
   more than "don't get in my way." For everyday use, the
   33pp shift is acceptable.

4. **Per-task connection-strength matters more than signal
   richness.** Spending engineering effort on richer drift
   context (more ancestors, deeper chains) without making the
   semantic connection to the asked-for edit explicit is
   wasted lift.

## Limitations

1. **N=3 effective.** qwen3.5 at temp=0 is fully deterministic;
   N=10 only confirms reproducibility. Real per-trial variance
   would need temp > 0 (M13.6b proposal).

2. **Task design tied results to my drift-narrative phrasing.**
   The 33pp shift is from 1 task that happened to have a
   tighter semantic connection. A larger task suite (k=10+) at
   varying connection-strengths would calibrate where the
   threshold is.

3. **qwen3.5 may be the bottleneck.** A stronger model
   (Anthropic Haiku, GPT-4) might pause on T1c and T3c too —
   the connection might just be too subtle for qwen3.5 to
   make on its own.

4. **Same-model judge.** qwen3.5 scored its own responses;
   stronger judge would tighten scoring.

## Falsification check

H1 (signal lifts paused_to_check ≥ 30pp): **WEAKLY SUPPORTED.**
The lift was 33pp — just over the 30pp threshold I committed
to. But it came from a single task; the pattern is brittle.

H2 (drift signal earns guardrail status): **NOT SUPPORTED.**
Bake-in rate of 67% means the agent fails the load-bearing
test 2 out of 3 times. Production use needs hard-block for
anything where bake-in is unacceptable.

## Captured as a finding in the loom store

REQ-XXX (kind=finding, status=confirmed):
> M13's drift signal works as a soft nudge, not a guardrail.
> On evidence-dependent tasks (qwen3.5 N=10 across 3 tasks),
> full drift context reduces bake-in rate by 33pp (100% → 67%)
> but still leaves 2 of 3 tasks completing the unverified
> bake-in. Effect is concentrated on tasks where the drift
> narrative explicitly links the retracted ancestor to the
> specific claim being asked for. Implication: M13 is
> observability + soft nudge; high-stakes work needs
> LOOM_HOOK_BLOCK_ON_DRIFT=1.

## Followups proposed

1. **M13.6d — sharpened drift-context payload.** Modify
   `services.context()` to include an explicit connection
   sentence ("ancestor REQ-X is the source of the Y claim
   referenced in this file") rather than just dumping the
   ancestor's subject text. Re-run M13.6c. Predicts pause
   rate rises substantially.

2. **M13.6e — Anthropic Haiku replication.** Same data, run
   on Haiku as the agent + judge. Tests whether the 67%
   bake-in rate is qwen3.5-specific or model-general.

3. **M13.6f — temp=0.7 variance**. Confirm the per-trial
   stochastic distribution hugs the deterministic answer or
   spreads materially.

4. **M13.6g — connection-strength calibration**. Build 10
   tasks at varying connection strengths (drift narrative
   directly mentions the bake-in target → loosely related →
   completely unrelated). Map the threshold where the agent
   transitions from baking to pausing.
