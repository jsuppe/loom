# M28 Findings — ClangdIndexer Phase 1 on C++ S1

**Date:** 2026-06-06
**Verdict:** **H1 REFUTED.** ClangdIndexer does not replicate the
M10.2 hand-curated stub's lift on the locked S1 C++ benchmark.
**H3 STOP gate passed** (off cell 0%); the refutation is interpretable.

Captured as **REQ-2007b144** in the loom store.

---

## Result table

40 trials, qwen2.5-coder:32b, ClangdIndexer with `--background-index`
enabled, `LOOM_CLANGD_WARM_SLEEP_S=1.5` (default) per the M28.2
implementation.

| cell | M10.2 stub (N=5) | **M28 clangd (N=10)** | Wilson 95% CI | delta |
|---|---|---|---|---|
| off | 0% | 0% (0/10) | [0%, 28%] | 0 |
| on-rule | 20% | 0% (0/10) | [0%, 28%] | **-20pp** |
| on-rule+placebo | 60% | 20% (2/10) | [6%, 51%] | **-40pp** |
| on-rule+rat | 40% | **0% (0/10)** | [0%, 28%] | **-40pp** |

Mean tokens per trial: input 959-1176 (off → rat), output ~260
across cells, semantic-context block ~1300-2400 chars.

## Pre-registered verdicts

| hypothesis | prediction | result | verdict |
|---|---|---|---|
| H1 (primary) | rat cell 30-50% | 0% (CI 0-28%) | **REFUTED** (below 20% falsifier) |
| H2 (secondary) | placebo ≥ 40% | 20% | refuted |
| H3 (STOP gate) | off ≤ 20% | 0% | **passes** — no rule leak |

## What this tells us

The M10.2 stub's +40pp rationale-cell lift was **not** carried by
Kythe-shaped structural facts. It was carried by **embedded contract
prose** — sentences like:

> "IMPORTANT: this call site does NOT have a try/catch around
> fetchWithRetry. It assumes fetchWithRetry returns std::nullopt on
> failure and never throws. If fetchWithRetry propagates
> std::runtime_error, BackoffLoop::run will let it bubble up
> uncaught — a contract violation that production hit on 2024-09-12."

The M10.2 stub block contains roughly 8 sentences of this kind of
authored prose. A real LSP-backed indexer (clangd) returns refs +
surrounding lines verbatim — no contract prose, no production-incident
narrative, no "IMPORTANT" callouts. The structural facts are *true*
but they're not what was carrying the lift.

This is the **same failure mode** as M10.3a's phQ3 finding (captured
as REQ-7ed1bdd2): on JavaScript, a hand-curated JSDoc-style stub
showed strong lift, but when re-implemented as a "clean" LSP-backed
indexer, the off-cell jumped because the JSDoc was leaking rule
semantics, and the structural-facts-only version dropped back to
baseline.

The M28 result extends that pattern: **for both JS and C++, the
"semantic context" hypothesis was confounded by embedded prose in the
stub.** Real LSP refs do not replicate the effect.

## Methodology pattern earns its keep, 6/6

| arc | what the pattern caught |
|---|---|
| M22a.0 | 2 fatal design flaws pre-launch |
| M22a re-grade | F2 refined (binary grader overclaimed) |
| M22b | structural confounds pre-launch (factual error + 2 leaks) |
| M22e | pre-reg locked workload-arm pivot before sweep |
| M19v2 | wrong-prediction surfaced honestly even with favorable result |
| **M28** | **clean refutation of H1 under locked pre-reg; without the 20% falsifier, "rat cell 0%" would have been hand-waved as "needs more iteration"** |

The M28 H3 STOP gate is what makes the refutation interpretable. The
off cell stayed at 0% — so we know the 0% rat cell is a real
"intervention does not work" signal, not "intervention is leaking
rule content into off and the rat is masked." Pre-registration in
M28 was the difference between a clean falsification and a muddled
narrative.

## What changes downstream

* **EFFECTIVENESS.md** does NOT gain a "C++ with ClangdIndexer =
  mixed fit" claim. C++ stays in the **weak** zone. The new entry in
  the honest-null section is: "ClangdIndexer Phase 1 (M28) was
  pre-registered against M10.2's stub baseline and falsified —
  hand-authored contract prose, not structural facts, carried the
  M10.2 lift."

* **M29 (style constraint)** simplifies to Phase A only. M29 Phase B
  (combined style + semantic) was conditional on M28 H1 confirming;
  it's now dropped per the pre-reg. M29 Phase A is independent of
  M28's outcome and still informative.

* **M28 follow-ups (queued, not committed):**
    1. **stub-vs-LSP diff study** — quantify the difference between
       M10.2's stub block and ClangdIndexer's output for retry.hpp.
       Identifies what specifically the stub had that the LSP doesn't.
    2. **M28v2 — LLM-summarized contract prose** — augment ClangdIndexer
       with an Anthropic Haiku pass that reads the LSP refs and writes
       contract-style prose around them. Tests whether the prose IS
       the carrier (predicts: yes, +40pp recovery).
    3. **Kythe Phase 2** — the original M10 Phase 2 plan. Different
       project-wide query semantics; would test whether cross-TU
       semantic facts are the lever. Substantially more infrastructure
       cost.

* **Token-efficiency tracking** (M30, building now) — M28's negative
  result is the cleanest possible data point for this tooling. The
  indexer added ~150-200 input tokens per trial and produced zero
  quality lift. A token-efficiency rollup makes this visible
  cross-experiment.

## Artifacts (everything reproducible)

| artifact | path |
|---|---|
| Pre-registration | [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) |
| Locked harness | [`m28_clangd_smoke.py`](m28_clangd_smoke.py) |
| Indexer | [`../../src/loom/indexers_cpp.py`](../../src/loom/indexers_cpp.py) |
| Trial summaries | [`../bakeoff/runs-m28/`](../bakeoff/runs-m28/) (40 JSONs) |
| Manual verification | [`verify_indexer.py`](verify_indexer.py) |
| Captured finding | REQ-2007b144 (loom store) |

To reproduce, on any machine with clangd 17+ and qwen2.5-coder:32b in
Ollama:

```bash
PATH="<llvm-bin>:<g++-bin>:$PATH" \
  python3 experiments/m28_clangd_indexer/m28_clangd_smoke.py --sweep --n 10
```

Output lands in `experiments/bakeoff/runs-m28/`.
