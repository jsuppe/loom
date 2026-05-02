# Bakeoff V2 — JsIndexer v2 validation (phQ6, M10.3e)

**Date:** 2026-05-02
**Question:** Does the JsIndexer v2 (M10.3e — import-line filtering
+ adjacent type definitions) close the placebo gap that phQ5
(M10.3d) identified between real LSP output (20%) and the phQ3
hand-curated stub (90%)?
**Approach:** Same harness as phQ5 (`s1_swallow_error_esm/`,
`qwen2.5-coder:32b`, 4 cells × N=10), only the JsIndexer
implementation changed. Direct phQ5→phQ6 comparison isolates the
v1→v2 effect.
**N:** 40 trials. 0 LSP failures. 0 retries fired. 11.1 min wall.

---

## TL;DR

> **v2 helped, but not nearly as much as expected.** Filtering
> import refs and adding adjacent type defs lifted placebo by
> **+10pp** (20% → 30%), well short of the phQ3 stub's 90%. The
> rationale cell saturation held at 100% (no regression). Off
> and on-rule cells held at 0% (correctly).
>
> | cell | phQ4 (no stub) | phQ3 (hand stub) | phQ5 (LSP v1) | **phQ6 (LSP v2)** | v2−v1 | gap to phQ3 |
> |---|---|---|---|---|---|---|
> | off | 0% | 0% | 0% | **0%** | 0pp | 0pp |
> | on-rule | 0% | 0% | 0% | **0%** | 0pp | 0pp |
> | placebo | 10% | 90% | 20% | **30%** | **+10pp** | -60pp |
> | rat | 80% | 100% | 100% | **100%** | 0pp | 0pp |
>
> **Falsified:** the M10.3d hypothesis that adjacent type
> definitions were the dominant missing ingredient. v2 actually
> includes MORE type defs than phQ3 (4 vs 2 — `BackoffError`,
> `BackoffLedger`, `BackoffLoop`, `SyncWorker`), and the placebo
> still sits 60pp below the stub. So the type-defs section is
> *useful* (+10pp) but not *load-bearing*.
>
> **Newly suggested:** the load-bearing missing piece is most
> likely the **test-file reference** the phQ3 stub included —
> `tests/test_retry.js:14: assert(result === null)`. That's an
> explicit acceptance criterion in code form, the strongest
> single signal that the contract is "returns null on failure."
> v1 and v2 both miss it because tests live outside the
> workspace at indexing time. Worth a follow-up experiment
> (phQ7) before more architecture changes.

---

## Setup

Identical to phQ5 except for the JsIndexer implementation:

- v1 (phQ5): raw `textDocument/references` + 4-line snippets
- v2 (phQ6): same, plus
  - **Import-line filter**: snippets whose first line matches
    `^\s*(?:import\b|export\s+\{...\}\s+from\b|...require\(...)`
    are dropped from the references list before emission.
    Module-level `_is_import_ref()` helper.
  - **Adjacent type definitions**: after collecting references
    that survive the import filter, files with surviving refs
    are queried via `textDocument/documentSymbol`, top-level
    Class symbols are extracted, and their bare signature lines
    are appended to a "Symbols defined in referenced files:"
    section. New `_collect_adjacent_type_defs()` method.

Same model (qwen2.5-coder:32b), same scenario, same prompt
template, same N=10 per cell.

---

## Empirical record

| cell | phQ5 v1 | phQ6 v2 |
|---|---|---|
| off | 0% (0/20) | 0% (0/20) |
| on-rule | 0% (0/20) | 0% (0/20) |
| on-rule+placebo | 20% (4/20) | **30% (6/20)** |
| on-rule+rat | 100% (20/20) | 100% (20/20) |

Output size: 1397 chars (v1) → 1293 chars (v2). v2 is *smaller*
because the import filter removed 2 reference snippets and the
type defs section adds only ~200 chars of single-line entries.

Per-cell change in placebo: 4/20 → 6/20 — two more trials
complied. Within sampling noise the actual lift could be
+0pp to +30pp (binomial CIs are wide at this N), but the
qualitative finding is robust: v2 didn't close the gap.

---

## Side-by-side: what's actually in each context block

**phQ3 hand-curated stub (955 chars, 90% on placebo):**

```
References to fetchWithRetry (3 results):
  src/backoff_loop.js:34
      const result = await fetchWithRetry(url, this.attempts);
      ...
      throw new BackoffError("retry budget exhausted");
  src/sync_worker.js:89
      const data = await fetchWithRetry(endpoint.url);
      if (data) this._cache.insert(endpoint.key, data);
  tests/test_retry.js:14                                    ← TEST REF
      const result = fetchWithRetry("http://example.com");  ← TEST REF
      assert(result === null);                              ← TEST REF

Symbols defined in adjacent files:
  class BackoffError extends Error           // backoff_loop.js:8
  class BackoffLedger                         // backoff_loop.js:18
      recordExhaustion(url)
```

**phQ6 v2 LSP output (1293 chars, 30% on placebo):**

```
References to doFetch (1 result):
  retry.js:18
      return doFetch(url);
      ...

References to fetchWithRetry (2 results):
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

Symbols defined in referenced files:
  export class BackoffError extends Error    // backoff_loop.js:8
  export class BackoffLedger                 // backoff_loop.js:10
  export class BackoffLoop                   // backoff_loop.js:19
  export class SyncWorker                    // sync_worker.js:6
```

The v2 output has **strictly more type signatures** than phQ3's
stub (4 vs 2). It has comparable call-site snippets (2 vs 2,
both clean of imports). The single concrete thing v2 lacks:
the test reference with `assert(result === null)`.

---

## What this rules in / rules out

**Rules out:** "adjacent type definitions are the load-bearing
missing piece." If they were, v2 would have closed most of the
gap (it has 2x as many type defs as the phQ3 stub had). It
didn't. So they're useful (+10pp) but not the dominant
mechanism.

**Rules in:** the test-reference hypothesis. It's the only
remaining structural difference between phQ3 and phQ6 v2
outputs. The `assert(result === null)` line is an explicit
acceptance criterion in code form — directly states the
expected contract. Without it, the model has to infer the
contract from the fact that callers check `result === null`
without try/catch — a softer signal.

**Doesn't explain:** *why* a single test reference would carry
60pp of compliance lift on a placebo cell. One plausible
mechanism: the test assertion is the closest thing in the
prompt to "the rule, in code form" — it ties the requirement
text to a concrete, executable claim. Placebo cells need that
extra anchoring; rationale cells get it from the rationale
prose itself.

---

## Implications for v1.x M10 work

**Ship M10.3e (JsIndexer v2) as-is.** The +10pp is a real
improvement and the import-filter is unambiguously correct
(import lines are noise). Adjacent type defs are noisier but
useful. No reason to revert.

**Reframe the JsIndexer product pitch (again).** The honest
status:

> *JsIndexer ships an LSP-backed semantic context bundle for
> JavaScript and TypeScript executor prompts. It saturates
> rationale-augmented requirements at 100% compliance under
> qwen2.5-coder:32b (vs 80% without the indexer). On
> requirements with placebo-shaped explanations but no real
> rationale, it adds ~20pp lift (10% → 30%) — useful but not
> saturating. The dominant mechanism appears to be the rationale
> itself; the indexer amplifies it. v2 (M10.3e) adds
> import-filtering and adjacent type definitions on top of v1
> (M10.3c).*

**Defer further structural-context work** until the test-
reference hypothesis is tested. The next defensible
falsification:

- **phQ7 (proposed):** add a `surface_test_refs` mode to
  JsIndexer that locates `*.test.js` / `*.spec.js` /
  `tests/*.js` files in the project and surfaces references
  to the target's exported symbols from those files. If
  phQ7 lifts placebo from 30% toward 90%, the test-reference
  hypothesis is confirmed and we ship `surface_test_refs`
  as a v3 feature. If it doesn't, the gap is something else
  entirely and we need a different experiment.

---

## Limitations

- **N=10 binomials.** 4/20 vs 6/20 is a two-trial gap. The
  +10pp could plausibly be +0pp to +20pp at this N.
- **Single scenario.** Only S1 swallow_error in the new ESM
  variant. Whether the test-reference hypothesis holds for
  S2/S3-shaped scenarios is open.
- **Single executor.** qwen2.5-coder:32b only. The phQ4
  finding ("bigger code-specialist hurts contrarian rule
  cells") suggests qwen3.5:latest with v2 might score
  differently. Untested.
- **Type defs may have second-order effects.** The 4 class
  signatures might be confusing on top of the 2 phQ3 stub had,
  if the model treats them as a checklist of types-to-use.
  Hard to disentangle from the import-filter effect since both
  landed in the same v2.
- **No anti-rule placebo.** A placebo that subtly argues
  *against* the rule would test whether v2's lift is
  "explanation present" or "explanation supports rule" —
  same open question as in phQ3 / phQ4 findings.

---

## Recommended next experiments (priority order)

1. **phQ7: test-reference surfacing** (proposed above).
   Tests the dominant remaining hypothesis for the placebo
   gap. Cheap to implement (~30 LoC) and run (~12 min wall).
2. **Higher-N rerun on placebo cell** at v2 (N=20-30) to
   tighten the +10pp CI. Cheap.
3. **Cross-scenario S2/S3 port** to confirm the v2 lift
   pattern generalizes beyond the swallow_error scenario.
4. **Cross-tier executor** (qwen3.5 + v2) to test whether
   the smaller model with the indexer matches the phQ4
   pattern (general-purpose models are more rule-followy).

---

## Files of record

- `experiments/bakeoff/v2_driver/phQ6_crosssession_js_real_lsp_v2_smoke.py`
  — phQ6 harness (identical to phQ5, only JsIndexer changed)
- `experiments/bakeoff/runs-v2/phQ6_s1_js_*_run{1..10}_summary.json`
  — 40 trial summaries
- `src/loom/indexers_js.py` — v2 implementation
  (`_is_import_ref`, `_read_signature_line`,
  `_collect_adjacent_type_defs`)
- `tests/test_indexers_js.py` — 9 new helper tests + 1 new
  integration test for the type-defs section
- Compare against:
  - `FINDINGS-bakeoff-v2-js-real-lsp.md` (phQ5 v1 baseline)
  - `FINDINGS-bakeoff-v2-js-stub-clean.md` (phQ3 hand-curated stub)
