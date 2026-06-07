# M10.2 Replication at N=10 — Pre-registration

**LOCKED:** 2026-06-06 (after M28 + M29 + M28v2 all refuted on this scenario)
**Methodology pattern:** REQ-3896db58

> **Hypothesis under test:**
> The original M10.2 hand-curated `StubCppIndexer` rat-cell result of
> 3/6 (50%, Wilson 95% CI 19-81%) holds at N=10. If the rat cell at
> N=10 lands in [30%, 70%], the original effect was a real (if
> confounded by fictional context) signal. If it lands ≤ 10%, the
> original was N=5 noise.

---

## Why this experiment

After M28 + M29 + M28v2 all refuted three different "semantic
context lifts C++" hypotheses on the locked S1 scenario, the M10.2
baseline (3/6 = 50% rat cell at N=5) became the load-bearing
anomaly. Two competing readings emerged in M28v2's FINDINGS.md:

1. **Real signal, confounded carrier:** the M10.2 stub's lift was
   carried by hand-crafted fictional context (file references to
   `backoff_loop.hpp`/`sync_worker.cpp` that don't exist; an invented
   "production incident 2024-09-12" anchor). The signal is real but
   unscalable — a hand-crafted plausibility hack.
2. **Noise:** the M10.2 rat cell was 3/6 at N=5; Wilson 95% CI
   spanned 19-81%. The 50% point estimate is consistent with a true
   underlying rate as low as 19%.

This replication discriminates between the two. No new intervention
— just more trials of the locked M10.2 harness.

## Pre-registered hypotheses

**H1 (primary, two-sided):** M10.2 N=10 rat cell ∈ [30%, 70%].

* **Confirms** (rat ∈ [30%, 70%]): the original effect was real signal.
  Reading 1 (fictional-context-as-carrier) is supported. EFFECTIVENESS.md
  gets a refined claim: "hand-crafted fictional context lifts C++
  compliance — but the mechanism doesn't scale to real codebases."
* **Refutes** (rat ≤ 10%): the original was Type I error at N=5.
  Reading 2 (noise) is supported. EFFECTIVENESS.md gets a stronger
  claim: "no scalable C++ S1 mechanism has been demonstrated across
  any tested shape, including the originally-cited baseline."
* **Inconclusive** (10-29% or 71-100%): unusual; would suggest
  the population mean is in a band the pre-reg didn't anticipate.
  Re-evaluate.

**H2 (sanity check):** Off cell, on-rule cell, placebo cell directions
hold roughly. Specifically, at N=10:
  * off ≤ 30% (was 0% at N=5)
  * on-rule ≤ 50% (was 20% at N=5)
  * placebo ≥ 30% (was 60% at N=5)

If any of these breaks badly, M10.2's full result was noisier than
just the rat cell — affects the read on what "M10.2 actually
measured."

## Locked harness

| Component | Locked value |
|---|---|
| Driver | the existing `experiments/bakeoff/v2_driver/phL2_crosssession_cpp_stub_indexer_smoke.py` (M10.2 baseline harness, UNMODIFIED) |
| Wrapper | `experiments/m10p2_replication/sweep_n10.py` — a thin loop that invokes phL2 once per (cell, run_id) for run_id 1-10 |
| Output dir | `experiments/bakeoff/runs-m10p2-n10/` (separate from runs-v2/phL2_* so the original N=5 stays preserved) |
| Executor model | `qwen2.5-coder:32b` (same as M10.2) |
| Scenario | Same `crosssession_cpp/s1_swallow_runtime_error/` |
| N per cell | 10 (fresh; not pooled with the original N=5) |

## Why fresh N=10 instead of pooling original 5 + 5 new

Pooling would mix trials from different days / different Ollama
states. Fresh N=10 is methodologically cleaner. The original M10.2
N=5 stays preserved as historical evidence in `runs-v2/phL2_*`;
the M10.2 FINDINGS doc will compare both N=5 and N=10.

## Methodology compliance checklist (REQ-3896db58)

| Step | Status |
|---|---|
| 1. Independent design review | user-completed via the "1" answer that triggered this experiment |
| 2. Pre-registration locked before code lands | this file, before sweep_n10.py runs |
| 3. Independent taxonomy check | N/A |
| 4. Cross-vendor judge calibration | N/A (deterministic g++ grading) |
| 5. Honest falsifier verdict | H1 binary at the [30%, 70%] band |

## Anti-Texas-sharpshooter commitments

1. **Exclusions locked.** Harness errors → replace, don't drop.
2. **Two pre-registered hypotheses (H1 + H2).** Post-hoc analysis
   beyond these is hypothesis-generation.
3. **Null results count.** Either H1 confirm OR refute is a real
   result. Inconclusive (10-29% or 71-100%) is itself informative —
   call it inconclusive, don't massage.
4. **The harness is locked.** No edits to phL2 between this commit
   and sweep completion.

## Predictor's prior (locked)

Given M28/M29/M28v2 all refuted, and the M10.2 stub references
fictional files, I lean toward **H1 REFUTES** (rat ≤ 10%). My prior
probability: ~60% refute, ~30% confirm, ~10% inconclusive.

Logging this prior protects against post-hoc spin in either
direction. If the data confirms H1 at ~50%, the finding should be
"unexpected signal sustains at N=10; the fictional-context hack
actually scales further than I expected" — not retconned as
"obvious in hindsight."

## Effort estimate

* Author sweep wrapper: 15 min
* Run sweep: ~20 min wall (40 trials × ~30s)
* Compute verdict + write findings: 30 min
* Total: ~1 hour

## References

- **M10.2 original findings:**
  [`../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md`](../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md)
- **M28v2 findings (the trigger):**
  [`../m28v2_clangd_prose/FINDINGS.md`](../m28v2_clangd_prose/FINDINGS.md)
- **REQ-b096c333** (M28v2 verdict + M10.2 reframe in loom store)
