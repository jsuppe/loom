# M19v2 Findings — Enriched Drift-Detection Precision Eval

**Locked:** 2026-05-26
**Status:** v2 eval complete N=76 (58 drift-fires + 18 TN match cases). Heuristic-classified 58/58 as TP. Precision = 100%.
**Pre-reg:** [M19_PREREGISTRATION.md](./M19_PREREGISTRATION.md) (unchanged from v1)
**v1 finding:** [M19_FINDINGS.md](./M19_FINDINGS.md)

## What changed from v1

v1 ran on the 10 linked impls present at session start; sample was
degenerate (12 of 17 cases were file-inception events). v2 added
20 new src/loom/ links via auto-link enrichment (M19v2 enrich.py) —
bumping the linked-impl count to 30. Re-ran the M19 harness against
the enriched store.

| | M19v1 | M19v2 |
|---|---|---|
| Linked impls | 10 | 30 |
| Sample N | 17 | 76 |
| drift_fires=yes | 17 | 58 |
| drift_fires=no (TN) | 0 | 18 |
| Inception events in TP set | 12/17 | ~7/58 |
| Active src/loom/ files | 1 | 19 |

## Result

```
Classification summary (N=76 total, 18 no-drift TN):
  TP   : 58
  FP   : 0
  Ambig: 0  (excluded from precision)
  Precision (TP / (TP+FP)) = 100.0% (n=58)

Bin distribution (per locked rubric):
  M-API     : 40
  M-Behav   : 18
```

**Precision unchanged at 100%** despite the enriched sample. The
pre-registered prediction (50-70% precision) was wrong in the same
direction in v2 as in v1 — over-estimating the FP rate.

## Bugs surfaced during M19v2 (and fixed)

The enrichment pass surfaced THREE real loom bugs:

1. **`services._read_file_content` defaulted to system encoding.**
   `Path.read_text()` without an explicit encoding uses cp1252 on
   Windows, which dies on UTF-8 source files containing em-dashes
   or non-ASCII identifiers. **Fixed** in this session: now passes
   `encoding="utf-8", errors="replace"`.

2. **`_ollama_embed` failed silently on large files.**
   `nomic-embed-text` returns HTTP 400 `input length exceeds the
   context length` for inputs over ~7000 characters (despite
   documented 8K-token context). The error was caught by the
   ollama-outage handler and silently fell back to hash-pseudo-
   embeddings — producing semantic-similarity NOISE that was being
   reported to users as real matches. **Fixed** in this session:
   `_ollama_embed` now truncates input to 4000 chars (conservative
   cap surviving dense code tokenization).

3. **Spurious auto-links from hash fallback.** Before the fix above,
   the first enrichment pass auto-linked 5 src/loom/ files to
   essentially random requirements (e.g. `paths.py` → REQ-73bcd158
   which is an M22e finding). Rolled back after the fix and
   re-linked with real embeddings.

These bugs would have been silent in normal use — they happened to
surface here because M19v2's enrichment touched the full file-content
embedding path that few other code paths exercise on large files.

## Honest caveats on the 100% precision number

The classifier was AI-applied via deterministic heuristics
(`classify_v2.py`). The heuristics are biased toward TP:

* Pure whitespace / pure comment / pure import-rearrangement → FP
* Anything else with substantive line changes → TP
* Default for ambiguous shapes → Ambig (excluded from denominator)

In practice, no commit produced enough pure-cosmetic changes to one
of the 30 linked files to trigger an FP bin. **This is not because
loom's drift detector is magically perfect; it's because real Python
commits to active source files almost always include at least some
substantive change.** PEP-8 cleanup, formatter passes, and pure-
comment edits aren't usually their own commits per file — they
piggyback on substantive changes.

### Deeper question the v2 metric does NOT answer

Hash-based drift detection has 100% precision on **"the file's
content changed since indexed"** — that's trivially correct by
construction.

What it does NOT distinguish is **"the change violates the linked
req's specific intent"** (the actually-useful signal) from **"the
change is real but doesn't matter for the linked req"** (noise from
the user's perspective).

Example: `cli.py` is auto-linked in M19v2 to a few REQs. A 1-line
commit "remove undefined SKILL_DIR reference" triggers drift
because the file's hash changed. But the linked REQs are about
cli's overall purpose, not the specific SKILL_DIR detail. The
hash-detector said "drift" (correct under "content changed"); a
strict req-relevance reading would say "this change doesn't
violate the linked req's intent" (i.e., warning is noise).

Measuring **req-relevance precision** requires per-(file, req, commit)
hand-judgment of whether the change matters for THAT req. That is
out of scope for v2.

## Caveat on the enriched-link semantic quality

The 20 new auto-links were created via embedding similarity at
distance ≤ 0.45 (cosine ≥ 0.55). Inspecting the actual links:

| file | top match req(s) | semantic quality |
|---|---|---|
| `services.py` | REQ-81a67c36, REQ-51455681, REQ-ab5b84b0 | moderate — REQs are about loom's services layer broadly |
| `cli.py` | REQ-51455681, REQ-4d3e74f2, REQ-bdb1e667 | moderate — generic CLI/cmd content |
| `intake.py` | REQ-73bcd158 (M22e finding!), REQ-ba817d28, REQ-40b70660 | LOOSE — M22e finding is about a research result, not the intake module |
| `embedding.py` | REQ-7e2d6518 (layout-hallucination finding), REQ-2a621c40 | LOOSE — finding REQ shares vocabulary by accident |

Recently-captured FINDING-kind REQs frequently appear in the top
matches because they share vocabulary with the technical code
they describe (they were written DURING this session about that
code). This is an **artifact of the session** that wouldn't
recur on an established codebase where findings are stable.

In a real "loom self-eval to characterize drift detection" study,
these loose links would not be auto-applied — they'd be hand-
curated to map each file to the REQ that actually captures its
intent.

## What this v2 round actually tells us

* **Hash-based content drift correctly fires on real code changes.**
  No technical bug in the detector itself; 100% of triggered signals
  correspond to non-cosmetic diffs.
* **Loom on Windows had three silent failure modes** in the auto-link
  path (encoding, embed-size, hash-fallback noise) that v2's
  enrichment pass surfaced and fixed.
* **Pure-cosmetic per-file commits are rare in this codebase.** Real
  developer commits to a file include substantive work, even when
  the diff is small.

## What this v2 round does NOT establish

* That hash-drift is useful **as a warning signal** in the sense
  that matters to users (req-relevance precision unmeasured).
* That loose auto-linked impls are good ground truth (they aren't).
* That precision generalizes to a non-self-eval codebase.
* Recall (still out of scope per v1 pre-reg).

## Pre-registered prediction vs actual (v2)

* **Predicted: 50-70%** (held over from v1 pre-reg).
* **Actual: 100%.**

The prediction was wrong in v2 for the same reason as in v1: the
prediction implicitly assumed a baseline cosmetic-commit volume that
real-world Python commits don't produce.

This is itself a learning — the pre-reg's prediction model was
based on intuition about "how many commits are cosmetic on a code
file" that doesn't match the actual ratio. Future drift studies
should pre-register predictions grounded in empirical commit-stat
distributions, not intuition.

## Methodology assessment (running tally)

Methodology pattern (REQ-3896db58) earned its keep again:

* The **pre-reg gates** caught nothing this round (precision was
  good, gates passed by construction).
* The **predicted-band requirement** did its job: by recording the
  prediction (50-70%) the writeup is forced to confront that the
  prediction was wrong, even though the result direction is
  "favorable." Without that lock, the result could be reported as
  "loom drift detection works, 100% precision!" without surfacing
  the systematic prediction mistake.
* The **bugs surfaced are themselves the most valuable deliverable
  from M19v2** — three silent failures in production code paths
  the test suite didn't exercise.

Pattern count: now 9/9 (8 from this session's prior studies + the
prediction-vs-actual surfacing here).

## Pivot proposals

If "characterize drift detection signal-usefulness for users"
remains the active goal:

1. **M19v3 — req-relevance precision study.** Hand-curate 20-30
   tight (file, req) linked-impl pairs (not auto-linked) with
   clearly-stated req intent. Then walk history and for each
   triggered drift, classify "does this change violate THAT req's
   stated intent?" Measures the actually-useful signal. ~1 day work.
2. **M19v4 — synthetic-edit recall study.** For each tightly-curated
   linked impl, manually author 3 known-cosmetic and 3 known-
   substantive edits; measure both precision and recall. Populates
   the FP bin by construction and gives recall numbers v1/v2 didn't.
3. **Stop drift-eval, take the bug-fix value.** v2's most concrete
   deliverable was 3 production bug fixes (encoding, embed-size,
   hash-fallback). Those alone justify the session. Move to
   different operational work (M17.4 exports, M20.x productionization,
   M14.4 triage loop).

## Sub-milestone status

| sub | status |
|---|---|
| M19v2.0 — enrich script | ✅ complete |
| M19v2.1 — eval run (N=76) | ✅ complete |
| M19v2.2 — heuristic classification | ✅ complete (58 TP, 0 FP, 0 Ambig) |
| M19v2.3 — bug fixes (3) | ✅ encoding, embed-size, hash-fallback rollback all shipped |
| M19v2.4 — findings (this doc) | ✅ complete |

## Files

* `experiments/m19_drift_eval/enrich.py` — auto-link enrichment script (locked params: src/loom/*.py, distance ≤ 0.45, top 3 reqs per file)
* `experiments/m19_drift_eval/classify_v2.py` — heuristic classifier with per-case rationale
* `experiments/m19_drift_eval/enrichment_log.txt` — what got linked (with distances)
* `experiments/m19_drift_eval/m19_classifications.csv` — 76 rows with classifications
* `experiments/m19_drift_eval/M19V2_FINDINGS.md` — this doc
* `src/loom/services.py` — encoding fix in `_read_file_content`
* `src/loom/embedding.py` — truncation fix in `_ollama_embed`
