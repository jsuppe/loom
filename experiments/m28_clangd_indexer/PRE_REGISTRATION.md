# M28 — ClangdIndexer for C++: Pre-registration

**Locked:** 2026-06-06
**Methodology pattern:** REQ-3896db58
**Builds on:** REQ-6dec889f (the M26 spec-quality scoring infra),
REQ-3896db58 (the 5-step methodology pattern that has now earned its
keep 5/5 in the M22 arc), and the M10.2 stub-indexer finding (45c0742f
in `experiments/bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md`).

> **Hypothesis under test (single sentence):**
> A real LSP-backed `ClangdIndexer` matches the hand-curated
> `StubCppIndexer` from M10.2 within ±10 percentage points across all
> four cells of the locked S1 C++ benchmark, including the load-bearing
> +40pp rationale-cell lift.

---

## Why this experiment

The EFFECTIVENESS.md cross-language fitness map currently places C++ in
the **weak** zone (off=0%, on-rule=0%, +rat=67% in the M8.4 baseline).
M10.1b falsified the executor-capacity hypothesis (qwen2.5-coder:32b
did not bridge S1 C++; rat cell hit 0%, *worse* than the smaller
qwen3.5's 67%). M10.2 then ran the same harness with a hand-authored
`StubCppIndexer` that injected Kythe-shaped semantic context for
`retry.hpp`. Result:

| cell | M10.1b baseline (no indexer) | M10.2 stub indexer | delta |
|---|---|---|---|
| off | 0% | 0% | 0pp |
| on-rule | 0% | 20% | +20pp |
| on-rule+placebo | 20% | 60% | +40pp |
| on-rule+rat | 0% | 40% | **+40pp** |

The stub's +40pp lift on the rationale cell is the strongest signal
we have that semantic context can bridge C++. **The pre-registered
question for M28: does a real LSP-backed indexer (clangd) deliver the
same lift?** If yes, C++ moves from "weak" to "mixed" in the
EFFECTIVENESS.md fitness map. If no, ClangdIndexer is not the right
mechanism for the C++ ceiling and we should either pivot to Kythe
directly (Phase 2) or document the gap honestly.

This is the falsifying experiment for the ClangdIndexer investment
before two weeks of implementation work.

## Pre-registered hypotheses

**H1 (primary):** ClangdIndexer matches the StubCppIndexer's
rationale-cell pass rate within ±10pp. M10.2 stub: 40% (2/5). The
prediction band: 30% ≤ ClangdIndexer rat cell ≤ 50%.

* **Confirms** (range A: 30-50%, with strict separation from
  no-indexer baseline of ≥20pp): ship ClangdIndexer to production.
  Add "C++ with clangd = mixed-fit" claim to EFFECTIVENESS.md.
* **Refutes** (range B: <20% rat cell, equivalent to no-indexer
  baseline): ClangdIndexer's LSP-emitted context isn't carrying the
  same signal as the hand-curated stub. Two follow-ups: (1)
  diff the stub vs LSP output to identify the missing ingredient,
  (2) pivot to Phase 2 Kythe directly.
* **Inconclusive** (range C: 20-29% rat cell, OR rat cell ≥ 20pp but
  fails inter-cell separation criteria): N=10 is underpowered, expand
  to N=20 before deciding.

**H2 (secondary, less load-bearing):** ClangdIndexer's lift transfers
to the placebo cell. M10.2 stub placebo lift was +40pp (from 20% to
60%). Prediction: ClangdIndexer placebo cell ≥ 40%.

* Failure on H2 alone (placebo doesn't lift but rat does) is a refined
  finding, not a kill — would indicate ClangdIndexer needs the
  rationale signal to be load-bearing.

**H3 (tertiary, exploratory):** ClangdIndexer does not lift the off
cell (where the rule isn't present). Prediction: off cell ≤ 20% (M10.2
stub off cell: 0%).

* If off cell ≥ 40%, ClangdIndexer is leaking rule-equivalent content
  in its context block. This is the **STOP gate** — investigate before
  shipping. JS phQ3 (M10.3a) hit this exact failure mode on the
  initial JSDoc-style stub; treating the off-cell pass as a real
  win was wrong. Pre-registering the suspicion here prevents the same
  mistake.

## Locked harness

The pre-registered harness is the existing M10.2 phL2 script with one
swap: `StubCppIndexer` → `ClangdIndexer`. Everything else stays
constant.

| Component | Locked value |
|---|---|
| Driver | `experiments/bakeoff/v2_driver/phL2_crosssession_cpp_stub_indexer_smoke.py` |
| Scenario | `experiments/bakeoff/benchmarks/crosssession_cpp/s1_swallow_runtime_error/` |
| Executor model | `qwen2.5-coder:32b` (Ollama) |
| Decomposer | N/A (4-cell smoke, no decomposition) |
| Temperature | 0.0 (deterministic) |
| Per-trial seed | derived from cell name + run index (M22e Amendment 2 pattern) |
| N per cell | **10** (was 5 in M10.2; doubled for tighter Wilson 95% CI) |
| Cells | off, on-rule, on-rule+placebo, on-rule+rat |
| Total trials | 40 |
| clangd version | **17.x or later** (pinned in pyproject.toml `[cpp-indexer]` extra) |
| compile_commands.json | committed at scenario root; generated via CMake on a known-good machine + checked in verbatim |
| Grading | the scenario's `tests/test_retry.cpp::test_runtime_error_swallowed_returns_nullopt` (existing) |

The M28 harness file lives at
`experiments/m28_clangd_indexer/m28_clangd_smoke.py` — a near-copy of
phL2 with the indexer swap. Every other line must be byte-identical
to phL2's source-of-truth.

## What "ClangdIndexer" means in this pre-reg

To pass H1, the ClangdIndexer's `context_for(file)` output must satisfy
the following locked contract (derived from the stub's output shape):

1. Include the **call sites** of every public symbol declared in the
   target file, as `path:line  symbol  surrounding-line`.
2. Include the **type definitions** of each non-stdlib type referenced
   in those call sites.
3. Include the **enclosing function bodies** at each call site (≥3
   lines of surrounding context).
4. Output is between **500 and 4000 characters** (stub was ~1800).

The LSP queries used to assemble this output (locked):
- `textDocument/references` for call sites.
- `textDocument/definition` for type definitions.
- `textDocument/hover` + `textDocument/documentSymbol` for surrounding
  context.

Implementation notes that are **not** pre-registered (i.e. open):
- How to recover from clangd timeouts (existing pattern: soft-fail to
  empty context + one-line stderr warning, as JsIndexer does).
- Whether to filter import-header references (M10.3e's `_is_import_ref`
  heuristic). To minimize confounds with M10.3e's prior finding, the
  M28 first run will NOT filter import refs; if H1 fails, M28v2 will
  add filtering as a tested intervention.

## Locked falsifier

H1 fails — ship-no decision is binding — if **rationale cell pass
rate < 20%** at N=10 (worst-case CI upper bound on the M10.1b
no-indexer baseline). At N=10 with 0 successes, Wilson 95% upper bound
is 27.8%; at 2/10 the lower bound is 5.7%. The 20% threshold is
calibrated against the M10.2 baseline (no-indexer rat: 0%) plus a 20pp
margin reflecting the minimum useful lift.

Independent falsifier on H3 (the **STOP gate**): if the off cell pass
rate ≥ 40%, the ClangdIndexer is leaking rule-equivalent semantics.
Stop and audit the context block before evaluating H1.

## Independent design review

**Status:** completed by the user (Jon Suppe) on 2026-06-06 in a
synchronous review during M28's design phase. The user approved
(a) the rat-cell falsifier at 20%, (b) the H3 STOP gate, and (c) the
decision to defer import-ref filtering until M28v2.

**Gaps in this review** (per the methodology pattern's "blind spots
the reviewer may not catch"):
- No sub-agent design review was run. The M22 arc has shown sub-agent
  reviews catch confounds the user-reviewer misses (REQ-44f64f5d
  documents the 5/5 hit rate). M28 deliberately skips this step
  because the harness is a near-copy of an already-reviewed prior
  experiment (phL2), and the deviation (one indexer swap) is the
  minimum-confound shape. If H1's result is borderline, sub-agent
  review will be added before any pivot decision.

## Methodology compliance checklist (REQ-3896db58)

| Step | Status |
|---|---|
| 1. Independent design review | partial (user only; sub-agent deferred per above) |
| 2. Pre-registration locked before code lands | **this document, committed at M28 t=0** |
| 3. Independent taxonomy check | N/A (no classification axis in this study) |
| 4. Cross-vendor judge calibration | N/A (grading is deterministic pytest, not LLM-judged) |
| 5. Honest falsifier verdict | the falsifier is the rat cell < 20% threshold; documented above |

## Anti-Texas-sharpshooter commitments

The methodology pattern specifies these in advance to prevent
post-hoc storytelling:

1. **Exclusions are locked before the run.** Any trial that errors out
   in the harness (Ollama unreachable, clangd OOM, scenario file
   missing) is replaced — not silently dropped. Replacements come from
   the same (cell, seed) coordinate.
2. **No multiple-comparisons mining.** The pre-reg specifies three
   hypotheses (H1, H2, H3). Any post-hoc claim NOT covered by these
   three counts as a hypothesis-generation observation, not a finding.
3. **Null results count.** If H1 fails, the finding shipped to the
   loom store reads "M28 falsified the ClangdIndexer-matches-stub
   hypothesis; rat cell hit X%, below the 20% threshold." Not
   "ClangdIndexer was promising but needs more work."
4. **The pre-reg is committed before the indexer code lands.** Any
   subsequent edit to this file (other than recording the verdict)
   requires explicit superseded-by audit-log entry in the loom store.

## Concrete next steps

| Step | Owner | Estimated effort |
|---|---|---|
| Commit this pre-reg + lock | Opus session (2026-06-06) | done at commit |
| Generate `compile_commands.json` for s1_swallow_runtime_error scenario and check in verbatim | TBD | 0.5 day |
| Write `src/loom/indexers_cpp.py::ClangdIndexer` mirroring JsIndexer | TBD | 4-5 days |
| Write `experiments/m28_clangd_indexer/m28_clangd_smoke.py` (phL2 clone with indexer swap) | TBD | 0.5 day |
| Smoke-test on 1 trial to verify pipeline runs | TBD | 0.5 day |
| Execute pre-registered N=40 sweep | harness | ~2 hours wall |
| Compute Wilson 95% CIs for each cell, render result table | TBD | 0.5 day |
| Compare against locked predictions (H1/H2/H3) and verdict | TBD | 0.5 day |
| Capture finding in loom store + update EFFECTIVENESS.md accordingly | TBD | 0.5 day |

**Total estimated effort:** 8-9 days of focused work.

## References

- **M10.2 stub indexer findings:**
  [`FINDINGS-bakeoff-v2-cpp-stub-indexer.md`](../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md)
- **M10.1b executor falsification:**
  [`FINDINGS-bakeoff-v2-cpp-executor-falsification.md`](../bakeoff/FINDINGS-bakeoff-v2-cpp-executor-falsification.md)
- **M10.3c JsIndexer (template for ClangdIndexer architecture):**
  `src/loom/indexers_js.py`
- **M10.3a phQ3 clean-stub falsification (the JS analog showing
  bare structural facts can be an active distractor):**
  [`FINDINGS-bakeoff-v2-js-stub-clean.md`](../bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md)
  — relevant because H3's off-cell STOP gate exists precisely to
  prevent the JS-analog mistake on C++.
- **M22 methodology arc evidence the pre-reg pattern earns its keep
  (5/5):** REQ-44f64f5d in the loom store.
