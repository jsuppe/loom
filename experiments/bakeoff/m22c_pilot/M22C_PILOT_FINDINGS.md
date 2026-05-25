# M22c-pilot — Postmortem Finding (Floor-Too-Low)

**Locked:** 2026-05-25
**Status:** PILOT FAILED gates 2 + 6. Sweep NOT run, per pre-registration.
**Pre-reg:** [M22C_PREREGISTRATION.md](./M22C_PREREGISTRATION.md)

## Headline

**Pilot N=24 produced 0/24 compile-passing trials across all four arms.**
The hook-fact upper-bound arm (literal method signatures provided in the prompt)
compiled 0% just like no_context. This is a model-capability ceiling on the
qwen3.5:latest × multi-file-Dart workload combo, not a hide-rule design issue.

Per the locked pre-registration:

* Gate 2 (≥1 discordant outcome per arm-pair) **FAILED** — all arm pairs:
  neither=6, both=0. Scenarios do not discriminate at compile granularity.
* Gate 6 (floor non-degenerate) **FAILED** — floor is 0%, the bottom case.

**Decision:** stop the M22c arc as designed. Do not run the full sweep
(M22c.5). Capture this finding and pivot.

## Pilot run (N=24)

```
arm              n   comp_fail  link_fail  test_fail  test_pass  C+L_pass%
no_context       6          6          0          0          0      0.0% CI[0,39]
hook_rationale   6          6          0          0          0      0.0% CI[0,39]
hook_fact        6          6          0          0          0      0.0% CI[0,39]
placebo          6          6          0          0          0      0.0% CI[0,39]
```

All 5 paired McNemar comparisons: Δ=+0.0pp, p_exact=1.00, both=0, neither=6.

## What actually failed

Spot-check of representative trial stderr (all four arms produce the same
shape):

```
lib/services/customer_service.dart:1:8: Error: 'Store' isn't a type.
lib/services/customer_service.dart:11:29: Error: 'Customer' isn't a type.
lib/services/customer_service.dart:27:42: Error: 'Address' isn't a type.
```

The model writes correct-looking Dart but **does not emit the right
`import 'package:shop/types/customers.dart';`** etc. The visible sibling
files (e.g. `order_service.dart`) have the imports but qwen3.5:latest
(7B) does not transfer that pattern to its own output reliably.

Even the **hook_fact arm**, where the prompt literally contains the
method signatures verbatim, fails the same way — the model gets the
method shapes right but the import context wrong. This confirms it's not
a "missing context" problem; it's a model-capability ceiling.

## Pre-reg gates revisited

| gate | criterion | result |
|---|---|---|
| 1 | empty-response < 5% (1/24) | **PASS** — 0/24 empty responses |
| 2 | ≥ 1 discordant outcome per arm-pair | **FAIL** — all neither=6 |
| 3 | within-cell variance check | not reached |
| 4 | judge round-trip ≥ 95% | not reached |
| 5 | hand-spot-check ≥ 8/10 agreement | not reached |
| 6 | floor non-degenerate | **FAIL** — 0% floor across all arms |

Two of the pre-reg's pivot/redesign-or-stop gates failed. Per the
locked rules, the sweep does not run.

## What the floor failure means

The augmentation-effectiveness pilot is **silent on whether
hook-rationale helps**, because the workload + grader + model combo
floors below where any rationale-shaped signal could surface.

This is NOT a finding that hook-rationale is ineffective. It's a
finding that this benchmark setup cannot measure the effect.

A real conclusion would require one of:

* **(A) Stronger code model.** Use a larger / better-coding model
  (e.g. qwen3.5:14b, or claude-haiku-4-5, or a Dart-aware model)
  where the floor lifts above 0% on at least the hook-fact arm.
  This *changes the model arm of the experiment* and would need a
  new pre-reg.
* **(B) Easier workload.** Move from "regenerate a service file in
  a multi-file Dart project" to "implement a single function with
  explicit imports in scope." This makes the task more tractable
  but moves further from the "real loom usage" target.
* **(C) Different grader.** Drop compile/test grading; use the
  LLM-judged response 4-bin (as in M22a-regrade) as the primary
  metric. But the pre-reg pre-committed to NOT pivot to the
  4-bin engagement metric when compile/test goes against us
  (anti-Texas-sharpshooter rule).

**Path (C) is closed by the pre-reg's null-result pre-commitment.**
Paths (A) and (B) each break the design enough that they would
constitute a NEW study, not a continuation of M22c.

## Methodology assessment

The pre-reg gates DID their job: they caught a degenerate floor in N=24
(~3 minutes of compute) instead of in N=60 (~7.5 minutes) followed by
a writeup of a result that wasn't there. This is the value of locked
gates — failing early when the experiment can't measure what it was
designed to.

REQ-3896db58 (methodology pattern) **continues to earn its keep**:
6/6 across the M22 arc, with this M22c.4 result the first time the
pattern stopped a study *before* the sweep cost was paid.

## Other findings already captured by the design

* The "loom-context envelope is recognized by the model" question is
  unanswerable in this setup — model can't produce compile-passing
  output even when the answer is in the envelope.
* The hide-contract operational rule (per pre-reg Blocker 2) was
  applied as designed; nothing in the failure mode indicates a hide-rule
  bug. The rule kept the visible workspace at the "consumer files
  visible, target hidden" configuration we wanted.

## Cost summary

* **Pilot wall time:** 221s for 20 new trials + ~25s for 4 smoke trials ≈ **4 minutes**.
* **Full-sweep cost avoided:** ~5-8 additional minutes of compute, plus
  the much larger cost of writing up a null result without a known
  measurement floor.
* **Net:** the pre-reg gates paid for themselves on first use.

## Pivot proposals (each requires a new pre-reg, NOT continuation of M22c)

If the goal "characterize hook-rationale effectiveness on real coding
tasks" remains active, options:

1. **M22d (model-arm pivot).** Same workload + scenarios, but
   replace qwen3.5:latest with a stronger executor (qwen3.5:14b or
   a hosted API model). Re-run gates 1, 2, 6. If floor lifts above
   30%, proceed to full sweep.
2. **M22e (workload-simplification pivot).** Single-file Python or
   simple-Dart tasks where the model reliably produces compile-passing
   output. Move from "regenerate file" to "complete this function".
3. **Accept refuted-via-floor verdict.** M22a-regrade's engagement
   4-bin already produced a positive signal for loom-rationale
   ("proceeded with reasoning" 41% vs ≤6% other arms). M22c was a
   *replication-style* extension on compile/test grading; that
   replication does not happen in this configuration. The M22a
   engagement finding stands.

## Sub-milestone status

| sub | status |
|---|---|
| M22c.0 — methodology review | ✅ complete |
| M22c.1 — pre-registration | ✅ complete |
| M22c.2 — Dart workload scaffolding | ✅ complete |
| M22c.3 — 4-arm harness | ✅ complete |
| M22c.4 — pilot N=24 + gates | ✅ **complete (pilot FAILED gates 2+6 — sweep NOT run)** |
| M22c.5 — full sweep N=60 | ❌ **NOT RUN** per pre-reg null-result pre-commit |
| M22c.6 — analysis + findings | ✅ this document |

## Files

* `experiments/bakeoff/m22c_pilot/m22c_pilot.py` — harness
* `experiments/bakeoff/m22c_pilot/scenarios.json` — locked scenarios
* `experiments/bakeoff/runs-m22c-pilot/` — 24 trial summaries + raw outputs
* `experiments/bakeoff/m22c_pilot/M22C_PREREGISTRATION.md` — locked design
