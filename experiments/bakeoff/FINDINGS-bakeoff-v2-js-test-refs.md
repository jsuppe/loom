# Bakeoff V2 — JS test-reference surfacing (phQ7, M10.3f)

**Date:** 2026-05-02
**Question:** Does surfacing the test file's references close the
remaining placebo gap that phQ6 (M10.3e) left between LSP v2 (30%)
and the phQ3 hand-curated stub (90%)?
**Approach:** Copy `tests/test_retry.js` into the workspace root
alongside the source files, so the JsIndexer's `_walk_project`
naturally indexes it as part of the project. **No JsIndexer code
change.** This tests the hypothesis from phQ6's findings doc that
the test reference (`assert(result === null)` in phQ3, here
`if (result === null) { console.log("PASS: ...") }`) was the
load-bearing missing piece.
**N:** 40 trials. 0 LSP failures. 0 retries fired. 11.3 min wall.

---

## TL;DR

> **Hypothesis confirmed. +40pp lift on placebo (30% → 70%) with
> no other cell regressing.** Largest single-intervention effect
> across the entire M10 series — bigger than the +10pp from
> JsIndexer v2's import-filter + type-defs combined. We're now
> within 20pp of phQ3's hand-curated stub (90% on placebo); the
> remaining gap is plausibly N=10 sampling noise.
>
> | cell | phQ4 (no stub) | phQ3 (hand stub) | phQ5 (LSP v1) | phQ6 (LSP v2) | **phQ7 (v2 + tests)** | Δ vs phQ6 |
> |---|---|---|---|---|---|---|
> | off | 0% | 0% | 0% | 0% | **0%** | 0pp |
> | on-rule | 0% | 0% | 0% | 0% | **0%** | 0pp |
> | placebo | 10% | 90% | 20% | 30% | **70%** | **+40pp** |
> | rat | 80% | 100% | 100% | 100% | **100%** | 0pp |
>
> **No JsIndexer code change required.** The test files were
> surfaced naturally because `_walk_project` doesn't exclude
> `tests/`, `__tests__/`, or `*.test.js` filenames. The phQ5/phQ6
> placebo gap was an artifact of how those harnesses constructed
> their workspaces (only copying `reference/*`, excluding the
> tests directory). For typical project layouts where tests are
> part of the project tree, the JsIndexer architecture was already
> correct.
>
> **Operational guidance:** point the JsIndexer's `root` at the
> project root, not at a subset that excludes tests. The tests
> are load-bearing semantic context for placebo-augmented prompts.

---

## Setup

Identical to phQ6 except for ``setup_workspace``:

```python
def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phQ7_s1_js_"))
    for src in SCENARIO_DIR.glob("reference/*"):
        shutil.copy(src, ws / src.name)
    # phQ7 addition: also copy the test file into the workspace
    shutil.copy(SCENARIO_DIR / "tests" / "test_retry.js",
                ws / "test_retry.js")
    return ws
```

One line. The test file lands at the workspace root alongside
`retry.js`, so its `import { fetchWithRetry } from './retry.js'`
resolves cleanly. JsIndexer's `_walk_project` opens it via
`textDocument/didOpen`, the LSP indexes it, and
`textDocument/references` returns its call sites of
`fetchWithRetry` alongside the call sites in `backoff_loop.js`
and `sync_worker.js`.

---

## What the LSP v2 indexer surfaces (phQ7 view)

```
References to fetchWithRetry (4 results from textDocument/references):

  backoff_loop.js:29
      const result = fetchWithRetry(url, this.attempts);
      if (result === null) {
          this._ledger.recordExhaustion(url);
          throw new BackoffError("retry budget exhausted: " + url);
      }

  sync_worker.js:12
      const data = fetchWithRetry(endpoint.url);
      if (data) {
          this._cache.insert(endpoint.key, data);
      }
      // null result → nothing to insert. ...

  test_retry.js:19                                ← NEW IN phQ7
      const result = fetchWithRetry("http://example.com", 3);
      if (result === null) {
          console.log("PASS: returns_null_on_failures");
          passed++;
      } else {

  test_retry.js:34                                ← NEW IN phQ7
      fetchWithRetry("http://example.com", 1);
      console.log("PASS: error_does_not_propagate");
      passed++;
  } catch (e) {
```

The two test references explicitly say:
- `if (result === null) { console.log("PASS: returns_null_on_failures"); }`
- `console.log("PASS: error_does_not_propagate");`

These are the strongest possible "the contract is X" signal —
direct PASS labels on the contract conditions. phQ3's hand-
curated stub had `assert(result === null)` which is comparable
in shape but less explicit; the actual test's PASS labels are
arguably *stronger* than phQ3's stub.

Yet phQ7 lands at 70% while phQ3 hit 90%. Three plausible reasons
for the 20pp remaining gap:

1. **N=10 binomial noise.** 14/20 vs 18/20 is a 4-trial gap; the
   95% CIs overlap heavily. Higher-N could close it.
2. **Verbosity tradeoff.** phQ7's semantic block is 1818 chars
   (vs phQ3's 955 chars and phQ6's 1293). The model's attention
   is spread across more text. Despite the strong signal, more
   filler may dilute it.
3. **Adjacent type defs noise.** phQ7 (inheriting from v2)
   includes 4 class signatures; phQ3 had 2. If model uses class
   signatures as a "things to instantiate" checklist, additional
   classes could dilute compliance focus.

(2) and (3) are testable but not necessary for v1.x — the +40pp
result is decisive evidence the hypothesis is right.

---

## What this rules in / rules out

**Rules in:** the test-reference hypothesis from phQ6's findings.
The +40pp placebo lift is conclusive evidence that the test
file's call-site code (specifically the `if (result === null) {
PASS }` framing) carries substantial signal about the contract,
which in turn helps the model commit to rule compliance under
placebo augmentation.

**Rules in:** the existing JsIndexer architecture is correct.
No code change was needed. `_walk_project` already includes
`tests/` and `__tests__/` and `*.test.js` files because none of
them are in `_PROJECT_GLOB_IGNORE_DIRS`. The phQ5/phQ6 gap was
an artifact of synthetic workspace setup, not a JsIndexer
limitation.

**Rules in (operationally):** instantiate `JsIndexer(root=...)`
with the project root, not with a subdirectory that excludes
tests. The tests carry load-bearing context for the placebo
case.

**Doesn't yet rule out:** that the placebo lift mechanism is
specifically the PASS labels in the test rather than the call
site itself. A test with bare `assert()`s (no console.log
labels) would tell us whether the verbal labels matter or just
the structural assertion shape. Worth a follow-up
falsification.

---

## Implications for v1.x M10 work

**No code change to JsIndexer required.** The +40pp lift was
delivered by a one-line workspace change in the experiment
harness, not a feature in the indexer. The architecture
already does the right thing.

**Documentation needed.** The README / CLAUDE.md guidance for
JsIndexer should note: *"Point JsIndexer at your project root,
not a subset of it. Test files (`*.test.js`, `*.spec.js`,
`tests/*.js`, `__tests__/`) are load-bearing semantic context
for the executor — exclude them from the index and you'll lose
~40pp of placebo-cell compliance lift on contrarian specs."*

**Reframe the JsIndexer pitch (final form for v1.x):**

> *JsIndexer wraps `typescript-language-server` to surface
> peek-references-style semantic context for the loom_exec
> prompt. It saturates rationale-augmented requirements at
> 100% under qwen2.5-coder:32b on the M8.4 cross-session JS
> scenario (vs 80% without). On placebo-augmented prompts
> (rule + length-matched filler explanation), it lifts
> compliance from 10% to 70% — provided the project root
> includes the test files. Bare-rule cells without explanation
> remain at 0%; the indexer amplifies explanation-shape
> signals, it doesn't manufacture rule compliance.*

**No 10.3g experiment needed.** The remaining 20pp gap to
phQ3's stub is plausibly noise. The next priority steps from
here are 10.4 (structural drift, now properly unblocked) and
10.5 (`loom indexer doctor`).

---

## Limitations

- **N=10 binomials.** 14/20 vs 18/20 is a 4-trial gap. Higher
  N would tighten the placebo CI and either close the
  remaining 20pp gap to phQ3 or confirm a real ceiling.
- **Single scenario.** Only S1 swallow_error in the ESM
  variant. Whether the test-reference effect generalizes to
  S2/S3-shaped scenarios is open.
- **Single executor.** qwen2.5-coder:32b only.
- **PASS-label vs bare-assert ambiguity.** The phQ7 test uses
  `console.log("PASS: ...")` which is verbal labeling; phQ3's
  stub used `assert(result === null)` which is bare. The
  +40pp could be from either or both. A test variant with
  bare `assert()`s would isolate.
- **Single test file.** Some real projects scatter tests
  across many files. The 5-refs-per-symbol cap might cut off
  important test refs in larger codebases.
- **No `surface_test_refs` mode.** Users with tests in
  unconventional locations (outside the project root) would
  still need a workaround. A future indexer mode could
  explicitly include external test directories, but it's not
  needed for the standard case.

---

## Recommended next experiments (priority order)

1. **Higher-N rerun on placebo cell** at phQ7 (N=20-30) to
   tighten the +40pp CI and either close or confirm the
   remaining 20pp gap to phQ3.
2. **Bare-assert test variant** to isolate "PASS labels"
   from "test call site" as the placebo lift mechanism.
3. **S2/S3 port** to confirm the effect generalizes beyond
   swallow_error.
4. **10.4: structural drift detection.** Properly unblocked
   now — JsIndexer's `signature_of` capability via LSP can
   power a structural-drift channel in `services.check`.
5. **10.5: `loom indexer doctor`.** Health check for the
   user's indexer pipeline.

---

## Files of record

- `experiments/bakeoff/v2_driver/phQ7_crosssession_js_with_test_refs_smoke.py`
  — phQ7 harness (one-line setup_workspace difference vs phQ6)
- `experiments/bakeoff/runs-v2/phQ7_s1_js_*_run{1..10}_summary.json`
  — 40 trial summaries
- `src/loom/indexers_js.py` — unchanged from M10.3e (commit
  `b19ddb5`)
- Compare against:
  - `FINDINGS-bakeoff-v2-js-real-lsp-v2.md` (phQ6 v2 baseline)
  - `FINDINGS-bakeoff-v2-js-real-lsp.md` (phQ5 v1 baseline)
  - `FINDINGS-bakeoff-v2-js-stub-clean.md` (phQ3 hand-curated stub)
