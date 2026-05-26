# M22e Pre-registration — Pre-Pilot Amendments

This document records changes made to the M22e design AFTER the locked
pre-registration but BEFORE the pilot run. Each amendment is a
discovered-bug fix uncovered during M22e.3 smoke-testing — the kind of
change that pre-reg locks explicitly allow (and even encourage) when
the original design has an obvious mechanical error.

**These are NOT scope changes, falsifier-threshold changes, or
hypothesis re-framing.** None of the locked methodology rules from
M22c (null-result pre-commit, anti-Texas-sharpshooter, falsifier
thresholds, exclusion rule, primary metric) are touched.

## Amendment 1 — Placebo pool: task-orthogonal text, not "other scenarios' rationales"

**Discovered:** 2026-05-25 during M22e.3 smoke test (s_validate × placebo, t1).

**Symptom:** The placebo trial produced 4096 output tokens with no
extractable code (M22a F3-shape failure). Inspecting the raw output
showed the model fell into a runaway-comment loop trying to reconcile
the placebo's borrowed-from-s_retry framing ("Distinguish 'truly
retriable' errors from terminal errors") with the s_validate task.

The placebo text was drawn from other scenarios' rationales (per the
original pre-reg). For M22a/M22b/M22c this had not surfaced because:
- M22a/M22b had different model+workload combinations
- M22c had ALL arms floor-failing at 0% so any placebo confound was
  invisible behind the model-capability ceiling

For M22e (single-file JS with a capable model on this workload), the
"borrowed rationale" placebo text is plausibly project-conventions-shaped
enough that the model takes it seriously as guidance for the current
task — and tries to apply it. That's not a length-matched neutral
control; that's a semantic-interference confound.

**Fix:** Replace the placebo pool with a fixed paragraph of
task-orthogonal project notes (CI/formatting/release-process content)
that resembles "project conventions" text in shape and length but
cannot apply to any of the three target functions. Documented inline
in `m22e_pilot.py::_NEUTRAL_PROJECT_NOTES`.

**Why this is a bug fix, not a goal-post move:**
- The locked spec was "length-matched irrelevant text." The original
  implementation used a borrowed-rationale source that turned out to
  NOT be irrelevant in the operational sense.
- The fix moves toward the locked spec's intent (truly irrelevant),
  not away from it.
- Pre-pilot, not post-pilot.
- All three arms (no_context / hook_rationale / hook_fact) still use
  identical framing; only placebo's CONTENT changes.

**Re-smoke result:** see commit log for the fixed smoke trials.

## Amendment 2 — Sampling: temp=0.3 + per-trial seed (not temp=0 + fixed seed)

**Discovered:** 2026-05-25 during M22e.3 smoke-test determinism check.

**Symptom:** Running 2 trials of (s_validate, no_context) with the
inherited M22c sampling config (temp=0.0, top_k=1, fixed seed=42)
produced bit-identical raw outputs (verified by SHA-256 hash match).
This means under the planned pilot N=24 (2 trials/cell) and sweep
N=120 (10 trials/cell), every trial within a cell is a duplicate:

* Effective pilot N = 12 unique trials (3 scenarios × 4 arms × 1)
* Effective sweep N = 12 unique trials (same — no gain from more trials)
* McNemar paired-pairs per arm-pair = 3 (one per scenario)
* Minimum detectable effect at p≤0.05 ≈ 70+ pp

The original M22c pre-reg's gate 3 ("if all 5 bit-identical, drop
trials/scenario back to 1") was specified — but applied to M22e, it
collapses the sweep to the point of statistical incoherence. M22c did
not surface this because every arm failed at 0% floor; the
within-cell-determinism issue was masked by the M22c gate-6 failure.

**Fix:** Move to a sampling regime that enables within-cell variance
while preserving per-trial reproducibility:

* `temperature: 0.3` — modest sampling exploration (was 0.0).
* `top_p: 0.9, top_k: 40` — standard sampling defaults (was 1.0 / 1).
* `seed: hash((scenario_id, arm, trial_n))` — deterministic per-trial
  seed so re-running trial N reproduces exactly the same output, but
  trial 1 and trial 2 of the same cell get different seeds and
  therefore different (correlated) samples.

This restores meaningful N for both pilot (24 real trials) and sweep
(120 real trials), with paired-McNemar pair counts of 6 (pilot) and
30 (sweep) per arm-pair.

**Why this is a bug fix, not a goal-post move:**

* The pre-reg specified neither temperature nor seed strategy
  explicitly; both were inherited from `m22c_pilot.py` as unstated
  harness conventions. Amending an unstated convention before the
  pilot runs is bug-fix-shaped, not goal-post-shaped.
* The locked spec around "≥2 distinct response strings per cell"
  (gate 3) implies non-zero variance was always intended.
* Per-trial seed is deterministic and replayable; this is NOT moving
  to a non-reproducible regime.
* The fix is pre-pilot, applies to ALL arms equally, and does not
  change any falsifier threshold, hypothesis, primary metric, or
  exclusion rule.
* Without the fix, the M22e study cannot scientifically distinguish
  any effect under ~70pp from null — running it would be a costly
  exercise in producing inconclusive data.

**Caveat acknowledged:** non-zero temperature means a single trial's
outcome is one draw from a probability distribution, not the model's
single most-likely answer. The aggregate over N trials/cell is what
the McNemar test is designed for. We will report sampling parameters
explicitly in the writeup.

**Re-smoke result:** see commit log for confirmation that t1 and t2
under Amendment 2 produce distinct outputs.

## Carry-forward unchanged

Everything in M22E_PREREGISTRATION.md remains locked. This amendment
file ONLY records bug-level fixes to the harness during smoke-testing.
Any change to the comparison structure, falsifier thresholds,
hypothesis, primary metric, exclusion rule, gates, or carry-forward
rules would be a methodology violation and would invalidate the study.
