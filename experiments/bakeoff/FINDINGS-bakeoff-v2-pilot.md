# Bakeoff V2 — Pilot findings (N=1 per condition)

**Date:** 2026-04-24
**Protocol:** `PROTOCOL-v2.md` + Amendment 1 (Claude Code subagent-
driven, committed `604cddd`)
**Model:** Claude Code `general-purpose` subagent (Claude Sonnet
4.6 via Max subscription)
**Ground truth:** Same TaskQueue library from V1.
**N:** 1 per condition. **Pilot — single data point is anecdote,
not evidence.** Intended to validate the subagent-driven harness
and read the direction.

---

## Headline

**The direction reverses from V1 completely.**

| | V1 (qwen+qwen) | V2-pilot (Sonnet+Sonnet) |
|---|---|---|
| Baseline pass_rate median | 0.53 | (this run) 1.00 |
| Loom pass_rate median | 0.33 | (this run) 1.00 |
| Baseline tokens | 30K | 224K |
| Loom tokens | 490K (**16× more**) | **137K (39% LESS)** |
| Baseline iters to green | some never reached | **5** |
| Loom iters to green | none reached | **3** |

In V1, qwen-with-Loom burned 16× more tokens than qwen-baseline for
worse outcomes. In V2 pilot, Sonnet-with-Loom used **39% fewer
tokens than Sonnet-baseline** AND reached green in **3 iterations
vs 5**.

Both V2 runs hit 15/15 perfect. Loom was a clear win on both axes.

---

## V2 pilot data (N=1 each)

| run | cond | pass/total | iters | tokens | stop_reason |
|---|---|---:|---:|---:|---|
| c4_sonnet_baseline_001 | baseline | 15/15 | 5 | 223,657 | all_tests_pass |
| c3_sonnet_loom_001 | loom | 15/15 | 3 | 137,226 | all_tests_pass |

### Per-iteration pass-rate curves

- Baseline: 1 → 5 → 8 → 10 → 15
- Loom:     1 → 5 → **15**

Loom condition hit REQ-3 through REQ-6 in a single iteration after
the PO batched the remaining specs. The engineer used Loom to
track 6 REQs cleanly and emitted all methods at once.

### Loom usage in the Loom run

6 requirements captured (one per REQ). 6 link operations. Zero
redundant extracts. **Contrast with V1's qwen engineer which made
22+ redundant `loom_extract` calls and 14+ `loom_list` calls to
re-check its own work.**

Token count per iteration for Loom run was only marginally higher
than baseline (~24K vs ~23K per iter for Sonnet), but Loom finished
in 3 iters vs 5 — fewer iterations dominates total cost.

---

## What the pilot says

Three claims. All anecdotal at N=1 but the direction is stark:

1. **Loom's value depends on the caller's reasoning capacity.**
   qwen3.5 at 9.7B can't use Loom judiciously mid-conversation —
   it loops, re-extracts, burns tokens narrating. Sonnet makes one
   clean call per concept and moves on.

2. **Loom may actually accelerate capable agents on small projects.**
   V1 framed the question as "does Loom help?" and found no. V2
   reframes it as "does Loom help WHEN THE CALLER CAN USE IT WELL?"
   and the pilot says yes, measurably — ~40% token savings, ~40%
   iteration reduction. Effect size is large if it holds.

3. **The subagent-driven harness works.** Each iteration = 2
   subagent spawns + a bash test invocation + orchestrator glue.
   Clean data from the Agent tool's `total_tokens` / `tool_uses` /
   `duration_ms` fields. Workspace isolation held — engineer never
   saw tests/. Loom runs in a hermetic store.

---

## Hard caveats

- **N=1 per condition.** Two runs total. Variance unknown.
  Effect could be random noise on the right side of the V1→V2
  direction flip.
- **Orchestrator context cost is the scaling bottleneck.**
  Each iter costs the orchestrator (this Claude Code session)
  ~40-50K tokens of context. Full N=5 per condition requires
  ~2M orchestrator tokens — exceeds my 1M context window in a
  single session. Scaling needs a different approach: a Python
  driver that uses `claude -p` headless mode, or splitting runs
  across fresh sessions.
- **Only one project.** TaskQueue is small (~200 LoC, 15 tests).
  Larger projects may favor Loom more (context pressure matters)
  or less (overhead accumulates).
- **No statistics applied.** Two data points cannot produce a
  meaningful p-value or effect size. This is direction-reading,
  not hypothesis testing.

---

## What this doesn't overturn

V1's finding still stands on its own terms: **qwen3.5 using
Loom tools in-session on this project burns 16× more tokens than
baseline for worse outcomes.** The V2 pilot doesn't falsify that;
it shows the conclusion is condition-specific, not universal. V1
measured the wrong model class for Loom-as-in-session-tools and
correctly concluded that that combination underperforms. V2 pilot
is the first evidence that the combination works when the model
class matches Loom's implicit design assumption.

---

## What we should do next

1. **Scale V2 to N=5 per condition** via a different orchestration
   path (headless `claude -p` from a Python driver), so we have
   statistical evidence not just anecdote.
2. **Test on a larger project** — TaskQueue is small enough that
   working memory covers it. Loom's value should grow with project
   size.
3. **Reshape the product narrative.** If Loom's value scales with
   caller capacity, the product story becomes *"a structured memory
   layer for capable agents"*, not *"a productivity boost for all
   agents."* That's a narrower but more defensible claim.
4. **Investigate V3 architecture** (Sonnet orchestrates Loom,
   delegates codegen to qwen via `loom_exec`). The V2 pilot
   suggests this might be the cost-efficient sweet spot.

---

## Publication commitment held

Findings published regardless of direction. V1 said Loom hurts
(for qwen). V2 pilot says Loom helps (for Sonnet). Both reported
honestly. ROADMAP to be updated so users know the
condition-dependence.
