# Bakeoff V1 — Findings

**Date:** 2026-04-24 (revised after loom_002 completed)
**Protocol:** pre-registered at commit `ee28d38` as
`experiments/bakeoff/PROTOCOL.md`. No amendments.
**Harness:** `experiments/bakeoff/driver.py` + `aggregate.py`.
**Ground truth:** TaskQueue library, ~200 LoC, 15 pytest tests.
**Model:** qwen3.5:latest via Ollama (both agents).
**N:** 5 baseline, 5 loom (loom_002 re-run as step 4 of the V2 prep).

## TL;DR

> On this project scope, with both agents running qwen3.5, giving
> the engineer access to Loom tools as in-conversation tooling
> measurably *increases token cost without improving pass rate*.
> Holm-corrected p = 0.049 on `total_tokens` with Cliff's delta = +1.0
> — **every single Loom run used more tokens than every single
> baseline run.** Median Loom run: 490K tokens vs baseline: 30K
> tokens (16× more).

This is a legitimate null-or-negative result for the hypothesis as
V1 framed it. But V1 measured a mode of Loom usage the product
wasn't designed for. See "What this does NOT mean" below.

---

## Results

### Raw data (N=5 per condition)

| run | pass/total | iters | tokens | regressions | stop_reason | duration |
|---|:---:|:---:|:---:|:---:|---|---:|
| baseline_001 | 8/15 | 13 | 88,908 | 2 | no_progress | 74s |
| baseline_002 | 2/15 | 6 | 21,971 | 0 | no_progress | 19s |
| baseline_003 | **15/15** | 7 | 28,391 | 0 | all_tests_pass | 26s |
| baseline_004 | **15/15** | 7 | 30,011 | 0 | all_tests_pass | 30s |
| baseline_005 | 4/15 | 25 | 295,567 | 18 | max_iterations | 168s |
| loom_001 | 7/15 | 9 | 502,725 | 2 | **token_budget** | 521s |
| loom_002 | 3/15 | 8 | 490,007 | 0 | no_progress | 120s |
| loom_003 | 3/15 | 7 | 397,551 | 0 | no_progress | 169s |
| loom_004 | 5/15 | 7 | 343,089 | 0 | no_progress | 104s |
| loom_005 | 13/15 | 9 | 606,252 | 0 | **token_budget** | 144s |

### Primary metrics (Mann-Whitney U + Cliff's delta, alpha=0.10)

| metric | baseline median | loom median | delta | effect size | p raw | p Holm | significant |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| final_pass_rate | 0.533 | 0.333 | -0.280 | small | 0.531 | 1.000 | no |
| iterations_to_80pct | 7 | ∞ | +0.520 | large | 0.210 | 0.630 | no |
| **total_tokens** | **30,011** | **490,007** | **+1.000** | **large** | **0.012** | **0.049** | **YES (against Loom)** |
| regression_count | 0 | 0 | -0.240 | small | 0.602 | 1.000 | no |

Only `total_tokens` reached significance — AGAINST Loom. Every Loom
run used more tokens than every baseline run (Cliff's delta = +1.0,
the maximum possible). For the other three metrics, the small sample
and high variance of both conditions gave inconclusive evidence, but
the direction is consistently worse for Loom.

### Perfect runs

- Baseline: 2 of 5 hit 15/15 green (runs 003, 004). Both finished
  in ~30K tokens within 7 iterations.
- Loom: 0 of 5 hit 15/15. Best was loom_005 at 13/15 when the
  token budget forced stop.

### Why Loom burned tokens

Per-run Loom tool-call counts:

| run | extract | spec | link | check | list | total Loom calls |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| loom_001 | 22 | 15 | 9 | 5 | 0 | 51 |
| loom_002 | 30 | 2 | 6 | 0 | 14 | 52 |
| loom_003 | 10 | 0 | 9 | 0 | 12 | 31 |
| loom_004 | 7 | 1 | 9 | 2 | 4 | 23 |
| loom_005 | 24 | 3 | 9 | 0 | 21 | 57 |

Reading the event logs, the dominant failure mode is the engineer
calling `loom_extract` repeatedly, sometimes 22+ times, re-capturing
requirements it had already extracted. It re-emitted the full
req text in each call's args and then narrated the action back in
its reply. Cumulative token cost compounded fast.

`loom_list` usage in runs 3 and 5 was the engineer checking what it
had already captured — a symptom of the same confusion (the engineer
couldn't track Loom state in its conversation history).

These aren't harness bugs. This is qwen3.5 at 9.7B failing to reason
about **when** and **what** to capture, then making bookkeeping calls
that filled its context with redundant work.

---

## What this means

### The honest negative read

In its current form, invoking Loom as in-session tools during a small
(~200 LoC) project with a small local model (qwen3.5:latest)
demonstrably hurts more than helps on this evidence:
- No run reached a perfect grade in the Loom condition.
- Every Loom run used more tokens than every baseline run.
- Two Loom runs hit the token budget cap before finishing; zero
  baseline runs did.
- The engineer's Loom-related reasoning (deciding what to capture,
  avoiding duplicates) ate tokens without improving code output.

### What this does NOT mean

**V1 measured a use of Loom the product was not designed for.**
Specifically, V1 put qwen3.5 on BOTH sides of the conversation AND
gave the engineer Loom tools to use in-session. That's different from
Loom's validated architecture:

The `experiments/gaps/FINDINGS.md` experiment validated a specific
claim: *qwen3.5 matches Opus 4.7 on atomic tasks when it receives
a pre-assembled Loom context bundle as its prompt.* In that setup,
the model never *calls* Loom tools — it receives Loom's output.

The `loom decompose` + `loom_exec` pipeline rides this validated
path: a capable model (Opus) curates structure once via Loom; the
cheap model (qwen3.5) consumes one atomic task at a time. Cost
estimate for a 100-task project: ~$0.60, versus ~$30 for a
frontier-only run.

V1 collapsed that asymmetry. Both agents ran qwen3.5. qwen couldn't
simultaneously reason about requirements, make good Loom decisions,
AND write code. Token overhead dominated because a 9.7B model was
being asked to do a task it was never shown to be good at.

### What V1 does NOT test

- Cross-session handoff (agent A leaves, agent B picks up from store)
- Loom in long-context-pressure scenarios
- Asymmetric model pairs (capable model curates, cheap model codes)
- Loom as a persistent memory across weeks, not minutes
- Larger projects where the agent can't hold the whole spec in
  working memory

The thesis of Loom is primarily about these scenarios. V1's scope
didn't touch them.

---

## Data completeness

Initial V1 capture had `loom_002` incomplete — the first background
invocation didn't produce a summary (event log showed iteration 4
in progress then terminated). Cause was the shared background
process being preempted; not a run-level failure.

**Re-ran `loom_002` on the unchanged Ollama harness** (step 4 of
the V2 preparation). Result: 3/15 pass, 8 iterations, 490K tokens,
0 regressions — in-range with the other 4 Loom runs and reinforces
the conclusion. Updated stats reflect complete N=5/5.

---

## What we're doing next

**This finding motivates Bakeoff V2.** Rather than abandon the
thesis, V2 tests Loom in the architecture it was designed for.

V2 extends the protocol with two Sonnet conditions:

| Condition | PO agent | Engineer agent | Loom tools |
|---|---|---|---|
| C3 — Sonnet + Loom | Sonnet 4.6 | Sonnet 4.6 | yes |
| C4 — Sonnet baseline | Sonnet 4.6 | Sonnet 4.6 | no |

C3 vs C4 tests: does Loom-as-tools help when the agent has the
reasoning capacity to use it well? C4 vs C1 tests: does model
capability alone close the gap?

Pre-registration in `PROTOCOL-v2.md` before the harness is extended.

---

## Publication commitment

Per PROTOCOL.md: this finding is on the record regardless of
direction. It does not update the ROADMAP's Milestone 0 claims
(which remain valid for `loom decompose` → `loom_exec` — the
asymmetric path the gaps experiment validated). It does add a
warning that **agent-facing Loom tools in a small single-session
project with a small local model measurably underperforms.** The
product's answer to that failure mode is the `loom decompose` /
`loom_exec` architecture, not in-session tool use.

Neither the PROTOCOL nor the metric definitions were changed after
seeing the data. The only post-data decision was to proceed with V2
as outlined above — which itself is a pre-registered design in
`PROTOCOL-v2.md`, committed before the new harness code.
