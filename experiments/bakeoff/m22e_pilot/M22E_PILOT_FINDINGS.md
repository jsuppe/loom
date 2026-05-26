# M22e-pilot — Postmortem Finding (Ceiling-Bound, Sweep NOT Run)

**Locked:** 2026-05-25
**Status:** PILOT FAILED gate 6 (ceiling-bound) and gate 7 (hook_fact does not discriminate). Sweep NOT run, per pre-registration.
**Pre-reg:** [M22E_PREREGISTRATION.md](./M22E_PREREGISTRATION.md)
**Amendments:** [M22E_PREREGISTRATION_AMENDMENTS.md](./M22E_PREREGISTRATION_AMENDMENTS.md)

## Headline

**Pilot N=24 produced compile+link saturation: 3/4 arms hit 100% pass rate**
(`no_context`, `hook_fact`, `placebo`). The only arm under 100% was
`hook_rationale` at 83.3% — explained by a single compile_fail trial,
not a systematic effect (N=6, McNemar p=1.00).

Per the locked pre-registration:

* Gate 6 (floor + ceiling band): **FAILED (ceiling-bound)** — no_context
  compile+link pass rate = 100%, ABOVE the pre-registered [25%, 75%]
  upper bound. The compile+link metric is saturated; it cannot
  discriminate rationale signal on this workload.
* Gate 7 (hook_fact discriminates ≥10pp over no_context): **FAILED** —
  hook_fact = 100%, no_context = 100%, Δ = 0pp.
* Primary metric outcome: **OPPOSITE direction** — placebo 100% beats
  hook_rationale 83.3% by 16.7pp. McNemar exact p=1.00 (a single
  discordant pair). Per pre-reg falsifier table, this is `OPPOSITE`.

**Decision:** stop the M22e arc as designed. Do not run the full sweep
(M22e.5). Capture this finding and pivot or stop.

## Pilot run (N=24)

```
arm              n   comp_fail  link_fail  test_fail  test_pass  C+L_pass%
no_context       6          0          0          6          0    100.0% CI[61,100]
hook_rationale   6          1          0          5          0     83.3% CI[44,97]
hook_fact        6          0          0          6          0    100.0% CI[61,100]
placebo          6          0          0          6          0    100.0% CI[61,100]
```

Paired McNemar (compile+link primary):

```
  hook_rationale  vs placebo         | Δ=-16.7pp | p_exact=1.0000  OPPOSITE
  hook_rationale  vs no_context      | Δ=-16.7pp | p_exact=1.0000  OPPOSITE
  hook_fact       vs placebo         | Δ= +0.0pp | p_exact=1.0000  NULL
  hook_fact       vs hook_rationale  | Δ=+16.7pp | p_exact=1.0000  NULL
  hook_fact       vs no_context      | Δ= +0.0pp | p_exact=1.0000  NULL
  placebo         vs no_context      | Δ= +0.0pp | p_exact=1.0000  NULL
```

The Δ=−16.7pp on the primary `hook_rationale vs placebo` comparison is
driven by **exactly one** trial of N=6 (`s_retry hook_rationale t2`
produced no extractable code — the model output ran to 4096 tokens
without closing a fence). It is not a systematic effect.

## Why this happened — workload too easy at compile+link granularity

Pre-registration predicted no_context floor = **40-65%** compile+test
pass rate. Actual = **100%** compile+link. The prediction was wrong
by a wide margin.

Reasons (post-hoc analysis, not part of pre-reg):

1. **JS/TS layout was explicit in the prompt.** The import_block envelope
   eliminated the M22c file-layout-hallucination confound (the
   confound-elimination move was load-bearing). But it also removed the
   single most common reason for compile failure on qwen3.5:latest's
   output — wrong imports. Once imports are stable, qwen3.5 produces
   compileable JS for non-trivial functions with high reliability.
2. **JS is in qwen3.5:latest's strong-prior zone.** Even at 7B, single-
   file JS with standard ES module patterns is one of the model's most
   reliable output domains. The capability-floor problem from M22c (Dart
   multi-file → 0% compile) inverts to a ceiling problem here
   (JS single-file → 100% compile).
3. **The 4-bin grading (compile_fail / link_fail / test_fail / test_pass)
   is too coarse for this workload.** The interesting variation is at
   the sub-test pass-rate granularity, not the binary compile+link
   threshold.

## What the pre-reg forbids and we will NOT do

* Switch the primary metric to sub-test pass rate post-hoc. The pre-reg
  explicitly forbids this in §"NOT acceptable": "swapping the primary
  test to the response-4-bin if compile/test goes against us." The same
  rule applies a fortiori to swapping to a different compile-grade
  granularity that produces a more favorable headline.
* Drop the `s_retry hook_rationale t2` trial as an outlier to make
  hook_rationale tie at 100% — that would be cherry-picking. We report
  the OPPOSITE-direction result as the locked rule requires.
* Run the N=120 sweep "anyway" to see if the variance settles — the
  pre-reg's gate 6 hard-fail says sweep does not run.

## What the pre-reg DOES allow us to report descriptively

The sub-test pass rate distribution surfaces an interesting pattern
worth recording as a finding, NOT as a primary verdict:

| arm | mean sub-pass | individual trial sub-pass (out of 25-26) |
|---|---|---|
| no_context | 15.7 | 7, 22, 6, 21, 18, 20 |
| hook_rationale | 17.7 | 22, 22, 22, **0**, 20, 20 |
| hook_fact | 14.0 | 7, 4, 20, 17, 18, 18 |
| placebo | 20.5 | 22, 22, 19, 20, 20, 20 |

Three observations, each explicitly framed as DESCRIPTIVE-only:

1. **Placebo has the highest sub-test mean (20.5).** Possibly because
   the neutral CI/formatting notes ground the model in a "boring
   production project" context without imposing constraints. Cannot be
   used as evidence that placebo helps because the pre-reg locked
   compile+link as primary.
2. **hook_fact UNDER-performs no_context on sub-tests (14.0 vs 15.7).**
   The literal signature envelope appears to mislead the model on some
   scenarios (s_aggregate: 4-7/25 on hook_fact vs 22/25 on placebo).
   Possibly the model anchors too hard on the signature text and
   misinterprets test contract details.
3. **hook_rationale is bimodal.** Sometimes excellent (22/25 on
   s_aggregate × 2 trials), sometimes catastrophic (0/26 on s_retry t2).
   Higher mean than no_context but much higher variance. Consistent
   with the M22a-regrade finding that hook-rationale activates more
   interpretive reasoning ("proceeded with reasoning" 41% vs ≤6% other
   arms) — that reasoning can either help or hurt depending on whether
   the rationale aligns with the test contract.

These are **observations from the pilot**, NOT a refined hypothesis
that justifies running M22e's sweep on a different metric.

## Pre-reg gates revisited

| gate | criterion | result |
|---|---|---|
| 1 | empty-response < 5% (1/24 max) | **PASS** — 0/24 empty (the single hook_rationale compile_fail was a code-extraction failure, not an empty response) |
| 2 | ≥ 1 discordant outcome per arm-pair | **PARTIAL FAIL** — 3 of 6 arm-pairs have 0 discordance (the three pairs not involving hook_rationale) |
| 3 | within-cell variance check | PASS (Amendment 2 enabled) — t1 sub-pass ≠ t2 sub-pass on most cells |
| 4 | judge round-trip ≥ 95% | not reached |
| 5 | hand-spot-check ≥ 8/10 agreement | not reached |
| 6 | floor + ceiling band [25%, 75%] | **FAIL — ceiling-bound** — no_context = 100% |
| 7 | hook_fact discriminates ≥10pp over no_context | **FAIL** — Δ = 0pp |

Pre-reg's hard-stop list includes (1), (2), (4). Gate 2 partial fail is
itself a signal: 3 of 6 arm-pairs cannot discriminate because of
ceiling saturation. Gate 6 explicitly says "halt sweep, redesign single
hide-rule for stronger context-strip" — but for single-file workload
the only context-strip available is removing the import_block, which
would reintroduce the M22c confound this pivot was built to eliminate.

## Pre-registered pivot-killer Q1 outcome

The pre-reg's pivot-killer Q1 said:

> If the pilot N=24 produces no_context compile+test pass rate outside
> [25%, 75%] AND the band-edge predicted by the redesign rule cannot
> be hit by a minor hide-rule tweak, the verdict is REFUTED-VIA-FLOOR.

Floor band failure direction is CEILING (not floor) — semantic
adjustment but the spirit is identical: the workload + grader combo
cannot measure hook-rationale signal at this granularity. There is no
"minor hide-rule tweak" available for single-file workload that
wouldn't reintroduce M22c's confound.

**Per the pre-reg's pivot-killer commitment, the verdict is:**

> **REFUTED-VIA-CEILING.** The compile+link grading methodology cannot
> measure hook-rationale signal on this workload at qwen3.5:latest's
> capability tier. M22a-regrade's engagement 4-bin signal stands as
> the existing positive evidence; M22e does not add new compile/test
> evidence either way.

## Methodology assessment

For the second consecutive study, pre-registered gates stopped the
study before the sweep cost was paid. The M22 methodology pattern
(REQ-3896db58) is now **7/7** — twice now in M22-arc has the pattern
prevented running a sweep that could not have measured the intended
effect.

Two amendments were made during M22e.3 smoke-testing and were
transparently documented in M22E_PREREGISTRATION_AMENDMENTS.md:

1. **Placebo source change** — borrowing other scenarios' rationales
   caused semantic interference; replaced with task-orthogonal project
   notes. Discovered via runaway-comment-loop failure on first smoke
   trial.
2. **Sampling regime change** — temp=0 + fixed seed (inherited from
   M22c) produces bit-identical trials, collapsing the planned N=120
   sweep to N=12 unique outcomes. Moved to temp=0.3 + per-trial seed
   so each trial is a real independent draw while remaining replayable.

Neither amendment touched the comparison structure, falsifier
thresholds, primary metric, exclusion rule, or hypothesis. Both were
discovered-bug-in-harness fixes.

## Pivot proposals (each requires a NEW pre-reg, NOT continuation of M22e)

If the goal "characterize hook-rationale effectiveness on real coding
tasks via compile/test grading" remains active, options:

1. **M22f (hardness pivot).** Single-file but more contract-complex
   workload where qwen3.5:latest's no_context floor lands in [25%,
   75%]. E.g. retry with circuit-breaker + jitter; validate with
   async checks; aggregate with windowing. Risk: more contract
   complexity expands rationale-leak surface area.
2. **M22g (metric pivot, requires new pre-reg).** Switch primary
   metric to a continuous sub-test pass rate (or t-test on means)
   with explicit pre-registration of the new metric. Cannot continue
   M22e under this — must be a fresh study with the metric locked
   from the start, NOT post-hoc on M22e data (Texas-sharpshooter
   forbidden).
3. **Accept the existing engagement-signal verdict.** M22a-regrade's
   "proceeded with reasoning" 41% vs ≤6% finding stands as the
   existing positive evidence for loom-rationale. M22c and M22e
   were both replication-style extensions on compile/test grading
   that did not produce additional positive evidence. Stop the
   augmentation-effectiveness research arc and shift to operational
   work (e.g. M19 real-world drift evaluation, M16.3 Python LSP
   indexer, M20.3 L4 productionization).

## Cost summary

* **Pilot wall time:** 60 seconds for 22 new trials + ~10s smoke ≈
  **~70 seconds total.**
* **Full-sweep cost avoided:** ~5 minutes of compute, plus the much
  larger cost of writing up a saturated-metric null result.
* **Net:** the pre-reg gates paid for themselves on second use too.

## Sub-milestone status

| sub | status |
|---|---|
| M22e.0 — methodology review | ✅ complete |
| M22e.1 — pre-registration | ✅ complete |
| M22e.1a — independent leak-grading | ✅ complete (3/3 PASS) |
| M22e.2 — JS/TS workload scaffolding | ✅ complete (76/76 oracle tests pass) |
| M22e.3 — 4-arm harness | ✅ complete (with 2 documented amendments) |
| M22e.4 — pilot N=24 + gates | ✅ **complete (gates 6+7 FAIL — sweep NOT run)** |
| M22e.5 — full sweep N=120 | ❌ **NOT RUN** per pre-reg null-result pre-commit |
| M22e.6 — analysis + findings | ✅ this document |

## Files

* `experiments/bakeoff/m22e_pilot/m22e_pilot.py` — harness
* `experiments/bakeoff/m22e_pilot/scenarios.json` — locked scenarios
* `experiments/bakeoff/benchmarks/js-singlefile/` — reference workspace
* `experiments/bakeoff/runs-m22e-pilot/` — 24 trial summaries + raw outputs
* `experiments/bakeoff/m22e_pilot/M22E_PREREGISTRATION.md` — locked design
* `experiments/bakeoff/m22e_pilot/M22E_PREREGISTRATION_AMENDMENTS.md` — 2 documented harness fixes
* `experiments/bakeoff/m22e_pilot/M22E_LEAK_GRADING.md` — independent leak-grading record
