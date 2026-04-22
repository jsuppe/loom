# Experiment: `loom gaps` — small-model capability substitution

**Status:** complete. Results written up in [`FINDINGS.md`](FINDINGS.md).

## Hypothesis under test

> With Loom + sidecar context, a sufficiently small local model can
> execute a sufficiently-atomic, sufficiently-specced coding task at the
> same success rate as a frontier cloud model.

## Scope (final)

Three tasks of escalating difficulty on `services.gaps()`:

| Task | Shape | Grading tests |
|------|-------|----------------|
| 1 | Write from spec (implement from scratch)            | 14 |
| 2 | Extend existing (add 4th gap type: drift)           | 20 |
| 3 | Behavior-preserving refactor (split into helpers)   | 29 |

## Design

- **Models compared:**
  - Local (Ollama, single-turn codegen, no tool access):
    `phi4-mini:latest` (3.8B), `llama3.1:8b` (8.0B),
    `qwen3.5:latest` (9.7B), `gpt-oss:latest` (20.9B),
    `qwen2.5-coder:32b` (32.8B).
  - Cloud (Claude Code subagents, multi-turn with tool access):
    Haiku 4.5 baseline + enhanced, Opus 4.7 baseline + enhanced.
- **Isolation:** subagents ran in their own `git worktree` so diffs
  don't collide. Local benchmarks run in a temp copy, code extracted
  from a fenced ``` python ``` block, spliced into the scratch file.
- **Trials:** 3 per cell for qwen3.5 and llama3.1; 1–2 for the larger
  models (latency was the constraint).
- **Grading:** exit 0 from `pytest test_gaps_*` in the scratch copy.
  Structure-only passes don't count — behavior tests are load-bearing.

## Caveats (what this can and cannot tell us)

- Subagents have tool access (Read/Edit/Bash/etc.) so cloud models could
  explore, not just execute. That makes the cloud cells strictly easier
  — a positive result for cloud small-model is a ceiling, not a floor.
- Subagent token accounting is opaque (the Agent tool doesn't expose
  `usage`). For cost comparison, we rely on published prices.
- Single-file, Python-only, deterministic-correctness-criterion tasks.
  Cross-module, multi-language, and design-judgment tasks are untested.
- See `FINDINGS.md` → "What this doesn't validate" for the full list.

## Files

- `task.md` — task description shared by baseline and enhanced cells.
- `context_bundle.md` — enhanced-only context (reqs + spec + sidecar).
- `test_gaps_task1.py` — Task 1 grading (14 tests).
- `test_gaps_extend.py` — Task 2 grading (20 tests = 14 + 6 drift-specific).
- `test_gaps_refactor.py` — Task 3 grading (29 tests = 20 behavior + 9 structure).
- [`FINDINGS.md`](FINDINGS.md) — headline numbers, results matrix, cost analysis, practical implications.

## Headline (see FINDINGS.md for detail)

| Model                | Params | Task 1 | Task 2 | Task 3 |
|----------------------|-------:|:------:|:------:|:------:|
| phi4-mini            |  3.8B  | 0/3    | 0/3    | —      |
| llama3.1:8b          |  8.0B  | 1/3    | 3/3    | **0/3** behavior-broken |
| **qwen3.5:latest**   |  9.7B  | **3/3**| **3/3**| **3/3** |
| qwen2.5-coder:32b    | 32.8B  | —      | 1/1    | 1/1 (455s) |
| Haiku 4.5 (subagent) | cloud  | 3/3    | —      | —      |
| Opus 4.7 (subagent)  | cloud  | 3/3    | —      | —      |

`qwen3.5:latest` (local, 9.7B) matched Opus 4.7 on every trial — at `temperature=0`, output was byte-deterministic across repeats.

## Reproduction

```bash
# Task 1 (write from scratch)
git checkout e9b06e9       # baseline gaps() checkpoint
python benchmarks/ollama_gaps.py          --model qwen3.5:latest --trials 3

# Task 2 (extend)
git checkout 81aa1ee       # extended gaps() checkpoint
python benchmarks/ollama_gaps_extend.py   --model qwen3.5:latest --trials 3

# Task 3 (refactor)
python benchmarks/ollama_gaps_refactor.py --model qwen3.5:latest --trials 3
```

Results emitted as `benchmarks/ollama_gaps*.json`.
