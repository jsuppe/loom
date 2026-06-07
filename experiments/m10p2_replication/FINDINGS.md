# M10.2 Replication at N=10 — Findings

**Date:** 2026-06-06
**Verdict:** **H1 CONFIRMS.** The M10.2 rat cell signal sustains at
N=10 (4/10 = 40%, Wilson 95% CI 17-69%). The original 3/6 = 50% was
real signal, not N=5 Type I error. All H2 sanity checks pass.

Captured as **REQ-c38ea918** in the loom store.

---

## Result table — every cell sustains broadly within its N=5 band

| cell | M10.2 ORIG (N=5) | **M10.2 REPL (N=10)** | H2 threshold | result |
|---|---|---|---|---|
| off | 0% (0/5) | **20%** (2/10) | ≤ 30% | ✓ |
| on-rule | 20% (1/5) | **0%** (0/10) | ≤ 50% | ✓ |
| on-rule+placebo | 60% (3/5) | **60%** (6/10) | ≥ 30% | ✓ |
| **on-rule+rat** | **50%** (3/6) | **40%** (4/10) | **[30%, 70%]** | **✓ H1 confirms** |

Wilson 95% CIs at N=10:
* off: [5.7%, 51.0%]
* on-rule: [0%, 27.8%]
* placebo: [31.3%, 83.2%]
* rat: **[16.8%, 68.7%]** — the H1 band is [30%, 70%]; the lower CI
  bound (17%) is below 30%, but the *point estimate* (40%) is firmly
  inside the band and the CI excludes the falsifier band ≤ 10%.

## Pre-registered verdicts

| hypothesis | prediction | result | verdict |
|---|---|---|---|
| H1 (primary) | rat ∈ [30%, 70%] | 40% | **CONFIRMS** |
| H2.a sanity | off ≤ 30% | 20% | ✓ |
| H2.b sanity | on-rule ≤ 50% | 0% | ✓ |
| H2.c sanity | placebo ≥ 30% | 60% | ✓ |

## The locked predictor's prior was overturned

The M10.2-N10 pre-reg locked this prior before the run:

> "I lean ~60% refute, ~30% confirm, ~10% inconclusive — M28/M29/M28v2
> all refuted, and the stub references fictional files."

The data confirmed H1 — *the outcome I rated at 30% prior probability*.
This is the most informative kind of pre-reg result: high learning
value because the actual outcome was the unlikely one.

Without the locked prior, I'd have been tempted to retroactively
narrate "I always thought it might be real." The audit log shows
otherwise.

## What this means for the C++ S1 picture

Combined view across today's pre-registered C++ experiments:

| intervention | rat cell N=10 | note |
|---|---|---|
| No intervention (M10.1b at N=5) | 0% | baseline |
| M28 — clangd structural facts | 0% | refuted |
| M29 — style constraint alone | 0% | refuted |
| M28v2 — clangd + LLM-summarized prose | 0% | refuted; prose constrained to real files |
| **M10.2 — hand-curated fictional context** | **40%** | **confirmed real signal** |

The M10.2 stub's content that the LLM doesn't see anywhere else:

* Call sites at `src/backoff_loop.hpp:42` (file does not exist)
* Call sites at `src/sync_worker.cpp:118` (file does not exist)
* `BackoffError` and `BackoffLedger` type definitions (types do not exist)
* "Production incident 2024-09-12" anchor (incident is invented)
* Prose narration about how each fictional caller would be affected
  by a propagating exception

**The mechanism is: qwen2.5-coder:32b treats unverifiable but
plausibly-shaped context as authoritative weight on the rationale
cell's contrarian rule.** This isn't unique to qwen — it would be
worth replicating across other models to characterize the
generality — but it IS a methodologically important finding about
LLM behavior in the presence of plausible fabrication.

## Implications for the workplace narrative

The honest claim shifts. **Loom does not have a working C++ S1
mechanism** — the only context that lifts compliance requires
hand-crafted fictional details the executor can't verify, which is
not a deployable pattern. C++ stays in the **weak** zone of the
language fitness map.

The *methodologically* interesting finding is what gets surfaced:

> **"Pre-registered C++ work today produced three refutations (M28
> ClangdIndexer, M29 style constraint, M28v2 LLM-summarized prose)
> followed by an unexpected confirmation of the M10.2 baseline at
> N=10. The confirmation is troubling: the only context that works
> is fictional/unverifiable, suggesting the executor treats
> plausibly-shaped context as authoritative regardless of whether
> the user could verify it. This is itself a finding worth
> investigating — not a Loom feature, but a property of executor
> behavior that affects how Loom prompts should be designed."**

That's a richer story than any single confirmation would have been.

## Methodology pattern: 9/9, with the most informative outcome yet

| arc | what it caught |
|---|---|
| M22a.0 - M22e (5) | structural confounds + scenario pivots pre-launch |
| M19v2 | wrong-prediction surfaced even with favorable result |
| M28 | clangd indexer falsified under locked H1 |
| M29 | refuted + scenario-mismatch flagged via locked prior |
| M28v2 | predictor's prior falsified; M10.2 reframed |
| **M10.2 N=10** | **predictor's prior falsified by CONFIRMATION; M10.2 reproducible at N=10; LLM-plausibility-vs-verifiability finding emerges** |

## Token efficiency snapshot

| intervention | rat rate | mean in-tok | mean out-tok | tokens/pass |
|---|---|---|---|---|
| M10.2 ORIG (N=5) | 50% (3/6) | 1,111 | 259 | 2,740 |
| **M10.2 REPL (N=10)** | **40%** (4/10) | **1,111** | **263** | **3,435** |
| M28 (clangd structural) | 0% (0/10) | 1,176 | 273 | — |
| M29 (style) | 0% (0/10) | 795 | 270 | — |
| M28v2 (clangd + prose) | 0% (0/10) | 1,024 | 266 | — |

Token cost at N=10 is virtually identical to the N=5 original — same
stub, same scenario, just more trials. The 2,740 vs 3,435 difference
is the pass-rate denominator: ratio = (mean tokens × n) / k, so 40%
gives a higher ratio than 50%.

## Follow-up research directions surfaced

1. **Plausibility-vs-verifiability characterization.** Vary the
   M10.2 stub block to test what specifically the model is keying
   on. Strip the production-incident timestamp (M10.2v1). Replace
   fictional file paths with explicit `// FICTIONAL EXAMPLE` markers
   (M10.2v2). Either still lifts the rat cell, or one doesn't —
   tells us which carrier matters.

2. **Cross-model replication.** Does qwen3.5:latest show the same
   M10.2 effect? Llama 3.1:8b? Anthropic Haiku? If only
   qwen2.5-coder:32b responds to plausible fabrication this way,
   it's a model-specific artifact. If multiple models do, it's a
   broader LLM property worth a separate study.

3. **Verifiable equivalents.** Could a "structured verifiable
   context" object (clangd refs + LLM prose + provenance tags)
   substitute for the fictional context? The user could then
   trust what the model trusts. This is the actual Loom product
   direction if the M10.2 mechanism is a real signal we want to
   harness ethically.

## Artifacts

| artifact | path |
|---|---|
| Pre-registration | [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) |
| Sweep driver | [`sweep_n10.py`](sweep_n10.py) (wraps unmodified phL2) |
| Trial summaries (40) | [`../bakeoff/runs-m10p2-n10/`](../bakeoff/runs-m10p2-n10/) |
| Original M10.2 N=5 evidence | [`../bakeoff/runs-v2/phL2_s1_cpp_*_run{1..5}_summary.json`](../bakeoff/runs-v2/) — untouched |
| Captured finding | REQ-c38ea918 (loom store) |

To reproduce:

```bash
PYTHONIOENCODING=utf-8 \
  python3 experiments/m10p2_replication/sweep_n10.py --n 10
```
