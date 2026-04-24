# Bakeoff V2 Phase A — Findings

**Date:** 2026-04-24
**Protocol:** `PROTOCOL-v2.md` + Amendment 1 (Claude Code subagents
via `claude -p` headless mode)
**Ground truth:** TaskQueue library (python-queue benchmark), ~200
LoC, 15 hidden pytest tests
**N:** 5 per cell, 10 cells, 50 runs total
**Driver:** `v2_driver/driver.py` using `claude -p --no-session-
persistence --output-format json --model {haiku,sonnet,opus}`
**Runtime:** 171.6 minutes wall-clock (~3.4 min average per run)
**Errors:** 0 / 50

---

## TL;DR

> Every single run hit 15/15 green. TaskQueue is completely
> saturated at the Claude tier — pass_rate uniformly 1.0 across all
> model pairs and Loom settings. Phase A therefore cannot answer
> *does Loom help?* It can only measure **cost overhead of using
> Loom when correctness is already perfect.**
>
> Loom adds **+12% to +48% cost** at different model tiers. Overhead
> shrinks with model capacity (Opus +12%, Sonnet +37%, Haiku +45%,
> asymmetric pairs +20–48%). **Direction reverses cleanly from V1:**
> qwen-with-Loom wasted 16× tokens for worse outcomes; Claude models
> with Loom waste only modest overhead for *equivalent* outcomes.
> Loom's in-session agent path is now bounded — not catastrophic at
> any Claude tier — but not yet demonstrated to produce value.

---

## Per-cell results (N=5 medians)

| PO | Eng | Loom | iters | $/run | Loom overhead |
|---|---|:---:|:---:|:---:|:---:|
| Haiku | Haiku | − | 6 | 0.44 | — |
| Haiku | Haiku | + | 7 | 0.64 | **+45%** |
| Sonnet | Sonnet | − | 5 | 0.68 | — |
| Sonnet | Sonnet | + | 5 | 0.93 | **+37%** |
| Opus | Opus | − | 6 | 1.85 | — |
| Opus | Opus | + | 5 | 2.08 | **+12%** |
| Sonnet | Opus | − | 5 | 1.22 | — |
| Sonnet | Opus | + | 5 | 1.81 | **+48%** |
| Opus | Sonnet | − | 5 | 1.04 | — |
| Opus | Sonnet | + | 5 | 1.25 | **+20%** |

All pass rates: **1.0** (15/15) — saturated.

Costs are notional ($ equivalent to pay-as-you-go API pricing). All
actual billing against Max subscription — zero out of pocket.

---

## Findings

### F1: TaskQueue is too easy for the Claude tier

Every one of 50 runs hit 15/15. The benchmark saturates any Claude
model, with or without Loom. **We cannot measure Loom's impact on
correctness using this benchmark at this model tier.**

This is a methodological limitation, not a negative result. It means
Phase A was answering a different question than intended.

### F2: Loom adds cost overhead in all cells, without exception

Every +Loom cell is more expensive than its −Loom counterpart. Over
the 25 +L vs 25 −L pairings, there's zero crossover. The overhead
is real and consistent:

| model tier | overhead |
|---|---|
| Opus symmetric | +12% |
| Opus PO + Sonnet Eng | +20% |
| Sonnet symmetric | +37% |
| Haiku symmetric | +45% |
| Sonnet PO + Opus Eng | +48% |

### F3: Loom overhead shrinks with model capacity

Opus uses Loom with +12% overhead; Sonnet +37%; Haiku +45%. More
capable models spend proportionally less on Loom bookkeeping
relative to their baseline cost. Two possible readings:

1. **Capable models make better Loom decisions** — fewer extracts,
   cleaner links, less narration. Consistent with the V2-pilot
   observation (Sonnet made 6 clean extracts for 6 reqs; V1 qwen
   made 22+ redundant extracts for the same 6 reqs).
2. **Capable models do more work per token anyway** — so the
   incremental Loom overhead is a smaller fraction of total.

Both are plausible. Phase B or C might let us separate them.

### F4: The qwen+Loom failure mode from V1 does not generalize

V1's qwen-qwen-with-Loom result was catastrophic: 16× tokens, worse
pass rate. V2 Phase A shows no Claude model pair produces anything
like that. Even Haiku (cheapest Claude) stays within +45% overhead
and matches baseline correctness.

**The 9.7B→Claude jump is where Loom-as-in-session-tools becomes
survivable.** Below that capacity, Loom is a distractor; at and
above it, Loom is at worst modest overhead.

### F5: Loom never improves anything in Phase A data

On this benchmark at this model tier, Loom does not:
- Improve pass rate (already 1.0 everywhere)
- Reduce iteration count (5 iters median in most cells regardless)
- Reduce cost (every +L cell costs more)
- Reduce regressions (0 regressions in almost every run)

**This is consistent with Loom being irrelevant overhead on a task
that fits in working memory.** It neither hurts much nor helps at
all. To see value, we need tasks where the *structured memory* Loom
provides is actually load-bearing.

### F6: The asymmetric cells behave predictably

Sonnet×Opus and Opus×Sonnet both land between the pure Sonnet and
pure Opus symmetric costs, as a rough average. No surprising
interaction effect. **Opus-PO + Sonnet-Eng ($1.04/$1.25) is
measurably cheaper than pure Opus ($1.85/$2.08) while matching
correctness** — relevant if teams deploy asymmetrically to save
cost.

---

## Cost summary (full Phase A)

| | sum $ | median $ | avg $ |
|---|---|---|---|
| Loom side (25 runs) | ~$33.50 | $1.25 | $1.34 |
| Baseline side (25 runs) | ~$25.00 | $1.04 | $1.00 |
| **Phase A total** | **~$58.50** | — | — |

Notional. Covered by Max subscription; $0 actually spent.

Runtime: 171.6 minutes wall-clock for 50 runs, 10s inter-run sleep.
Average ~3.4 min per run.

---

## What we still don't know

Phase A establishes a cost map. It doesn't answer:

1. **Does Loom reduce regressions on tasks with cross-file state?**
   TaskQueue is single-file. Cross-module code may regress when
   agents can't remember all the pieces; Loom may help there.

2. **Does Loom close the pass-rate gap on tasks beyond model
   capacity?** If a task is hard enough that Haiku fails to
   complete it, does Haiku+Loom recover? (This is the key
   "capability amplification" claim.)

3. **Does Loom help with long-context tasks?** Claude Code trims
   context aggressively. On a 20+-iteration run, Loom-as-persistent-
   memory should pay off. TaskQueue completes in ~5 iters and never
   stresses context.

4. **How does the delegation architecture (Sonnet Eng +
   loom_exec → qwen codegen) compare?** Not in Phase A; reserved
   for Phase D or dropped if time-pressed.

These are Phase B (state-machine), Phase C (Flutter), and Phase D
(delegation) questions.

---

## Recommendations

1. **Do not conclude from Phase A that Loom has no value.** The
   benchmark couldn't stress any of Loom's value hypotheses.
2. **Do conclude** that Loom's in-session agent-facing tool path is
   bounded-cost at Claude tier. Worst case +48% on this task; not
   catastrophic.
3. **Phase B (state-machine benchmark, ~350 LoC, cross-module) is
   the right next step.** Purpose-built to differentiate Loom and
   non-Loom paths via cross-file state and regression pressure.
4. **Skip Phase A expansion.** N=5 is already enough to see the
   flat pass_rate ceiling; more N won't reveal anything new.

---

## Publication commitment held

Per PROTOCOL.md: data published regardless of direction. Phase A
found no effect of Loom on correctness (ceiling effect) and a clean
cost-overhead gradient. Both are honest results. ROADMAP and product
narrative should treat "Loom as in-session tool on small tasks" as
a bounded-cost overhead, not a performance boost. Claim of
"Loom improves outcomes" requires Phase B+ evidence.

---

## Raw data

All run summaries preserved under `runs-v2/phA_*/`. Per-run
`summary.json` + `events.jsonl` retained for later analysis (e.g.,
Loom tool-call patterns in the +L cells). Batch progress log at
`v2_driver/batch_progress.jsonl`.
