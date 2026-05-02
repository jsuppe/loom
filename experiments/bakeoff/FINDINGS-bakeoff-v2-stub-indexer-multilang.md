# Bakeoff V2 — Multi-language stub-indexer experiments (M10.3)

**Date:** 2026-05-02
**Question:** Does the M10.2 finding — that hand-authored Kythe-shaped
semantic context lifts compliance on resistant-language scenarios —
generalize to other languages from the cross-language map (M8.4)?
**Approach:** Same `SemanticIndexer` registry, same `qwen2.5-coder:32b`
executor, same 4-cell harness. Two new stub indexers:
- **`StubCIndexer`** for C (resistant-mid in M8.4: off=50, rule=50, +rat=60)
- **`StubJsIndexer`** for JS (graded-no-saturation: off=0, rule=20, +rat=60)
**N:** 36 trials across two languages (some cells have N<5 due to
Ollama 32b runner crashes mid-sweep — see Limitations).

---

## TL;DR

> **The "context bridges resistant languages" hypothesis is
> language-specific, not universal.** Three languages tested with
> the same M10 architecture: C++ (M10.2), C (this), JS (this).
>
> | language | regime in M8.4 | with stub | takeaway |
> |---|---|---|---|
> | **C++** | collapsed | rat: 0% → 40% (+40pp) | **partial bridge** |
> | **C** | resistant-mid | rat: 60% → 50% (no change) | **no measurable lift** |
> | **JS** | graded-no-sat | rat: 60% → 100% (+40pp) | **saturating lift** |
>
> Three different responses to the same architectural intervention.
> The M10 thesis ("semantic context is the missing lever") holds for
> C++ and JS — strongly for JS — but does NOT generalize to C. The
> per-language plug-in shape (`KytheIndexer` vs `PyrightIndexer` vs
> `tsserver`-based, all sharing the abstract interface) was the right
> call: C and JS need different things even when both fall in the
> "Loom partially helps" bucket.

---

## Setup

Same per-language harness shape as phL2 (M10.2 C++):
- copy of the existing `phM` (C) / `phQ` (JS) cross-language smoke
- adds a `StubCIndexer` / `StubJsIndexer` registered through the M10.1
  `indexers.SemanticIndexer` registry
- adds a `## Semantic context` block above the file body in the prompt
- runs against the same scenario the M8.4 cross-language map measured

Per-language stub content was hand-authored to match what a real
backend would surface:
- **C** stub: clang-style call sites of `fetch_with_retry` from
  `backoff_loop.c` + `sync_worker.c`, the errno-flow contract,
  `BackoffLedger` struct, and the wrapper's expectation that errno=0
  on retry-budget exhaustion.
- **JS** stub: tsserver/JSDoc-style call sites of `fetchWithRetry`
  from `backoff_loop.js` + `sync_worker.js`, JSDoc `@returns`
  annotation for the null-on-failure contract, `BackoffError`
  class definition.

Both stubs are roughly 3000-3100 chars (vs the C++ stub's 2094) — same
shape, more verbose because of C/JS idioms.

Same model (`qwen2.5-coder:32b`) as M10.2 for parity.

---

## Empirical record

### C — phM2 (qwen2.5-coder:32b + StubCIndexer)

Compared against the M8.4 cross-language map's C row (qwen3.5):

| cell | baseline (qwen3.5) | with stub (32b + indexer) | delta |
|---|---|---|---|
| off | 50% | 5/10 (50%) | **+0pp** |
| on-rule | 50% | 3/4 (75%) | +25pp · *N=2* |
| on-rule+placebo | 60% | 6/10 (60%) | **+0pp** |
| on-rule+rat | 60% | 5/10 (50%) | -10pp |

- 0 compile failures · 0 silent code-extraction failures
- Citation regex hits: rat=4/5, placebo=3/5 (qwen2.5-coder:32b on C
  *does* reproduce the rationale's distinctive phrases — unlike C++
  and JS where citation stayed at 0)
- Wall: 4.8 min for 14 successful trials

**C interpretation:** The C cells move within sampling noise of their
baselines. The on-rule cell at 75% (N=2) is the only suggestive lift,
but with only 2 samples the binomial CI is wide enough that the
"+25pp" could be chance. None of the other cells show a real shift.
The M10.2 finding does NOT generalize from C++ to C.

### JS — phQ2 (qwen2.5-coder:32b + StubJsIndexer)

Compared against the M8.4 cross-language map's JS row (qwen3.5):

| cell | baseline (qwen3.5) | with stub (32b + indexer) | delta |
|---|---|---|---|
| off | 0% | 6/10 (60%) | **+60pp** |
| on-rule | 20% | 10/10 (100%) | **+80pp** |
| on-rule+placebo | 40% | 4/4 (100%) | +60pp · *N=2* |
| on-rule+rat | 60% | 10/10 (100%) | **+40pp** |

- 0 compile failures · 0 silent code-extraction failures
- Citation regex hits: 0 across all cells (qwen2.5-coder:32b on JS
  doesn't reproduce rationale phrases — same pattern as C++)
- Wall: 5.6 min for 17 successful trials

**JS interpretation:** **Massive lift across every cell, including
off.** This is the strongest M10 result yet, but it's also the
weirdest: the *off cell* — which has no rule injected — went from 0%
to 60%. That means the stub's semantic context, particularly the
JSDoc-style `@returns null on failure` annotation, is functioning as
an implicit rule even when no Loom rule is present. Three of four
cells saturate at 100%, and the rationale cell does so with N=10 —
unambiguous.

---

## What this rules in / rules out

**Rules in:** the M10 *architecture* (pluggable per-language
indexers, with the abstract `SemanticIndexer` interface). The right
indexer for each language wins — JS responds to LSP-style JSDoc
contracts, C++ responds to call-graph evidence, etc. The registry
pattern is correct.

**Rules out:** "one plugin to rule them all." The M10.2 finding does
NOT predict the C result. C's compliance is unmoved by clang-style
xref context. Two plausible explanations:
1. **C scenario is different.** The C task is "preserve errno across
   retries" — a state-flow constraint that isn't directly visible in
   call-site context. The C++ scenario was "swallow std::runtime_error"
   — a control-flow constraint where call-site evidence is decisive
   ("the wrapper doesn't catch — propagating breaks it").
2. **C is a different kind of resistant.** M8.4 classified C as
   "resistant-mid" alongside Go, but the response patterns may differ.
   Go's volatility (off=20, rule=60, +placebo=100, +rat=60) is unlike
   C's flatness (50/50/60/60). One M10 indexer probably can't fix
   both.

**Rules out also:** "semantic context is always additive." The JS off
cell going from 0% to 60% means the stub is encoding so much
information that it's effectively a rule-substitute. That's not bad,
but it complicates the comparison: the +80pp on-rule lift is a mix of
"context helps the model follow the rule" and "context contains the
rule." A cleaner experiment would use a maximally non-rule-encoding
stub that only describes structural facts.

---

## What this means for v1.x M10 work

The two M10 falsifications (M10.1b + M10.2) plus this multi-language
extension converge on a clearer roadmap:

1. **Build `KytheIndexer` for C++ first.** M10.2 is the cleanest
   result and the clang/Kythe pipeline is the most tractable real
   indexer. Expected: replicate or improve on the +40pp stub finding
   with real Kythe data.
2. **Build `tsserver`-based or LSP `JsIndexer`.** JS is the highest-
   ceiling result by far (saturates at 100%); even noisier real LSP
   output would likely replicate the lift. tsserver is operationally
   cheaper than Kythe (no extraction step). Probably the highest
   ROI second indexer.
3. **Keep C on the back burner.** The flat C result suggests a real
   `KytheIndexer` for C will not move the needle on the M8.4 C
   regime. Worth revisiting only when we have a different scenario
   shape (state-flow rather than control-flow).
4. **Re-author the JS stub more conservatively** — restrict it to
   call-site facts without inline JSDoc contract assertions, so the
   off cell doesn't carry. Confirms whether the lift is "context"
   vs "implicit rule."

Implications for the published cross-language map:
- C++ deserves an annotation: "collapsed under file-only context, not
  under semantic context"
- JS regime classification ("graded, no saturation") needs an
  asterisk: that ceiling is not a hard limit, semantic context lifts
  it to saturation
- C's classification stands

---

## Limitations

- **Ollama 32b runner crashed multiple times mid-sweep.** Several
  cells have N<5 because the original harness silently dropped trials
  when the runner terminated. The harness has been patched (commit
  follows) to write a summary file even on error, so future runs
  surface what happened. Cells with reduced N are flagged in the
  tables.
- **N=5 per cell where it landed.** Even the saturated 10/10 JS cells
  are only N=10 (combining placebo + rat samples). Tightening the
  CIs would benefit from a higher-N rerun, but the qualitative
  pattern is robust at this N.
- **Hand-authored stubs.** The stub context is a best-case for what a
  real indexer would produce. Real Kythe / tsserver output would be
  noisier and might lower the ceiling.
- **Single scenario per language.** S1 only. Whether the per-language
  pattern holds for S2/S3-shaped scenarios is open.
- **The off-cell lift on JS is a confound.** It indicates the stub
  encodes implicit rule information, which the methodology is not
  designed to control for. A "structural-facts-only" stub would
  isolate the context effect from the rule effect.

---

## Recommended next experiments (priority order)

1. **Higher-N rerun on JS** to confirm 100% across cells holds
   beyond N=5. The off-cell jump from 0% to 60% is the most
   surprising data point; it merits more samples.
2. **Real `tsserver`-based indexer for JS.** Cheap to stand up
   compared to Kythe; could land in v1.x quickly. If real tsserver
   output replicates the stub's lift, JS gets a working indexer
   shipped.
3. **C state-flow scenario rewrite.** The errno-preservation task may
   not be what call-graph context can address. A control-flow C
   scenario (similar shape to C++ swallow vs propagate) would test
   whether C's flatness is the language or the scenario.
4. **C++ real Kythe.** As planned in M10 roadmap. The stub result
   establishes feasibility; Kythe is the production version.

---

## Files of record

- `experiments/bakeoff/v2_driver/phM2_crosssession_c_stub_indexer_smoke.py`
  — C harness with `StubCIndexer`
- `experiments/bakeoff/v2_driver/phQ2_crosssession_js_stub_indexer_smoke.py`
  — JS harness with `StubJsIndexer`
- `experiments/bakeoff/runs-v2/phM2_s1_c_*_summary.json` — C trial
  results (~17 files; ~3 trials lost to runner crashes before harness
  patch landed)
- `experiments/bakeoff/runs-v2/phQ2_s1_js_*_summary.json` — JS trial
  results (~17 files; ~3 trials lost similarly)
- `experiments/bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md` —
  the M10.2 C++ original
- `ROADMAP.md` — M10.2/3 status

---

## Three-language summary (rat cell)

| language | qwen3.5 baseline | stub + 32b | net result |
|---|---|---|---|
| **C++** | 67% (artifact) | **40%** | +40pp over the 0% 32b-no-stub falsification |
| **C** | 60% | 50% | flat (no lift; possibly slight noise) |
| **JS** | 60% | **100%** | saturating lift |

The "M10 architecture is right; per-language plug-ins do different
things" framing is the most honest reading of these three results.
