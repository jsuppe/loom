# M19 Pre-registration — Real-World Drift Detection Precision Eval

**Locked:** 2026-05-25
**Status:** Locked BEFORE harness build
**Scope:** medium pattern per user lock (single pre-reg, no sub-agent review, loom self-eval, ~50 historical versions sampled across 10 linked files)
**Methodology weight:** lighter than M22c+M22e arc; rigorous enough for the "second empirical leg" framing (augmentation: M22a-regrade positive; drift-detection: TBD this study)

## Why this pre-reg exists

The M22 augmentation-effectiveness arc produced one positive result
(M22a-regrade engagement 4-bin: loom-rationale uniquely produces
"proceeded with reasoning" 41% vs ≤6% other arms) and two
REFUTED-VIA-{FLOOR,CEILING} verdicts on compile/test grading
(M22c, M22e).

This pre-reg covers the second empirical leg: **does loom's
drift-detection actually catch real-world drift, or does it
false-fire on cosmetic changes?**

We are deliberately scoping LIGHTER than the M22c+M22e arc because
(a) the user explicitly chose "medium pattern" weight, (b) no
rationale arms are involved so leak-grading doesn't apply,
(c) a single self-eval study is sufficient to characterize
detector precision; recall is out of scope for v1.

## The detector we're evaluating

`loom check <file>` runs multi-channel drift detection. Channels:

1. **Content drift** — file's current `sha256` differs from the indexed
   `content_hash` stored on the linked `Implementation`.
2. **Structural drift** — LSP-detected symbol changes vs the indexed
   `symbol_signature_hash` (M10.3c; JS-only currently).
3. **Superseded** — requirement is `status=superseded` but still has
   linked implementations.

This study focuses on **content drift** as the dominant signal. Structural
and superseded are reported descriptively if they fire but not the
primary metric (structural is JS-only; superseded fires on a different
condition entirely).

## Workload

* **Target codebase:** `loom` itself (the repo this pre-reg lives in).
* **Linked-file set:** the 10 files currently bearing `Implementation`
  links in the loom store. Frozen at the pre-reg lock timestamp via a
  `linked_files.lock` artifact.
* **Per file:** sample up to **8 historical versions** from `git log
  -- <file>` (newest first). If fewer than 8 historical commits exist,
  use all of them. Expected total versions ≈ 30-50 across 10 files.
* **Comparison baseline:** the file's content_hash AS STORED IN THE
  LOOM STORE at the pre-reg lock timestamp. The store's indexed version
  is the "what the code should be" claim.

## What we measure

### Primary metric — precision of content-drift signal

For each (file, historical version) sample:

1. Compute `sha256` of the historical version (via `git show`).
2. Compare to the stored `content_hash`.
3. If hashes differ: **content-drift fires** (this is the detector's claim).
4. Hand-classify: was the diff between historical and stored version
   **semantically meaningful** (the file's docstring intent / public API
   / observable behavior changed in a way that could violate the linked
   req) or **cosmetic** (whitespace, rename, comment, dead-code removal,
   noise) ?

* **TP** — drift fires AND diff is semantically meaningful
* **FP** — drift fires AND diff is cosmetic
* **TN** — drift does NOT fire AND diff is cosmetic (by construction
  this is only "hashes match" cases, which means no diff at all)
* **FN** — drift does NOT fire AND diff is semantically meaningful
  (essentially zero by construction since any byte change flips the hash)

**Reported:**

* **Precision = TP / (TP + FP)** on the historical-version sample.
* **Per-file precision** (descriptive).
* **Volume signal** (descriptive): drift events per historical version
  examined.

### Recall is OUT OF SCOPE for v1

Recall requires curated "no-drift-should-fire" cases for which the
file genuinely IS aligned with the req in some altered form. By
construction every byte-change flips the hash and would fire drift. To
measure recall we would need either:

* Structural drift (semantic equivalence under refactor), which is JS
  LSP-only — too narrow for this eval
* Synthetic "rewrite that preserves semantics" cases

We **pre-register that recall is NOT measured** in v1 and the writeup
will state this explicitly. If precision is poor, recall is moot.

## Sample size

* **Pilot:** ≤ 10 (file, version) pairs, hand-classified, to validate
  the rubric.
* **Full:** all sampled pairs from the lock'd file set (target 30-50
  pairs depending on commit-history availability).
* **Stop early** if hand-classification reveals the rubric is ambiguous
  on >30% of cases; refine rubric and re-lock before continuing.

## Pre-registered prediction

Before any data is examined, we predict:

* **Precision = 50-70%** on the historical-version sample.

The reasoning behind the prediction (no peeking at data):
- Loom's linked files are mostly experimental scripts (phQ*, phR, phS,
  phT, phU) which evolve with the experiment; many "old versions" will
  be substantively different (TP).
- A non-trivial fraction of past commits will be incidental fixes
  (comment cleanups, prettier passes, imports rearranged) → FP.
- Cosmetic precision should not be 100% in any real-world codebase.

**Verdict bands:**

* **PRECISION-HIGH:** ≥ 80%. Detector is well-tuned for this codebase.
* **PRECISION-EXPECTED:** 50-79%. Matches prediction; detector useful
  but with room for false-positive reduction.
* **PRECISION-LOW:** 30-49%. Detector noisy; false positives outweigh
  signal value.
* **PRECISION-BROKEN:** < 30%. Drift is essentially noise; rethink
  channel design.

We commit to reporting whichever band lands.

## Classification rubric (LOCKED)

For each (file, historical-version) pair where drift fires, classify:

| Code | Bin | Definition |
|---|---|---|
| `M-API` | TP | Public-API signature changed (function/class names, parameter shape, return type) |
| `M-Behav` | TP | Observable behavior changed (control flow, error handling, side effects) |
| `M-Intent` | TP | Stated intent / docstring of the file changed in a load-bearing way |
| `C-White` | FP | Whitespace / line-ending / formatting only |
| `C-Rename` | FP | Identifier renames where call sites are also renamed; net behavior unchanged |
| `C-Comment` | FP | Comment/docstring edits without intent change |
| `C-Dead` | FP | Dead code removal / import cleanup |
| `Mixed` | TP | Both meaningful and cosmetic changes in same version; classified as TP |
| `Ambig` | excluded | Cannot decide with confidence; excluded from precision denominator |

`Mixed` is TP because the detector's job is to surface the meaningful
part; cosmetic noise around it is acceptable.

If `Ambig` exceeds 20% of cases, the rubric is broken — refine and re-lock.

## Exclusion rules

* **Identical-content versions** (hash match) → not counted as drift
  signal at all; no classification needed.
* **File no longer exists at historical version** (created after that
  commit) → excluded from sampling; document the exclusion count.
* **Binary / non-text files** → excluded.

## What MUST be reported in the writeup (locked)

* Precision overall + per-file
* Confusion matrix (TP/FP counts per bin code)
* Volume signal (drift events per version examined)
* Hand-classification methodology + rubric application notes
* Excluded versions (count + reason)
* Predicted vs actual precision band

## What's NOT acceptable

* Cherry-picking specific (file, version) pairs to include or exclude
  after hand-classification has begun.
* Adjusting the rubric retroactively after seeing classification results.
* Switching the primary metric from "content drift precision" to
  something else if precision lands in a bad band.
* Claiming "recall" results from this eval (it's out of scope).

## Null/negative result pre-commitment

If precision lands in `PRECISION-LOW` (<50%) or `PRECISION-BROKEN`
(<30%), the writeup leads with: "loom's content-drift detector has
a high false-positive rate on this codebase; users should expect to
triage noise alongside signal."

We do NOT retreat to "but qualitatively the signal was useful" as the
headline. If the numbers don't support the precision claim, that's
the finding.

## Sub-milestone status

| sub | status |
|---|---|
| M19.0 — pre-registration (this doc) | ✅ complete |
| M19.1 — harness + linked_files.lock | ⏳ next |
| M19.2 — pilot ≤10 pairs + rubric validation | pending |
| M19.3 — full eval on all sampled pairs | pending |
| M19.4 — hand-classification + analysis | pending |
| M19.5 — findings doc | pending |

## Files (planned)

* `experiments/m19_drift_eval/M19_PREREGISTRATION.md` — this doc
* `experiments/m19_drift_eval/linked_files.lock` — frozen baseline (M19.1)
* `experiments/m19_drift_eval/m19_harness.py` — sampling + drift-fire runner (M19.1)
* `experiments/m19_drift_eval/m19_classifications.csv` — hand-classifications (M19.4)
* `experiments/m19_drift_eval/M19_FINDINGS.md` — analysis writeup (M19.5)
