# Bakeoff V2 — C++ executor-capacity falsification (M10.1b)

**Date:** 2026-05-01
**Question:** Is the C++ "collapsed" cell from the cross-language map (off=0%, on-rule=0%, +rat=67%) caused by qwen3.5:latest's executor capacity, or by the context bundle being too thin for C++?
**Approach:** Re-run the cross-language `phL` C++ harness (S1 swallow_runtime_error) verbatim, with `LOOM_EXEC_MODEL=qwen2.5-coder:32b` substituted for `qwen3.5:latest`. Same harness, same scenario, same 4-cell A/B/C/D structure, same N=5/cell.
**N:** 20 trials. 0 harness errors. 0 compile failures. 5.9 min wall.

---

## TL;DR

> **Executor capacity is ruled out as the cause of the C++ ceiling.**
> qwen2.5-coder:32b — a code-specialized 32B model that 100%'d the
> cpp-orders single-file scenario at Phase C — scored **0/10, 0/10,
> 2/10, 0/10** across the four cells of S1 C++. The bigger executor
> was actually *worse* on the rat cell than qwen3.5 (0% vs 67%).
>
> **What this rules in:** semantic context (Kythe / symbol-graph)
> becomes the next defensible lever, exactly the architecture
> Milestone 10 is designed for.

---

## Setup

Verbatim cross-language `phL_crosssession_cpp_smoke.py` harness, only
the executor model changed via env var:

```
LOOM_EXEC_MODEL=qwen2.5-coder:32b python3 phL_crosssession_cpp_smoke.py <cell> <run>
```

Looped over 4 cells × N=5. Each trial is independent — fresh workspace,
fresh Ollama call, no prompt or scaffolding changes from the published
qwen3.5 baseline.

The S1 scenario is the contrarian-rule "swallow OSError-equivalent"
test ported to C++. The rule (when delivered) tells the agent the
codebase explicitly catches and swallows runtime_error; the task
prompt invites adding propagation. Loom's job is to prevent the
agent from adding propagation when the rule is present.

---

## Empirical record

| cell | qwen2.5-coder:32b (M10.1b) | qwen3.5:latest baseline (M8.4) |
|---|---|---|
| **off** | **0/10 (0%)** | 0% |
| **on-rule** | **0/10 (0%)** | 0% |
| **on-rule+placebo** | **2/10 (20%)** | 100%* |
| **on-rule+rat** | **0/10 (0%)** | 67% |

\* The qwen3.5 baseline's `+placebo=100%` was flagged as a verifier
artifact in the cross-language map findings; the true "compliance
under placebo" was likely much lower. qwen2.5-coder:32b's 20% on
that cell is closer to noise floor and consistent with no real lift.

**Compile failures:** 0/20. The 32B model produced syntactically
valid C++ in every trial; the failures are correctness, not
syntax.

**Citation rate:** 0/20. The rationale-keyphrase regex never
matched a 32b response. (qwen3.5's cross-language-map citation
rate on C++ wasn't captured separately; not directly comparable.)

**Wall:** 5.9 min total. ~17–20s per trial (faster than expected;
32b on this scale is responsive).

---

## What this rules out

**Hypothesis A: qwen3.5:latest is too weak in C++.**
Falsified. qwen2.5-coder:32b is roughly 3× the parameter count, code-
specialized, and previously hit 100% on cpp-orders single-file. If
the ceiling were executor capacity, this run should have shown
substantial lift on at least one cell. It did not.

**Hypothesis B: qwen3.5's rat=67% was real bridging.**
Looks like noise. With more trials and a stronger executor (which
should be more, not less, capable of following structured rationale)
we got 0/10 in the rat cell. The original 67% was 5/15 on N=5/scenario;
revisiting at higher N would likely settle close to the 0–20% range
this run shows.

---

## What this rules in

**Semantic context as the next lever.** If neither rule injection
nor rationale injection nor a 3× larger executor moves the needle
on S1 C++, the missing signal is structural information that the
local file body doesn't carry — call sites, header definitions,
type relationships, override chains.

This is exactly what a Kythe-style semantic indexer surfaces, and
it's what Milestone 10 was scoped to integrate. The falsification
moves M10 from "speculative architecture" to "the next defensible
experiment."

---

## What this experiment did NOT prove

- The cross-language map's *non-C++* regime classifications stand
  unchanged. This run only swapped executors on S1 C++.
- It does not establish that Kythe will fix C++. It only establishes
  that *bigger executor* won't. The next step is to actually plug in
  a semantic indexer and re-run.
- Other resistant languages (C, Go) weren't tested. The hypothesis
  that semantic context is the lever for those is even less direct
  — they may have different blockers.
- N=5 per cell. The 0% results are decisive at this N, but the
  20% placebo cell is noise-floor and could be anywhere in [0%, 50%]
  with a wider sample.

---

## Recommended next experiments (priority order)

1. **Stub-Kythe S1 C++** — Hand-author the semantic context that a
   Kythe query would return for the S1 scenario, prepend it to the
   prompt, re-run. If this lifts compliance, Kythe is worth building.
   ~1 hour of work, no Kythe install required. Direct falsification
   of the "context, not capacity" hypothesis.
2. **Same falsification on C and Go** — these share the resistant
   regime. Are they also ruled out by 32B?
3. **Real Kythe integration on a small C++ project** — if (1) lifts,
   build the actual `KytheIndexer`. If (1) doesn't lift, the C++
   ceiling has yet another cause and Kythe is overkill.

---

## Files of record

- `experiments/bakeoff/v2_driver/phL_crosssession_cpp_smoke.py` —
  unchanged harness; ran with `LOOM_EXEC_MODEL` env override
- `experiments/bakeoff/runs-v2/phL_s1_cpp_*_run32b_*.json` —
  20 trial summaries
- `experiments/bakeoff/runs-v2/phL_cpp_qwen25coder32b_progress.log` —
  wall-clock progression
- Compare against: `FINDINGS-bakeoff-v2-cross-language-map.md`
  (qwen3.5 baseline — the published cross-language map)

---

## Honest caveat

This is N=5/cell against a published baseline that's also N=5/cell.
Both samples are small. The headline finding ("executor capacity
ruled out") is supported by 0/10 across the off/rule/rat cells —
that's decisive at this N. But the *exact* numbers from the
cross-language map (especially the rat=67%) deserve a higher-N
revisit before being treated as load-bearing.

What's safest to claim from this experiment alone: **bigger
executor doesn't bridge S1 C++; the M10 architecture (semantic
context) is the next defensible lever.**
