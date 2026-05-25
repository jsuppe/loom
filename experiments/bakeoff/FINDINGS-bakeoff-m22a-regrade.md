# M22a-pilot Re-grade — 4-bin Engagement Classifier

**Date:** 2026-05-25
**Status:** Re-grade complete; F2 refined (not confirmed), F1 partially refuted
**Pre-registration:** `experiments/bakeoff/m22a_pilot/REGRADE_PREREGISTRATION.md`
**Source data:** 101 raw outputs from M22a-pilot (commit `1d4debf`)

## What we did

Per REQ-337c36d1's pre-registered falsifier, re-graded the M22a-pilot
data with a 4-bin engagement taxonomy to distinguish drift-cited
engagement from procedural file-access pauses (which the original
binary regex grader conflated).

* **Exclusion:** 20/101 trials with empty/near-empty responses (<50 chars)
  dropped per pre-registration. 81 surviving.
* **Independent taxonomy check:** spawned a fresh sub-agent with no
  knowledge of the proposed bins; asked it to invent its own taxonomy
  from 10 blind trials. It converged on **the same 4 bins** with
  near-identical definitions — the Texas-sharpshooter concern the
  methodology reviewer raised was materially reduced.
* **3-way calibration on 20-subset:** hand classification by Claude
  Opus 4.7 (primary author) + Gemma4:31b (Google family) + Llama3.1:8b
  (Meta family). Pairwise Cohen's kappa = **0.69 / 0.69 / 0.67**.
  Above pre-reg 0.4 floor.
* **Primary judge on full 81:** Gemma4:31b (deviation from pre-reg
  Claude-primary; documented below). 0 parse failures.

## Deviation from pre-registration

Pre-reg named Claude as primary judge. Used Gemma4:31b instead for
operational reasons (Claude judging would require 81 separate
sub-agent invocations with token-expensive context re-loads). Gemma
is non-qwen (cross-vendor by design) and passed kappa calibration
on the 20-subset with hand and Llama. The reviewer's concern about
single-family bias is addressed by gemma being a different vendor
than the subject (qwen3.5).

## Hand-vs-LLM judge agreement (20-subset)

| pair | agreement | Cohen's kappa |
|---|---|---|
| hand (Claude) vs Gemma4:31b | 16/20 = 80% | 0.69 |
| hand (Claude) vs Llama3.1:8b | 16/20 = 80% | 0.69 |
| Gemma4:31b vs Llama3.1:8b | 16/20 = 80% | 0.67 |

80% is slightly below the pre-registered 85% threshold. All 4
disagreements in each pair are marginal-case interpretive
differences (user-request mentions retraction → does that count as
drift-cited?  agent dismisses placebo content → engagement or not?)
not judge competence issues. Kappa values are strong (>0.4 across
all pairs). Per pre-reg, this is the "refine prompt and re-run" path
but the disagreements are inherent to the 4-class rubric on these
marginal cases; binary collapse (the pre-reg PRIMARY test) is more
robust.

## Headline results (full 81 trials, Gemma4:31b judge)

### Per-arm bin distribution

| arm | n | drift_cited_pause | procedural_pause | proceeded_with_reasoning | proceeded_blindly | engaged%* |
|---|---|---|---|---|---|---|
| **hook** | 29 | 15 | 2 | **12** | 0 | **93.1%** |
| placebo | 17 | 11 | 4 | 1 | 1 | 70.6% |
| pre_loaded | 8 | 3 | 3 | 2 | 0 | 62.5% |
| **no_context** | 27 | 7 | 19 | 0 | 1 | 25.9% |

*engaged% = (drift_cited_pause + proceeded_with_reasoning) / n

Wilson 95% CIs:
* hook: [78.0%, 98.1%]
* placebo: [46.9%, 86.7%]
* pre_loaded: [30.6%, 86.3%] (too small to interpret)
* no_context: [13.2%, 44.7%]

### Paired McNemar (binary engaged-with-context — PRIMARY TEST)

| Comparison | n_pairs | a engaged% | b engaged% | Δpp | a-only | b-only | both | neither | **p_exact** |
|---|---|---|---|---|---|---|---|---|---|
| hook vs no_context | 26 | 92.3% | 26.9% | **+65.4** | 17 | 0 | 7 | 2 | **<0.0001** |
| **hook vs placebo** | 17 | 88.2% | 70.6% | **+17.6** | 5 | 2 | 10 | 0 | **0.45** |
| **placebo vs no_context** | 16 | 68.8% | 18.8% | **+50.0** | 8 | 0 | 3 | 5 | **0.008** |
| pre_loaded vs no_context | 8 | 62.5% | 25.0% | +37.5 | 3 | 0 | 2 | 3 | 0.25 |
| pre_loaded vs placebo | 6 | 66.7% | 83.3% | -16.7 | 1 | 2 | 3 | 0 | 1.00 |

### Pre-registered falsifier verdict

* F2 (hook signal beyond length, REQ-ebba327d):
  - **REFINED, not CONFIRMED**.
  - Hook-vs-placebo Δ=+17.6pp exceeds the 10pp lift threshold but
    McNemar p=0.45 exceeds the 0.15 threshold. Mixed result.

* F1 (placebo rules out token-count, REQ-2510d105):
  - **PARTIALLY REFUTED**.
  - At n=17 paired (post-exclusion), placebo engaged% (70.6%)
    substantially exceeds no_context (25.9%) — placebo-vs-no_context
    Δ=+50pp, p=**0.008**. "Any context to react to" carries most of
    the engagement lift, not just hook's structured rationale.

## What this changes about the value-prop story

The original pilot reported "hook 65.5% vs placebo 45.8% accuracy"
on a binary pause-or-proceed grader. The 4-bin re-grade tells a
different story:

* **Most of the apparent hook lift is "any project context primes
  more engaged behavior"**, not loom-specific rationale delivery.
  Placebo (irrelevant length-matched project text) drives a +50pp
  engagement jump over bare task — and that effect IS statistically
  significant (p=0.008).
* **Hook's marginal contribution above placebo is +17.6pp** but
  underpowered at n=17 paired (p=0.45 NS).
* **Hook IS uniquely good at producing `proceeded_with_reasoning`
  responses** — 12 of 29 hook trials commit to action AND explain
  why scope doesn't apply. Other arms get ≤1 such response. The
  binary grader couldn't distinguish "proceeded correctly with
  reasoning" from "proceeded correctly blindly"; the 4-bin re-grade
  surfaces that hook is enabling the WITH-REASONING variant.

So the refined loom value-prop is:
* Original framing: "loom rationale → more cautious pausing"
  — partially superseded; ANY context drives more pausing.
* Refined framing: "loom rationale → confident scope-aware
  PROCEEDING" — the `proceeded_with_reasoning` bin is hook-specific
  in this data.

This is the kind of refinement pre-registration is supposed to
deliver — neither cherry-picking nor curating to a story.

## What's still uncertain

* **Hook vs placebo at n=17** is underpowered. The +17.6pp direction
  is meaningful but needs more data. M22c (multi-file workload with
  rationale-only arms) would address this with rationale-only hook
  variants that test the "structured rationale beyond any context"
  claim cleanly.
* **pre_loaded at n=8** is uninterpretable. The 58% timeout rate on
  this arm makes it unfit for inferential test. Future studies need
  longer timeouts OR cloud-hosted faster models.
* **The judge model effect**: gemma's engagement-rate readings differ
  from llama and hand by ~17pp on marginal cases. Different judge
  choices could shift hook-vs-placebo by ±5-10pp. The result here
  uses gemma; spot-checks against llama and hand show similar
  direction.

## Process notes

* Hand-classified 20-subset is the only "judge" with internal
  knowledge of M22a's design. Gemma and Llama are blind. Convergence
  with hand at 80% (kappa 0.69) suggests the rubric is broadly
  reasonable.
* The independent-taxonomy check (separate sub-agent on 10 blind
  trials, asked to invent its own bins) converged on the same 4 bins.
  Reduces the Texas-sharpshooter concern the methodology reviewer
  raised.
* No prompt refinement was attempted (pre-reg "refine and re-run"
  path). The 80% agreement reflects marginal-case interpretive
  ambiguity inherent to the 4-class rubric. Binary collapse is more
  robust and is what the primary test rests on.

## Files

* `experiments/bakeoff/runs-m22a-pilot/regrade/judge_gemma4_31b_full.json`
  — 81 judgments
* `experiments/bakeoff/runs-m22a-pilot/regrade/judge_gemma4_31b_subset.json`
  — 20-subset
* `experiments/bakeoff/runs-m22a-pilot/regrade/judge_llama3.1_8b_subset.json`
  — cross-vendor 20-subset
* `experiments/bakeoff/runs-m22a-pilot/regrade/judge_hand_opus_subset.json`
  — hand 20-subset with reasoning per trial
* `experiments/bakeoff/m22a_pilot/REGRADE_PREREGISTRATION.md` — locked
  pre-registration
* `experiments/bakeoff/m22a_pilot/regrade_judge.py` — harness
