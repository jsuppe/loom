# Bakeoff V2 — Protocol

**Pre-registered:** 2026-04-24, before the Anthropic driver extension
is written or the harness touches a cloud API.
**Purpose:** V1 found that qwen3.5 using Loom tools in-session
measurably hurts. V2 tests whether the failure was the *model's
capacity to use Loom*, not Loom itself.

This document extends `PROTOCOL.md`. It does NOT amend V1 — V1's
result stands as published in `FINDINGS-bakeoff-v1.md`. V2 adds
new conditions and a new hypothesis. V1's metrics, stop conditions,
stats method, and publication commitment carry over unchanged.

---

## V2 hypothesis

> When both agents run Claude Sonnet 4.6, giving Engineer access to
> Loom tools improves the outcome relative to Sonnet without Loom.
>
> Additionally: the difference between (qwen baseline) and (Sonnet
> baseline) exceeds the difference between (Sonnet baseline) and
> (Sonnet + Loom). I.e., *raw model capability* contributes more
> of any observed improvement than *Loom-as-tools*.

Both pieces of the hypothesis can fail independently. A cleanly
positive V2 requires the first. The second is a test of whether
Loom's marginal value is meaningful above a capability baseline.

## V2 null hypothesis

> Loom tools, given to any model, add no measurable improvement on
> primary metrics over a no-Loom baseline at the same model.

---

## Experimental design

### Conditions

| | PO agent | Engineer agent | Engineer tools |
|---|---|---|---|
| **C1 (V1)** — qwen baseline | qwen3.5 | qwen3.5 | baseline (file I/O + tests) |
| **C2 (V1)** — qwen + Loom | qwen3.5 | qwen3.5 | + Loom tools |
| **C3 (V2)** — Sonnet + Loom | claude-sonnet-4-6 | claude-sonnet-4-6 | + Loom tools |
| **C4 (V2)** — Sonnet baseline | claude-sonnet-4-6 | claude-sonnet-4-6 | baseline (file I/O + tests) |

All four conditions share the same:
- Ground-truth project (TaskQueue library, unchanged from V1).
- Turn mechanic (PO speaks → Engineer responds → tests run).
- Stop conditions (all-pass / 25 iters / 500K tokens / 5-iter
  no-progress).
- Metrics (final_pass_rate, iterations_to_80pct, total_tokens,
  regression_count).
- Hermetic per-run setup (fresh workspace, fresh Loom store for
  treatment conditions, no state leakage).

V1 data is already collected; V2 adds C3 and C4 runs.

### Same-model-on-both-sides rule

Both sides of the conversation use the same model within a run. This
is locked from V1 and preserved here. Comparing e.g. Sonnet-PO +
qwen-Engineer is a different experiment (V3) — NOT this one.

### Sample size

- N = 5 per new condition (C3 and C4) to match V1.
- If any condition shows ambiguous signal (p > 0.10 but effect size
  visible), scale to N = 10 per PROTOCOL.md's pre-committed expansion
  rule. Do not add N iteratively.

### Expected cost

- V1 Loom runs used ~450K tokens median. V2 Sonnet runs are expected
  to use *fewer* tokens per run (better instruction-following, less
  redundant narration), but each Sonnet token costs more.
- Rough estimate at $3/MTok input / $15/MTok output, 70/30 split:
  ~$6-8 per run, ~$60-80 for 10 V2 runs.

---

## Added analyses

### Primary analysis (unchanged method, new comparisons)

Mann-Whitney U + Cliff's delta + Holm-Bonferroni, alpha = 0.10. Four
primary metrics per comparison. The V2-specific comparisons are:

1. **C4 vs C3** — does Loom help Sonnet?
2. **C1 vs C4** — does Sonnet alone explain any gap?
3. **C2 vs C3** — does Loom's value change with model capability?
   (Equivalent: is Loom's "overhead" in V1 an artifact of qwen
   struggling with Loom?)

Each comparison applies Holm-Bonferroni separately across its four
primary metrics. We do not apply a meta-correction across the three
comparisons; each is a distinct pre-registered question.

### Secondary analyses (diagnostic, reported not tested)

- `loom_tool_calls` distribution by condition — did Sonnet use Loom
  differently than qwen? (We expect fewer, better-placed calls.)
- Per-iteration pass_rate curves — faster or slower ramp?
- Duration per iteration — how much of the slowdown in V1 was
  Ollama inference vs Loom CLI overhead? (Subprocess overhead is
  the same in C3; only the Ollama time changes.)

### Model-level confounds we won't correct for

- Sonnet's API latency is bounded by network + rate limits. If
  occasional slow responses occur, they affect wall-clock duration
  but NOT any of the primary metrics.
- Both models are instruction-tuned differently. We accept this as
  baked into the per-model condition. Not confounded within a
  comparison.

---

## Publication commitment

Same as V1. Results go in `FINDINGS-bakeoff-v2.md` regardless of
direction. If V2 shows:

1. **C3 > C4 clearly**: Loom is validated at higher model
   capacity. Product narrative updates: Loom is useful for capable
   models; small-model usage needs the asymmetric `loom_exec`
   architecture.
2. **C3 ≈ C4**: Loom tools don't move the needle even with a
   capable agent in-session. Product reshape: Loom's value is
   across-session, not in-session.
3. **C3 < C4**: Loom hurts even with a capable model on this
   scope. Strong evidence the agent-facing tool surface as
   currently designed is net-negative for small projects.
4. **C1 vs C4**: Sonnet without Loom dramatically outperforms
   qwen without Loom — expected, but the magnitude matters for
   framing cost/benefit trade-offs.

All four outcomes are real results. None are "reshape the experiment."

---

## V3 (explicitly deferred)

The more interesting architectural question is: **does splitting
reasoning (Sonnet) from codegen (qwen) outperform either alone?**

That's V3. Shape:

| | PO | Engineer lead | Codegen |
|---|---|---|---|
| C5 | Sonnet | Sonnet (uses Loom + `loom_exec`) | qwen3.5 |

This tests `experiments/gaps/FINDINGS.md`'s validated architecture
end-to-end in the bakeoff setting. Not included in V2 because:
- Adds a `call_codegen_delegate` tool to the engineer prompt.
- Requires a sub-runner within a turn.
- The right time to build this is *after* C3 tells us whether Loom
  adds value at all when the caller is capable.

If V2's C3 result is clearly positive, V3 is the natural next test.
If V2's C3 result is null or negative, V3 may not be worth running.

---

## Known limitations of V2

All limitations from V1 carry over.  In addition:

- **Cost**: V2 is no longer free. Token budget becomes money.
- **Sonnet rate limits**: may slow throughput; not a metric concern
  but a wall-clock one.
- **Asymmetric cost comparison**: we report `total_tokens` per
  condition. For cost-per-feature, reader can multiply by
  pricing.  Not computing a "dollar per successful run" metric
  since pricing shifts; token counts are durable.
- **Still one project**: V2 doesn't expand scope beyond TaskQueue.
  A V2a variant on a larger project is a separate experiment.

---

## Amendments

### Amendment 1 (2026-04-24) — shift to Claude Code subagents

**Why:** The original V2 design proposed driving two Sonnet agents via
the Anthropic Messages API. But Loom is a *Claude Code skill*. The
actual product is Loom-in-a-Claude-Code-session, not Loom-via-API-
driver. Testing the API-driver path was reproducing V1's shape with a
better model rather than testing the shipped product.

Also: the user has Claude Max (subscription). Paying for separate API
billing on top of Max to run this experiment would be nonsensical
when the subagent path is on Max and more faithful to the product.

**Design change:**

- Runs are orchestrated from the human's Claude Code session (this
  one).  For each iteration, the orchestrator spawns one PO subagent
  and one Engineer subagent using the `Agent` tool.  All subagent
  tokens bill against Max.
- Both subagents are `general-purpose` type.  They have bash + read +
  write + grep access. They use Loom by invoking the loom CLI from
  bash (the same way a Claude Code user with the skill installed
  would).
- Metrics come from the `Agent` tool's usage field:
  `total_tokens`, `tool_uses`, `duration_ms` per subagent call.  No
  character-count proxy needed.
- Workspace isolation: the subagent works in a dedicated tempdir
  containing only `task_queue.py`.  The orchestrator maintains a
  separate tempdir containing `tests/`, copies `task_queue.py` into
  it after each engineer turn, runs pytest, reports results to the
  PO subagent on the next turn.  The engineer subagent never sees
  the tests directory.
- Stop conditions unchanged.

**Conditions (unchanged from pre-amendment design):**

| | PO agent | Engineer agent | Loom tools available |
|---|---|---|---|
| C3 — Sonnet + Loom | Claude Code subagent | Claude Code subagent | yes (via bash `python3 ~/dev/loom/scripts/loom ...`) |
| C4 — Sonnet baseline | Claude Code subagent | Claude Code subagent | no (engineer prompt forbids loom calls) |

**Model spec now**: whatever Claude Code routes subagents to. At the
time of this amendment, that's Claude Sonnet 4.6 (Max tier default).
If the model changes over the course of the run, we document it.

**Sample size caveat:** the orchestrator is this conversation, which
consumes context on every subagent response. Each subagent spawn
may return up to ~5K tokens. N=10 runs × ~10 iterations × 2
subagents = ~200 spawns, roughly 1M tokens of raw response data
streaming back through the orchestrator. We have headroom (1M window)
but V1-style hundreds of runs are infeasible in this shape. If V2
signal is clear at N=5 we accept it; if ambiguous we either scale
to N=10 within one session or split the runs across sessions.

**Anti-leakage rule (carried from V1):** PO subagent never reveals
test source.  Result reporting to PO happens at summary level
(counts + per-test-class pass/fail status).

**Publication commitment carries forward verbatim from V1 protocol.**
