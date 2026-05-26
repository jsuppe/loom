# M19 Findings — Drift Detection Precision Eval

**Locked:** 2026-05-25
**Status:** Eval complete N=17. Precision result is in the
PRECISION-HIGH band per the pre-reg, but the headline is the
sample-composition finding, not the precision number.
**Pre-reg:** [M19_PREREGISTRATION.md](./M19_PREREGISTRATION.md)

## Headline

**Content-drift detector fires correctly on 17/17 historical-version
samples (precision 100.0%). However, the sample composition is
degenerate: 12 of 17 cases are file-inception events (no prior
version existed); zero cases are cosmetic-only commits. The 100%
precision is honest at the locked rubric but does NOT generalize to
"drift detection works in real-world editing workflows" because the
sample contains no opportunities for false positives.**

## Eval result (N=17)

```
TP    : 17
FP    : 0
Ambig : 0
Precision (TP / (TP+FP)) = 100.0%  (n=17)

Bin distribution:
  M-API     : 1    (indexers_js.py health() addition)
  M-Behav   : 14   (12 inception + 2 substantive edits)
  M-Intent  : 2    (findings doc + results JSON inceptions)
```

## Why the sample is degenerate

The pre-reg locked: **10 linked files × up to 8 historical versions =
target 30-50 pairs.**

Actual sample = 17 pairs because the linked files have SHORT histories:

| file | versions in git log |
|---|---|
| phT_rule_precedence_smoke.py | 3 |
| phU_imperative_followups_smoke.py | 2 |
| FINDINGS-bakeoff-v3-payload-sharpening.md | 1 |
| phQ3_crosssession_js_stub_clean_smoke.py | 1 |
| phQ4_crosssession_js_no_stub_32b_smoke.py | 1 |
| phQ7_crosssession_js_with_test_refs_smoke.py | 1 |
| phR_rhetorical_ablation_smoke.py | 2 |
| phS_anti_rationale_smoke.py | 2 |
| indexers_js.py | 3 |
| warrants_l2_results.json | 1 |

Most linked files are experiment-driver scripts created in a single
commit and then iterated on 0-2 times. None have the "20+ commits with
mix of substantive and cosmetic edits" history pattern that would
populate the FP bins.

The CSV bin distribution confirms it: 0 entries in any C-* (cosmetic)
bin. The sample structurally cannot produce FPs.

## What this means

The eval as designed measures **detector correctness on existing
linked-file commit history.** What it does NOT measure:

1. **Real-world drift-detection FP rate.** Requires cosmetic-only edits
   to indexed files to be in the sample.
2. **Drift-detection signal utility for in-flight editing.** The
   detector's intended use is "developer is editing a file; signal
   fires when the edit deviates from req." Historical inception
   commits don't simulate that workflow.
3. **Whether the detector helps on richly-linked codebases.** Loom-self
   has only 10 linked impls; a project that's been heavily dogfooded
   (Sparkeye? a real consumer?) would have hundreds of links and a
   meaningful FP rate.

The 100% precision number is **technically correct** under the pre-reg's
locked rubric. It is **not useful evidence** that drift detection works
well in practice.

## Pre-registered prediction vs actual

* **Predicted precision: 50-70%** (with reasoning: experiment-driver
  files evolve substantively; some commits should be incidental fixes
  → expected FP).
* **Actual precision: 100%** — well above the predicted band.
* **Reason for prediction failure:** I underestimated how few cosmetic
  commits there are in the linked-file history. The "fix prettier
  pass" type of commit didn't make it into the sample because it
  didn't touch any linked file at all.

This is a useful prediction failure: it surfaces that the eval design
implicitly assumed a baseline level of cosmetic-commit volume which
doesn't exist on loom-self's linked-file subset.

## Pre-reg gates — all PASS, but moot

| pre-reg check | result | meaningful? |
|---|---|---|
| Sample size ≥ target 30 pairs | 17 pairs (BELOW target) | sample too small + biased |
| Ambig cases < 20% | 0% | trivially fine — all unambiguous TPs |
| Rubric self-consistent | yes | yes |
| Hand-classification documented | yes (via classify.py with AI provenance noted) | partial — see "Honesty caveats" |

## Honesty caveats

* **Classification was AI-applied, not human-applied.** The pre-reg
  said "hand-classified"; the implementation was an AI assistant
  applying the rubric per the locked bin codes, with provenance
  recorded in the `classifier_note` column. Each classification has
  a one-line rationale. User can spot-check or override in the CSV.
* **0% inter-rater reliability check** was done — there was no
  second classifier. For a v2 eval, hand-classification by the user
  on a random 5-row subset would provide a kappa estimate.
* **Sample drawn from author's own repo.** The linked impls reflect
  the author's curation; no claim about generalization to other
  codebases.

## What this finding does NOT claim

This study does NOT support any of:

* "Loom's drift detector works well in production codebases."
* "False positive rate is low."
* "Recall is good." (Recall was out of scope per pre-reg.)

The honest framing is: "**On the available sample on this codebase,
the detector correctly classified every version as drifted. The sample
is too biased toward inception events to draw broader conclusions
about FP rate.**"

## Pivot proposals (for user)

If "validate drift detection in production-realistic conditions"
remains an active goal, options:

1. **M19v2 — Enriched-link approach.** First do an indexing pass on
   loom's `src/loom/` modules to grow linked-impl count from 10 to
   ~50. Then re-run the eval. Likely to produce FP cases from
   non-substantive commits in the active source code. ~1 day's work
   for the indexing + eval.
2. **M19v3 — Synthetic-edit eval.** For each linked file, generate
   3-5 synthetic edits (mix of true semantic change + cosmetic-only)
   and run drift check on each. Lets us measure FP rate by
   construction. More work to author realistic synthetic edits, but
   the only way to populate the FP bin reliably. ~2-3 days.
3. **M19 stop, accept the limitation.** The current finding ("loom-self
   has too few linked files for drift-detection evaluation to produce
   FP signal") is itself useful — it documents that dogfooding loom
   on its own repo has not enriched the link graph enough for
   self-evaluation. Move on to operational work elsewhere.

## Methodology assessment

The pre-reg's "medium pattern" weight produced exactly the right
result for the available data: 1 pre-reg doc + 1 harness + 1 eval +
1 findings doc, in proportion to a study whose finding turned out
to be about its own sample composition.

The pre-reg's "predicted precision" requirement (50-70%) caught
the sample-composition problem precisely because the prediction
diverged from actual (100%). Without that prediction in the pre-reg,
"precision 100%, eval complete, done" would have been a tempting
but misleading writeup.

Pre-reg pattern continues earning its keep — this is its 8th
study and 3rd time it caught a result that would have been
misleading if reported at face value.

## Sub-milestone status

| sub | status |
|---|---|
| M19.0 — pre-registration | ✅ complete |
| M19.1 — harness + linked_files.lock | ✅ complete |
| M19.2 — pilot ≤10 pairs + rubric validation | ✅ effectively merged with M19.3 (sample was small) |
| M19.3 — full eval | ✅ complete (N=17) |
| M19.4 — classification + analysis | ✅ complete (AI-classified per rubric) |
| M19.5 — findings doc | ✅ this doc |

## Files

* `experiments/m19_drift_eval/M19_PREREGISTRATION.md` — locked design
* `experiments/m19_drift_eval/linked_files.lock` — frozen baseline (10 impls)
* `experiments/m19_drift_eval/m19_harness.py` — sampling + drift-fire runner
* `experiments/m19_drift_eval/classify.py` — AI-classification pass with per-case rationale
* `experiments/m19_drift_eval/m19_classifications.csv` — all 17 rows with classifications
* `experiments/m19_drift_eval/M19_FINDINGS.md` — this doc
