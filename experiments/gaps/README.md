# Experiment: `loom gaps` — small-model capability substitution

## Hypothesis under test

With Loom + sidecar context, Haiku 4.5 can execute a sufficiently-atomic,
sufficiently-specced coding task at the same success rate as Opus 4.7.

## Scope

TASK-gaps-1 only: add `services.gaps(store, types=None, limit=None)` to
`src/services.py` covering three gap types (missing_criteria,
missing_elaboration, orphan_impl). The follow-up gap types (drift,
unresolved_conflict) and the CLI wiring are future tasks.

## Design

- **4 cells**: {Haiku 4.5, Opus 4.7} × {baseline, enhanced}
- **Baseline**: task prompt only (repo still readable via tools)
- **Enhanced**: task prompt + pre-assembled `context_bundle.md`
- **Isolation**: each subagent runs in its own `git worktree` so diffs don't
  collide.
- **Trials**: start with 1 trial per cell (4 runs), read the tea leaves,
  expand if signal warrants.
- **Grading**: `test_gaps_task1.py` — all assertions must pass for success.

## Caveats (what this can and cannot tell us)

- Subagents have tool access (Read/Edit/Bash/etc.) so Haiku can explore, not
  just execute. That makes this strictly easier for Haiku than a pure
  API-execution test; a positive result here is a ceiling, not the floor.
- Token accounting is opaque — the Agent tool doesn't expose `usage`. We
  can only compare success rate and diff quality, not cost.
- 1 trial per cell is noise. Treat results as signal direction, not proof.

## Files

- `task.md` — task description shared by baseline and enhanced.
- `context_bundle.md` — the enhanced-only context (reqs + spec + sidecar).
- `test_gaps_task1.py` — grading test. Passes iff the task succeeded.

## What counts as success

`pytest experiments/gaps/test_gaps_task1.py` exits 0 in the subagent's
worktree. Stop tokens (`DONE:`, `TASK_REJECT:`, `NEED_CONTEXT:`) are logged
but do not by themselves determine success.
