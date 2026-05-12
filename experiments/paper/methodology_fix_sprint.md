# Methodology Fix Sprint — Plan of Record

**Status:** In progress, started 2026-05-11
**Companion to:** `independent_review_2026-05-11.md` (review #1),
  internal review #2 (this doc references it inline)
**Pivot rationale:** Two independent methodology reviews identified
  substantive issues with the underlying experiments. The author
  has pivoted from paper revision to experiment revision.

## Why this sprint exists

The paper at `experiments/paper/draft.md` claimed to extend Khan
(2025) "The Prompting Inversion" across 7 models and 3 scenarios.
Two independent methodology reviews identified that several
load-bearing experiments were measuring something different from
what the paper claimed. Specifically:

1. **Temperature was never locked.** Ollama defaults to T≈0.8;
   Claude CLI uses API default T=1.0. Cross-model "lever attendance"
   claims are partly cross-model temperature variance.
2. **S1 reference file already complies with the contrarian rule.**
   The grading test cannot distinguish "model followed rule" from
   "model preserved existing implementation."
3. **§4.4 N=50 R_sanity_pro silently merges data from a different
   harness phase** than R_imperative_pro.
4. **S1 prompts include a `## Semantic context` block that S2/S3
   prompts don't.** Cross-scenario comparisons confounded.
5. **5 dropped qwen3.5:27b trials, undocumented.** Possible
   selection bias.

The first reviewer flagged these as workshop-quality blockers. The
second reviewer identified additional concrete mechanical issues
with my proposed fix plan (Ollama sampling-parameter completeness,
byte-equality limits of no-op detection, etc.). This document
captures the revised sprint plan that incorporates both reviews.

## Sequencing (per second review's recommendation)

The plan executes in this order, not the original (1→2→3→4→5)
order, because Step 2 establishes the data-collection foundation
that downstream steps need:

| # | Step | Effort | Wall |
|---|---|---|---|
| 1 | Update phY/phT harness: Ollama sampling params + llm_response_full + strip JS semantic context | 1 hr | — |
| 2 | Smoke test on Ollama (qwen2.5-coder S2 R_imperative) at temp=0 | 5 min | 10 min |
| 3 | Re-run 5 dropped qwen3.5:27b trials with new harness | 5 min | 15 min |
| 4 | Verify phS vs phT V_FULL prompt byte-diff (closes §4.4 hand-wave) | 10 min | — |
| 5 | Anthropic SDK backend (replaces CLI for temperature control) | 2 hr | requires API key |
| 6 | SDK-vs-CLI smoke pilot on Sonnet R_imperative_pro (disentangle confounds) | 30 min | ~$1 API |
| 7 | Sonnet S1 R_sanity_pro + R_imperative_pro at N=50 via SDK temp=0 | 30 min | ~$5-10 API |
| 8 | Sonnet S2 R_baseline + R_imperative at N=50 via SDK temp=0 | 30 min | ~$5 API |
| 9 | Re-run all S1 cells (cross-vendor) with no-op-detection-capable harness | 1 day | 15-30 hr Ollama |
| 10 | AST-or-diff no-op detection + re-aggregation of new S1 data | 3 hr | — |
| 11 | Strip-JS-from-S1 re-run of cross-scenario cells | 1 day | 16-20 hr Ollama |
| 12 | Add length-controlled "R_padding" cell (Sonnet imperative-poison length isolation) | 4 hr | 1 hr API |
| 13 | Multi-comparison correction (Bonferroni / BH analysis) | 2 hr | — |
| 14 | Sub-test-level re-aggregation from existing `grade_stdout_tail` data | 1 day | — |
| 15 | Resolve §4.5 "deterministic at default temperature" — either drop or re-run | 2 hr | — |

**Realistic effort total:** 5-8 days of focused work + ~50-90 hr of
unattended wall-clock execution on Ollama. Anthropic API spend:
~$15-25.

## Decision points

### D1. Anthropic API key authorization (gates Steps 5-8 and 12)

The user previously declined an API key in favor of Claude Code CLI
auth via Max plan. The CLI does NOT expose a `--temperature` flag
(verified). Locking Sonnet temperature requires the raw Anthropic
SDK and an API key. Estimated cost: ~$15-25 across Steps 5-8 + 12.

**Default if not authorized:** Skip Steps 5-12 (the Anthropic-side
temperature-locked work). Sonnet findings would stay at "default
temperature" with explicit limitation disclosure. The within-Qwen
findings and the Ollama-side cross-vendor findings can still be
strengthened by the rest of the sprint.

### D2. Strip-JS-from-S1 vs add-Python-LSP-to-S2/S3 (gates Step 11)

The original plan was vague between these. Sprint commits to
**strip JS from S1** path: simpler harness change, faster re-runs.
Cost: re-running every S1 cross-vendor cell (5+ models × N=20+).

### D3. Step 9 vs Step 11 collision

Step 9 (re-run S1 with model outputs) and Step 11 (strip JS from S1)
both re-run S1 cells. They should be combined: a single S1 re-run
pass with both the no-op-detection-capable harness AND the
JS-semantic-context-stripped prompt builder. Net Ollama wall: ~15-30 hr
total, not 30-60 hr.

## What the sprint will leave undone (acknowledged)

- **Opus replication** (still missing tier coverage)
- **GPT proprietary replication** (different vendor)
- **S4 anti-pattern scenario** (S1 universality claim still rests on
  N=1 scenario)
- **Within-vendor coverage for Google/Meta/OpenAI** (only one model
  each)
- **Cross-domain validation** (does lever attendance transfer beyond
  code-rule compliance?)

These are deferred to a v2 sprint or future work.

## Success criteria

After the sprint completes:

1. **All headline cells have temperature-controlled data.** Sonnet
   imperative-poison N=50 + Sonnet S2 N=50 + Ollama cross-vendor
   cells at temp=0.
2. **No-op-vs-compliant-rewrite breakdown is reported** for every
   high-compliance S1 cell.
3. **The §4.4 phase merge is closed** by re-running R_sanity_pro
   under R_imperative_pro-identical conditions.
4. **S1 and S2/S3 prompts are structurally equivalent** (semantic
   context block removed from S1).
5. **All dropped trials are accounted for** (re-run or explicitly
   discussed).
6. **Multi-comparison correction is applied** to the cell grid.
7. **Sub-test-level analysis is at least optional** for readers.

After all of these: paper revisable to workshop-defensible quality.
Without API key (D1): partial coverage — Ollama-side strong;
Anthropic-side flagged with explicit "default temperature"
limitation.

## Sprint progress log

(updated as work completes)

### 2026-05-11: Sprint started

- [ ] Step 1: harness update — in progress
- [ ] Step 2: smoke test
- [ ] Step 3: 5 dropped qwen3.5 trials
- [ ] Step 4: phS vs phT byte-diff
- [ ] D1 decision pending (API key)
- [ ] Step 5-8: gated on D1
- [ ] Step 9+11 (combined): pending
- [ ] Step 10: pending
- [ ] Steps 12-15: pending
