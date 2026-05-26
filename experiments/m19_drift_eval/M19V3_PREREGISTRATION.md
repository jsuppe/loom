# M19v3 Pre-registration — Req-Relevance Precision Study

**Locked:** 2026-05-26
**Status:** Locked BEFORE harness work
**Scope:** medium pattern per user lock — single pre-reg, no sub-agent review, hand-curated tight link set, hand-classification with AI first-pass + user spot-check for kappa
**Builds on:** M19v1 (REQ-56811be1) + M19v2 (REQ-6834d5b6)

## Why this pre-reg exists

M19v1 produced "precision 100%" on a 17-row sample dominated by file-
inception events. M19v2 enriched the link set to 30 impls and re-ran:
N=76, still 100% precision. Both numbers are honest but uninformative
because they measure **"did the file's content change since indexed"** —
which a SHA-256 hash detects with trivial 100% precision by
construction.

The actually-useful signal for users is **"when drift fires, does
this change matter for the linked requirement's specific intent?"**
That is unmeasured in M19v1/v2. M19v3 measures it.

## The question

> When the content-drift detector fires on a change to a file F linked
> to requirement R, what fraction of those drift events represent
> changes that **directly or indirectly touch what R is about**, versus
> changes that are real but **orthogonal to R's specific concern**?

This is precision in the user-facing sense: how much of the drift
signal is "warning about something I care about for this req" vs
"warning about a change to this file that happens to share the link
but doesn't affect this req's intent."

## Workload

### Tight link curation (M19v3.1, locked before eval)

A hand-curated set of **20-25 `(file, req)` pairs** where the req's
value text clearly captures what the file is responsible for. Curation
rules:

* Each file links to **exactly one req** (the one whose value most
  clearly describes the file's primary intent). No multi-req pairs
  in M19v3 — keeps classification unambiguous.
* Reject pairs where the link is "the file is sort of about this
  but a competent reviewer would dispute it." Note rejections in
  the lock file with reason.
* Drawn from `src/loom/` (the active surface area) plus a small
  number of `experiments/` files where evidence ↔ finding links
  are legitimately tight (e.g. M19V2_FINDINGS.md ↔ REQ-6834d5b6).
* Both the file and the req must exist at HEAD.
* Avoid links to recently-captured finding-kind REQs unless the
  link is genuinely meaningful (those have known vocabulary-
  overlap noise per M19v2 finding).

Persisted as `tight_links.lock` JSON before the eval runs. Lock'd
git HEAD captured at curation time. Each entry includes a one-line
rationale for the pairing.

### History walk

Per link, walk `git log --max-count=10 -- <file>` (one more than
v1/v2's 8 to compensate for the smaller link set). For each
historical commit C:
1. Read file content at C via `git show C:F` (same as v1 harness)
2. Compute sha256 vs `tight_links.lock`'s stored hash
3. If hashes differ → drift event → classify; if same → TN match

Expected N: 20 files × ~6 commits each average = ~120 (file, version)
pairs. Probably 70-100 drift events (TPs+FPs combined).

## Classification rubric (LOCKED)

For each drift event, classify the relationship between the diff and
the linked req's stated intent:

| Code | Bin | Definition |
|---|---|---|
| `R-Direct` | TP | The diff modifies code that directly implements the req's stated concern — adding to, refactoring, or changing the behavior the req is about. |
| `R-Indirect` | TP | The diff touches code adjacent to the req's concern in a way a careful reader would say "the user maintaining this req should know about this change" — e.g. error handling around the req-relevant code, refactoring that affects how the req-relevant code is invoked. |
| `R-Unrelated` | FP | The diff is real (substantive, not cosmetic) but is in a different concern of the same file. A user reviewing this drift would say "irrelevant to this req, just happens to share the file." |
| `Cosmetic` | FP | Pure whitespace, comment-only, import-rearrangement. (Same as M19v1/v2's C-* bins; collapsed here since this study focuses on relevance, not the cosmetic-vs-substantive axis.) |
| `Ambig` | excluded | Reasonable readers could classify either way. Excluded from precision denominator. |

**Primary metric:**
```
req-relevance precision = (R-Direct + R-Indirect) / (R-Direct + R-Indirect + R-Unrelated + Cosmetic)
```

`Ambig` is excluded from the denominator per locked exclusion rule.

`R-Indirect` is TP because warning the maintainer about adjacent
changes IS useful signal — the conservative threshold is "could
this affect how the req-implementation is interpreted." Only purely
orthogonal changes count as FP.

## Pre-registered prediction

* **Predicted req-relevance precision: 30–60%.** Wide band on
  purpose — this is the first time the metric is measured for loom.

* Reasoning behind the prediction (no peeking):
  - File-level linkage is intentionally coarse (loom links whole
    files, not symbol regions, unless `--symbol` is used)
  - Most real source files implement multiple concerns; a req-link
    captures one, but commits routinely touch others
  - I expect `R-Unrelated` to dominate FP — substantive changes
    to other concerns in the file
  - I expect `R-Indirect` to be more common than `R-Direct`
    because direct concern changes happen less often than
    adjacent-refactor commits

**Verdict bands:**

* **PRECISION-HIGH:** ≥ 70% — drift signal is mostly relevant; coarse file-level linking holds up
* **PRECISION-EXPECTED:** 30–69% — matches prediction; drift signal useful but noisy; argues for symbol-level (M10.x) linking
* **PRECISION-LOW:** 15–29% — drift signal mostly noise; file-level linking too coarse for user value
* **PRECISION-BROKEN:** < 15% — drift signal is essentially noise on most fires; rethink the channel

Report whichever band lands.

## Sample size

* **Pilot:** none — the eval IS the sample. The hand-curation step
  is itself the pilot equivalent (verifying the rubric works during
  curation).
* **Full:** all (file, version) pairs from the tight link set.
  Target N=70-100 drift events.
* **Stop early** if hand-classification surfaces a rubric problem
  (e.g. >25% Ambig); refine and re-lock the rubric, restart
  classification.

## Classification process (LOCKED)

1. **AI first-pass** via `classify_v3.py`, applying heuristics from
   `classify_v2.py` adapted for the new rubric:
   - Cosmetic detection: same as v2 (pure whitespace / pure comment /
     pure import → `Cosmetic`)
   - For non-cosmetic: read the diff + the linked req's value; apply
     heuristic mapping to R-Direct / R-Indirect / R-Unrelated /
     Ambig based on keyword overlap, file-region affected, and
     surface-similarity. Record the heuristic that triggered each
     decision.
2. **User spot-check** on a randomly-sampled 20% of drift events.
   Compute Cohen's kappa (user vs AI). Pre-registered floor:
   **kappa ≥ 0.5** for the AI classification to be credible enough
   to report as the primary number.
3. If kappa < 0.5, **the user's classifications on the spot-check
   sample become the only data reported** — i.e. fall back to a
   smaller-N hand-classified result rather than rely on noisy AI.
4. Classifications recorded in `m19v3_classifications.csv` with
   provenance per row: `ai_bin`, `user_bin` (when spot-checked),
   `final_bin`, `classifier_note`.

## Exclusion rules (LOCKED)

* **No-drift-fires entries** (hashes match — TN events) reported
  separately, excluded from precision denominator (precision is a
  per-fire metric).
* **Files that no longer exist at historical commit** excluded with
  count documented.
* **Ambig classifications** excluded from precision denominator,
  count documented.

## What MUST be reported (locked)

* Req-relevance precision overall + per-file
* Bin distribution (R-Direct / R-Indirect / R-Unrelated / Cosmetic / Ambig)
* Inter-rater kappa (AI vs user) on the spot-check sample
* Comparison row: M19v1 (precision 100%, n=17), M19v2 (precision
  100%, n=58), M19v3 (this number, n=TBD), with explicit explanation
  that v1/v2 measured a different (trivially-correct) precision
* Predicted vs actual precision band
* Excluded-event counts + reasons
* Per-link sample size (which links had richer history)

## What is NOT acceptable

* Cherry-picking the tight links AFTER seeing initial classification
  results
* Refining the rubric AFTER classification has begun (only allowed
  if pilot-stop triggered)
* Switching the primary metric ("but precision drops if we count
  R-Indirect as FP") — the R-Indirect=TP rule is locked
* Reporting only the favorable per-file results and hiding the rest

## Null-result pre-commitment

If req-relevance precision lands in PRECISION-LOW or PRECISION-BROKEN,
the writeup leads with **"loom's content-drift signal at file-level
granularity has high false-positive rate from a user-relevance
perspective. The right pivot is symbol-level linking via the
SemanticIndexer pathway (M10.x) — file-level fires too broadly to be
useful as a user warning."**

We do NOT retreat to "but the absolute hash precision is still 100%."
The user-relevance number is the headline whatever it lands.

## What this study does NOT establish

* Recall — same as v1/v2, out of scope
* Generalization to non-loom-self codebases
* Performance on symbol-level links (M10.x pathway) — different study
* The right tightness threshold for auto-linking (would require
  recall data)

## Carry-forward from v1/v2

| rule | source | status in v3 |
|---|---|---|
| Pre-reg locked before harness | v1 | preserved |
| Predicted-band requirement | v1/v2 | preserved |
| Hand-classification rubric locked before run | v1 | preserved (new rubric) |
| Ambig excluded from precision denominator | v1 | preserved |
| Anti-Texas-sharpshooter | v1/v2 | preserved |
| Null-result pre-commitment | v1/v2 | preserved (new framing for relevance) |
| File-creation events | v1/v2 | will appear in v3 too; treated as M-Behav (TP-shaped) per content-change rubric, BUT under req-relevance rubric they classify as R-Direct iff the file's inception IS the req's implementation. Documented case-by-case in classification. |

## Sub-milestone status

| sub | status |
|---|---|
| M19v3.0 — pre-registration (this doc) | ✅ complete |
| M19v3.1 — hand-curated tight link set | ⏳ next (will surface candidate list to user before locking) |
| M19v3.2 — harness adaptation | pending |
| M19v3.3 — eval run | pending |
| M19v3.4 — hand-classification (AI + user spot-check) | pending |
| M19v3.5 — findings | pending |

## Open decisions (surfaced to user before next step)

1. **Link curation method:** I will produce a candidate list of ~25
   `(file, req, one-line-rationale)` triples and surface it before
   locking `tight_links.lock`. User picks the final 20, drops/edits
   any with weak rationale. This keeps me from biasing toward links
   I touched this session.
2. **M19v2 loose links:** leave parallel (not unlinked). M19v3 reads
   only from `tight_links.lock`; the live-store loose links don't
   affect this study. Cleaner store can be a separate chore.
3. **Predicted band:** locked at 30-60% above. If user disagrees,
   adjust BEFORE proceeding to M19v3.1.

## Files (planned)

* `experiments/m19_drift_eval/M19V3_PREREGISTRATION.md` — this doc
* `experiments/m19_drift_eval/tight_links.lock` — 20 hand-curated pairs (M19v3.1)
* `experiments/m19_drift_eval/m19v3_harness.py` — wrapper over m19_harness (M19v3.2)
* `experiments/m19_drift_eval/m19v3_classifications.csv` — rows with classifications (M19v3.4)
* `experiments/m19_drift_eval/classify_v3.py` — heuristic classifier (M19v3.4)
* `experiments/m19_drift_eval/M19V3_FINDINGS.md` — analysis writeup (M19v3.5)
