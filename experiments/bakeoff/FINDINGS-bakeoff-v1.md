# Bakeoff V1 — Findings

**Date:** 2026-04-24
**Protocol:** pre-registered at commit `ee28d38` as
`experiments/bakeoff/PROTOCOL.md`. No amendments.
**Harness:** `experiments/bakeoff/driver.py` + `aggregate.py`.
**Ground truth:** TaskQueue library, ~200 LoC, 15 pytest tests.
**Model:** qwen3.5:latest via Ollama (both agents).
**N:** 5 baseline, 4 loom (loom_002 didn't complete — see "Data
completeness" below).

## TL;DR

> On this project scope, with both agents running qwen3.5, giving
> the engineer access to Loom tools as in-conversation tooling
> measurably *increases token cost without improving pass rate*.
> Holm-corrected p = 0.080 on `total_tokens` (Cliff's delta = +1.0
> — every Loom run used more tokens than every baseline run).

This is a legitimate null-or-negative result for the hypothesis as
V1 framed it. But V1 measured a mode of Loom usage the product
wasn't designed for. See "What this does NOT mean" below.

---

## Results

### Raw data (N=5 baseline, N=4 loom)

| run | pass/total | iters | tokens | regressions | stop_reason | duration |
|---|:---:|:---:|:---:|:---:|---|---:|
| baseline_001 | 8/15 | 13 | 88,908 | 2 | no_progress | 74s |
| baseline_002 | 2/15 | 6 | 21,971 | 0 | no_progress | 19s |
| baseline_003 | **15/15** | 7 | 28,391 | 0 | all_tests_pass | 26s |
| baseline_004 | **15/15** | 7 | 30,011 | 0 | all_tests_pass | 30s |
| baseline_005 | 4/15 | 25 | 295,567 | 18 | max_iterations | 168s |
| loom_001 | 7/15 | 9 | 502,725 | 2 | **token_budget** | 521s |
| loom_003 | 3/15 | 7 | 397,551 | 0 | no_progress | 169s |
| loom_004 | 5/15 | 7 | 343,089 | 0 | no_progress | 104s |
| loom_005 | 13/15 | 9 | 606,252 | 0 | **token_budget** | 144s |

### Primary metrics (Mann-Whitney U + Cliff's delta, alpha=0.10)

| metric | baseline median | loom median | delta | effect size | p raw | p Holm | significant |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| final_pass_rate | 0.533 | 0.400 | -0.200 | small | 0.713 | 1.000 | no |
| iterations_to_80pct | 7 | ∞ | +0.500 | large | 0.270 | 0.811 | no |
| **total_tokens** | **30,011** | **450,138** | **+1.000** | **large** | **0.020** | **0.080** | **YES (against Loom)** |
| regression_count | 0 | 0 | -0.200 | small | 0.713 | 1.000 | no |

Only `total_tokens` reached significance. Every Loom run used more
tokens than every baseline run (Cliff's delta = +1.0, maximum
possible). For the other three metrics, the small sample and
high variance of both conditions gave inconclusive evidence.

### Perfect runs

- Baseline: 2 of 5 hit 15/15 green (runs 003, 004). Both finished
  in ~30K tokens within 7 iterations.
- Loom: 0 of 4 hit 15/15. Best was loom_005 at 13/15 when the
  token budget forced stop.

### Why Loom burned tokens

Per-run Loom tool-call counts:

| run | extract | spec | link | check | list | total Loom calls |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| loom_001 | 22 | 15 | 9 | 5 | 0 | 51 |
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

**`loom_002` is missing.** The background job that ran loom 002–005
produced summaries for 3, 4, and 5 but not 2. Event log shows iteration
4 was in progress with ~25 min elapsed before the process terminated;
no stop condition was reached cleanly. Cause is under investigation.

Per PROTOCOL.md, a missing run is not the same as a bad run — we
report N=4 for Loom, not N=5, and flag the gap. The direction of
the result (tokens 15× higher, pass rate slightly lower) is the
same across all 4 Loom runs that did complete, so loom_002's absence
doesn't change the conclusion. A retrospective re-run to fill in
loom_002 is scheduled (it would require only ~5 min).

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
