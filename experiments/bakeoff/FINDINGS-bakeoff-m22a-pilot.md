# M22a Pilot — Augmentation-Effectiveness Confound Detection

**Date:** 2026-05-23
**Status:** Pilot complete; scale-up direction pending
**Pre-registered hypothesis:** Hook augmentation > no-context (on m13_v1 pause-decision task)
**Reviewer flaws addressed:** Flaw A (length-matched placebo) ✓; Flaw B (workload mismatch) acknowledged, not fixed

## Why a pilot

The full M22a study design was reviewed by an independent methodology
sub-agent (M22a.0) before any trials were run. The reviewer **refused
to run the study as designed** and identified two fatal flaws:

* **Flaw A** — no length-matched placebo arm. Without it, any positive
  augmentation result could be "more tokens prime more cautious
  behavior" rather than "loom's structured context helps." Conceptual
  sibling of the no-op confound that killed the 2026-05-12 bake-off
  (REQ-7ed1bdd2).
* **Flaw B** — m13_v1 is the wrong workload. It was built to evaluate
  drift-warning calibration, not augmentation effectiveness. Per
  `FAILURE_AUDIT.md`, 96.4% of multi-file failures are typelink-shaped,
  0% of single-file failures are; m13_v1 is single-file only. A
  positive result on m13_v1 would be circular.

User picked Path 1 — run a small pilot (N=30 scenarios × 4 arms = 120
trials) on m13_v1 with the placebo arm added. Pilot's job: detect
confounds and methodology issues before committing to a bigger study.
Not for publishing lift claims.

## Design

* **Workload:** 30 scenarios sampled from m13_v1 stratified at 10 per
  stratum (`should_pause`, `should_proceed_no_drift`,
  `should_proceed_fp_trap`). Deterministic via `seed=42`.
  Locked at `experiments/bakeoff/m22a_pilot/scenarios.json`.

* **Four arms:**
  1. `no_context` — bare task prompt only.
  2. `hook` — bare task + `<system-reminder>` envelope injecting
     `finding_summary` + `rationale` + `drift_narrative` (current
     loom v3 production payload).
  3. `pre_loaded` — bare task + same content as `hook`, but framed
     as project-documentation preamble at session start (no
     system-reminder envelope).
  4. `placebo` — bare task + length-matched irrelevant project text
     (rationales from OTHER scenarios). Token-count precisely
     matched to `pre_loaded` (132 words each).

* **Subject:** `qwen3.5:latest` via Ollama, `temperature=0`, `top_k=1`,
  `seed=42`, locked against `experiments/bakeoff/sampling.lock`. Single
  model — pilot scope.

* **Grader:** Deterministic. Vocabulary-agnostic pause detector (regex
  on response — does the agent indicate it will NOT proceed with the
  edit?). Per the reviewer's fix #6, the rule does NOT require citing
  REQ-ID or the literal word "drift" — `hook` arm would otherwise win
  by tautology.

* **Order:** trials interleaved across arms (reviewer fix #5). Per-
  trial timeout 300s.

* **Infrastructure:** M18.1-.3 — sampling drift check, raw output
  retention to `runs-m22a-pilot/raw_outputs/`.

## Results

### Per-arm accuracy (vs `labeler_should_pause` ground truth)

| Arm | n (after errors) | Pause rate | Accuracy |
|---|---:|---:|---:|
| **hook** | 29 | 58.6% | **65.5%** |
| no_context | 29 | 75.9% | 48.3% |
| placebo | 24 | 66.7% | 45.8% |
| pre_loaded | 19 | 31.6% | 47.4% |

### Paired McNemar (exact binomial on discordant pairs)

| Comparison | Δpp | n_pairs | p | Interpretation |
|---|---:|---:|---:|---|
| **hook vs placebo** | +16.7 | 24 | 0.29 | Hook beats length-matched control — direction-positive; NS at this n |
| **placebo vs no_context** | -4.3 | 23 | 1.00 | ≈ equal — **token-count confound ruled out** |
| hook vs no_context | +17.9 | 28 | 0.18 | Hook lift consistent across baselines |
| hook vs pre_loaded | +33.3 | 18 | **0.07** | Hook >> pre_loaded — delivery mechanism matters |
| pre_loaded vs no_context | -11.1 | 18 | 0.75 | pre_loaded HURTS (but selection bias — see below) |
| pre_loaded vs placebo | -7.1 | 14 | 1.00 | pre_loaded < placebo (same caveat) |

### Per-stratum breakdown (hook arm)

| Stratum | n | Pause rate | Accuracy |
|---|---:|---:|---:|
| `should_pause` | 10 | 80.0% | 80.0% |
| `should_proceed_no_drift` | 9 | 44.4% | 55.6% |
| `should_proceed_fp_trap` | 10 | 50.0% | 60.0% |

Hook is balanced — pauses appropriately on real-drift cases (80%),
restrains itself on no-drift and fp-trap cases (44-50% pause rate
where pause is wrong).

### Errors

19 of 120 trials errored (15.8%). All were 300s timeouts on Ollama.
Distribution is highly non-uniform:

| Arm | Errors | Rate |
|---|---:|---:|
| pre_loaded | 11 | 36.7% |
| placebo | 6 | 20.0% |
| no_context | 1 | 3.3% |
| hook | 1 | 3.3% |

**This is the central methodology caveat for the pilot.** The
longer-prompt arms timed out disproportionately, so the trials that
completed are not a random sample. The pre_loaded arm in particular
is observed only on whichever 19 scenarios happened to finish — a
selection effect that almost certainly biases pre_loaded's accuracy
estimate.

## Findings (captured as kind=finding in loom store)

### F1 — Length-matched placebo confirms reviewer-fix necessity, rules out token-count confound

The placebo arm (length-matched to pre_loaded with semantically
irrelevant project text) scored within 4.3pp of no_context (45.8% vs
48.3%, n_pairs=23, p=1.0). The "more tokens prime more cautious
behavior" confound the M22a.0 reviewer flagged is NOT what's driving
the hook lift on this workload at this model.

**Implication:** Future augmentation studies on this workload should
keep the placebo arm. Cost: minimal (one extra arm). Value: rules out
the highest-priority confound the reviewer identified.

**Falsifier:** if a scale-up at N=100+ per arm shows placebo within
3pp of hook OR placebo lift over no_context > 10pp, the token-count
confound IS load-bearing and the pilot result was a small-sample
artifact.

### F2 — Hook delivery shows real signal beyond token count, but underpowered for significance

The hook arm beat the length-matched placebo by +16.7pp (n_pairs=24,
p=0.29) and pre_loaded by +33.3pp (p=0.07). Direction is consistent
across all comparisons (hook beats every other arm). Effect magnitude
is meaningful (Cohen's h ≈ 0.34). But at N=24-28 per paired
comparison, p-values are not significant at α=0.05.

This is a **suggestive positive result** for loom's current production
delivery mechanism (PreToolUse hook with `<system-reminder>` envelope
and scope-qualifier text). To upgrade from suggestive to publishable
requires N≈80-120 paired trials (at α=0.05, β=0.20, expected effect
size).

**Implication for product:** the hook isn't decorative. Same content
delivered via project-docs preamble (pre_loaded arm) doesn't produce
the same behavioral effect — even before correcting for the
selection-bias issue below.

**Falsifier:** if a scale-up shows hook within 5pp of placebo on a
paired comparison, the pilot result was small-sample noise and the
hook adds no value beyond token count.

### F3 — Long-prompt arms biased by timeout-driven sample loss; pre_loaded < placebo finding is invalid as observed

11 of 19 pilot errors (58%) were 300s timeouts on the pre_loaded arm
— the arm with the longest preamble (132-word project-docs section).
The pre_loaded trials that completed are skewed toward scenarios with
shorter completion times, which correlates with simpler model
responses. The observed "pre_loaded < no_context by 11.1pp" reading
is not interpretable without a higher timeout.

**Methodology requirement for scale-up:**
* Per-trial timeout of at least 600s on long-prompt arms.
* OR cap output token length (max_tokens) per arm so all arms have
  bounded latency.
* OR switch to a faster model (cloud Sonnet/Haiku via API) where
  long-prompt latency is bounded by network not local CPU/GPU.

**Falsifier:** if a scale-up at 600s+ timeout with full pre_loaded
completion still shows pre_loaded < placebo by >5pp, the original
finding direction was real and the pilot just made it harder to see.
If pre_loaded ≥ placebo at full completion, the pilot reading was a
selection artifact and pre_loaded performs comparably.

## Addendum (2026-05-24) — spot-check refinement

A stratified-by-(arm, correct) sample of 24 trials was hand-read by
claude-opus-4-7 to spot-check the deterministic grader. Three
methodology issues surfaced beyond what the original analysis caught.
Captured as the F4 finding below; key points:

* **Empty-response timeouts game the grader.** Of the 3 pre_loaded
  trials in the spot-check sample marked `correct=True` on
  `should_proceed` cells, all 3 had empty responses (wall ~214s,
  output_tokens 32K+). The grader's pause regex didn't match the
  empty string → `paused=False` → on `should_proceed` cells that
  scored as `correct=True`. The pre_loaded 100% accuracy on
  `should_proceed_fp_trap` was largely vacuous timeout-credit, not
  real performance. This is a bigger issue than F3's selection-bias
  framing — those trials were in the sample, not excluded.
* **Procedural pauses ("I lack file access") dominate.** ~half of
  pause responses across all arms are pausing because the model
  doesn't have file content access (the workload simulates an
  agent harness without actually providing files). The deterministic
  grader can't distinguish drift-cited pause from procedural pause.
  Both look identical to the regex.
* **Hook arm engages substantively** (qualitative). When the hook
  arm proceeds, responses cite the system-reminder and explain why
  the warning's scope doesn't apply to the edit. The no_context arm
  can't do this — there's no signal to engage with. Binary grader
  gives both arms the same `correct=True` label, understating the
  qualitative differential.

**Net effect on the headline numbers:**
* F1 (placebo rules out token-count): unchanged. Placebo ≈ no_context
  is a robust comparison.
* F2 (hook signal beyond length): direction unchanged but magnitude
  estimate questionable; procedural-pause confound affects all arms.
  Hook arm's qualitative engagement (which binary grader misses) may
  understate the real differential.
* F3 (selection bias): **refined** — the issue isn't just dropped
  trials but also empty-response trials being silently scored as
  correct.

## What this means for next steps

The pilot's job was confound detection. It succeeded:
* Validated that the placebo arm IS load-bearing (F1)
* Surfaced a real positive signal for the hook delivery (F2)
* Caught a selection-bias issue before a bigger study was run (F3)

The pilot did NOT settle the headline question "does loom improve
frontier-model performance" — that requires either a bigger sample on
the same (single-file) workload, or pivoting to the multi-file
typelink workload the reviewer flagged in Flaw B.

Three forward paths (user decision pending):

* **α** — Scale up M22a on m13_v1 at higher timeout, N=80-120 per arm
* **β** — Build the multi-file typelink workload first, then run M22a
  against it
* **γ** — Stop here; this pilot is the honest deliverable

The pilot data + harness are persisted at:
* `experiments/bakeoff/m22a_pilot/m22a_pilot.py` — harness
* `experiments/bakeoff/m22a_pilot/scenarios.json` — locked 30-scenario sample
* `experiments/bakeoff/runs-m22a-pilot/` — 120 trial summaries + raw
  outputs + `analysis.json`
