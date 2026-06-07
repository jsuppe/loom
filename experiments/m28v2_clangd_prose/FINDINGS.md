# M28v2 Findings — ClangdIndexer + LLM-summarized prose on C++ S1

**Date:** 2026-06-06
**Verdict:** **H1 REFUTED.** LLM-generated contract prose does NOT
recover the M10.2 hand-curated stub's lift. **H3 STOP gate passed**
(off 0% — no prose leak); the refutation is interpretable.

Captured as **REQ-b096c333** in the loom store.

---

## Result table

40 trials, qwen2.5-coder:32b as BOTH summarizer AND generator
(self-reinforcement confound accepted for v1 per the pre-reg).
Locked summarizer prompt with the source file + clangd structural
facts as input; no rule text, no task description.

| cell | M10.2 stub (N=5) | M28 clangd (N=10) | M29 style (N=10) | **M28v2 (N=10)** | Wilson 95% CI |
|---|---|---|---|---|---|
| off | 0% | 0% | 0% | **0% (0/10)** | [0%, 28%] |
| on-rule | 20% | 0% | 0% | **10% (1/10)** | [2%, 40%] |
| on-rule+placebo | 60% | 20% | 10% | **10% (1/10)** | [2%, 40%] |
| **on-rule+rat** | **50%** | **0%** | **0%** | **0% (0/10)** | [0%, 28%] |

## Pre-registered verdicts

| hypothesis | prediction | result | verdict |
|---|---|---|---|
| H1 (primary) | rat ≥ 30% | 0% | **REFUTED** at the ≤10% falsifier floor |
| H2 (efficiency) | input tokens < 2,000 | 1,024 | **confirms** |
| H3 (STOP gate) | off ≤ 20% | 0% | **passes** — no prose leak |

H1 + H3 together are the meaningful finding: **the LLM-generated
prose was successfully descriptive (off cell didn't lift) AND
ineffective at carrying the rationale signal (rat cell stayed at
zero)**.

## The locked predictor's prior was wrong

The M28v2 pre-reg locked this expectation before the run:

> "I expect H1 to confirm (rat ≥ 30%) — the M10.2 stub data + the
> M28/M29 falsifications form a chain of evidence that prose is the
> carrier."

The data refuted that prior. The methodology pattern just earned
its keep again: without the locked falsifier, the temptation would
be either "prose needs a better summarizer (Haiku)" or "prose
needs different phrasing" — both unfalsifiable spin.

## What this means for the M10.2 baseline

Re-reading the M10.2 `StubCppIndexer` block carefully:

> "Call sites of fetchWithRetry (3 references in this corpus):
>
>   src/backoff_loop.hpp:42 in BackoffLoop::run...
>   src/sync_worker.cpp:118 in SyncWorker::pull...
>   tests/test_retry.cpp:25 in test_runtime_error_swallowed_returns_nullopt..."

**`src/backoff_loop.hpp` and `src/sync_worker.cpp` do not exist in
the scenario directory.** The scenario has exactly two files:
`reference/retry.hpp` and `tests/test_retry.cpp`. The stub was
authoring fictional but plausible call sites — including the
referenced types `BackoffError` and `BackoffLedger`, the
"production-incident 2024-09-12" anchor, and the prose narration
about contract violations.

Real LSP queries (clangd) cannot surface these — they don't exist.
Real LLM summarization (M28v2) cannot generate them — the
summarizer correctly limited itself to the actual files.

Two readings of the M10.2 effect, both troubling:

1. **The stub's lift was carried by fictional details that
   reinforced the contrarian framing** — invented call sites in
   files the model couldn't verify, an invented incident anchor.
   If true, that's not a generalizable lever; it's a hand-crafted
   plausibility hack. It would not survive in any real codebase
   where the model could check the references.

2. **N=5 noise.** The M10.2 rat cell was 3/6 with Wilson 95% CI
   **19-81%**. The point estimate is 50% but the band overlaps
   with M28v2's 0% rat cell (CI 0-28%) at the right tail. At
   N=5, distinguishing a 50% intervention from a 30% one needs
   ~75 trials per cell for 80% power.

Either reading erodes M10.2's role as a credible baseline for
"semantic context lifts C++."

## What's actually true about C++ S1 now

After M28 + M29 + M28v2, the empirical picture for the locked S1
C++ scenario (qwen2.5-coder:32b, contrarian rule = swallow std::runtime_error):

| intervention | rat cell N=10 result |
|---|---|
| No intervention (M10.1b at N=5) | 0% |
| Structural facts via clangd (M28) | 0% |
| Style constraint alone (M29) | 0% |
| Structural facts + LLM-generated prose (M28v2) | 0% |
| Hand-curated fictional call sites + prose (M10.2 at N=5) | 50% — confounded baseline |

**No scalable C++ S1 intervention has been demonstrated to work.**
C++ stays definitively in the **weak** zone of EFFECTIVENESS.md's
fitness map.

## Methodology pattern: 8/8

| arc | what the pattern caught |
|---|---|
| M22a.0 - M22e (5 arcs) | prior wins |
| M19v2 | wrong-prediction surfaced even with favorable result |
| M28 | clangd indexer falsified under locked H1 |
| M29 | refuted + scenario-mismatch flagged via locked prior |
| **M28v2** | **predictor's prior falsified AND forced revision of the upstream M10.2 baseline (now suspect)** |

## What's left for C++

After three pre-registered refutations on one scenario, the
remaining candidates aren't about "different semantic context" —
they're about either changing the baseline or changing the
scenario:

1. **Re-run M10.2 at N=10** — same hand-curated stub, more trials,
   tighter CI. Tests whether the M10.2 effect was real or noise.
   Cheap (~20 min wall, no new code). If M10.2 still hits ~50%, the
   fictional-call-sites hack is confirmed real but unscalable. If it
   drops to ~10-20%, M10.2 was Type I error.

2. **Different scenario shape** — author a C++ S2 with multi-file
   structure AND a behavioral rule that doesn't pin idiom-level
   choices. Tests whether the C++ "weakness" is the language or
   the specific S1 setup. The user's original instinct on style
   constraint (M29) was that this scenario wasn't testing the
   intervention's natural habitat.

3. **Accept C++ stays weak.** EFFECTIVENESS.md continues to honestly
   document the C++ zone as weak. A workplace deploying Loom on a
   C++-heavy codebase needs to know this; better an honest
   limitation than a confounded claim.

4. **Move to a different language family.** The original M10 plan
   covered C/Go/C++ as the resistant cluster. If C++ resists every
   intervention, testing C and Go on the same scenario shape would
   complete the cluster picture before declaring victory on Python /
   Java / TS / Rust as Loom's strong-fit zone.

## Token-efficiency snapshot

| intervention | rat rate | mean in-tok | mean out-tok | tokens/pass | note |
|---|---|---|---|---|---|
| M10.2 stub (confounded) | 50% (3/6) | 1,111 | 259 | **2,740** | Pareto-optimal but now suspect |
| M28 (clangd structural) | 0% | 1,176 | 273 | — | refuted |
| M29 (style alone) | 0% | 795 | 270 | — | refuted, **cheaper** |
| **M28v2 (clangd + prose)** | **0%** | **1,024** | **266** | — | refuted; +prose 763 chars |

M28v2 sits between M28 and M29 on token cost; same null result. The
token-efficiency rollup ([`experiments/_meta/token_efficiency_rollup.py`](../_meta/token_efficiency_rollup.py))
will surface this when re-run with the M28v2 source added.

## Artifacts

| artifact | path |
|---|---|
| Pre-registration (locked) | [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) |
| Locked harness | [`m28v2_smoke.py`](m28v2_smoke.py) |
| Cached prose summary (recorded for reproducibility) | [`../bakeoff/runs-m28v2/_cached_prose.json`](../bakeoff/runs-m28v2/_cached_prose.json) |
| Trial summaries (40) | [`../bakeoff/runs-m28v2/`](../bakeoff/runs-m28v2/) |
| Captured finding | REQ-b096c333 (loom store) |

To reproduce on any machine with clangd 17+, g++, and
qwen2.5-coder:32b in Ollama:

```bash
PATH="<llvm-bin>:<g++-bin>:$PATH" \
  python3 experiments/m28v2_clangd_prose/m28v2_smoke.py --sweep --n 10
```
