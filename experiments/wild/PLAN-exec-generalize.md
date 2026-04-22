# Plan: generalize the exec pipeline to arbitrary target projects

**Authored:** 2026-04-22
**Motivated by:** `experiments/wild/FINDINGS-wild.md`
**Target branch:** `claude/exec-generalize` (new, from `main` after PR #3 merges)

## Goal

Take Loom from "the benchmark runs on itself" to "Loom can be pointed at
any Python+pytest repo, capture a REQ/SPEC, decompose it, and execute
the resulting tasks against that repo." Nothing beyond that on this branch.

**Non-goals:**
- No new capabilities (no multi-criterion grading, no non-Python support,
  no `loom init`, no dashboard).
- No refactors outside the files needed for the fixes below.
- No speculative design. Each change is small, justified by a specific
  friction in FINDINGS-wild.

## Scope

### Tier 1 — Blockers (must be fixed to claim "usable on other projects")

#### T1.1 — Target-dir support in `loom_exec` (fixes F9)

**Problem:** `scripts/loom_exec` resolves everything against its own
parent directory. Cannot run against another repo.

**Change:**
- Add `--target-dir` CLI flag and `LOOM_TARGET_DIR` env var (env fallback).
- Default when neither is set: the current working directory.
- `SKILL_DIR` retained for locating Loom's own resources (not used for
  file I/O against the task's source files).
- All references to `SKILL_DIR / task["files_to_modify"][0]`,
  `SKILL_DIR / task["test_to_write"]`, and the `copytree` of `src`/`tests`
  re-anchor to `target_dir`.
- If `target_dir` has no `tests/` dir, create it lazily (per-task
  grading-file creation is already supported; just needs the directory).

**Effort:** ~30 lines in `scripts/loom_exec`, one new test in `tests/test_exec.py`
(doesn't exist yet — skip test-harness for MVP, add before merge).

**Success criterion:** `LOOM_TARGET_DIR=~/dev/agentforge loom_exec --dry-run TASK-xxx`
prints a prompt that references agentforge's paths and does not touch the
Loom working tree.

#### T1.2 — Auto-populate `context_files` in decomposition (fixes F7, F8)

**Problem:** `loom decompose` produces tasks with empty `context_files`,
yielding executor prompts too thin to succeed on any real change.

**Change (two-part):**
- **Prompt edit** — Update `prompts/decompose.md` to add an explicit rule:
  > Any file in `files_to_modify` that already exists in the target repo
  > MUST also appear in `context_files` unless the task is a pure create
  > (empty file). When a task calls into an existing module (service,
  > helper, store), include that module as `context_files` too.
- **Validator auto-augmentation** — In `services._validate_task_proposals`,
  if `files_to_modify` has entries not in `context_files` and those files
  exist on disk (relative to target_dir), add them to `context_files`
  automatically. Log a warning so users see the auto-fill.

**Effort:** ~20 lines in `src/services.py`, minor prompt doc edit.

**Success criterion:** Re-decomposing `SPEC-43a53443` against agentforge
produces a task whose prompt includes the full text of
`src/backend/main.py`. qwen3.5:latest can then actually attempt the route.

### Tier 2 — First-use friction (should-fix on the same branch)

#### T2.1 — UTF-8 stdout reconfigure (fixes F5)

**Problem:** Emoji in `cmd_extract` and others crash on Windows cp1252
when stdout is piped.

**Change:** At CLI entry in `scripts/loom`:
```python
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
```
Add to `loom_exec` too. Single-file change per script.

**Effort:** ~10 lines total.

#### T2.2 — `-p/--project` accepted after subcommand (fixes F1, KNOWN_ISSUES C1)

**Problem:** `loom doctor -p myproject` fails because `-p` is only on the
parent parser. Users hit this on the first invocation.

**Change:** Add `--project/-p` to every subparser via a helper, and resolve
to the first non-None of (subparser value, parent value, env, git).

**Effort:** ~15 lines. Refactor `get_project_name` chain slightly.

#### T2.3 — Fix doc drift from yesterday's refresh (fixes F6)

**Problem:** `README.md`, `SKILL.md`, `CLAUDE.md`, and the example in
`CONTRIBUTING.md` show `loom spec -t "title"`. There is no `--title` flag.

**Change:** Replace `-t "..."` references with the actual flag pattern
(`-d "description"`). Verify by running every example command in the docs
and visually inspecting the output. No further mechanical verification.

**Effort:** ~5 minutes of find/replace + manual verification.

### Tier 3 — Deferred to follow-on branches (document, don't fix here)

- **F2** (no pytest in target deps): needs a design conversation. Options
  include (a) auto-add to target, (b) run from Loom's venv with `sys.path`
  injection, (c) support alternative test runners. Capture as roadmap item.
- **F3** (doctor model truncation): cosmetic. File an issue in
  KNOWN_ISSUES.
- **F4** (agentforge's own drift): write-up observation. No code change.

## Validation plan

Once T1.1 + T1.2 + T2.1 + T2.2 + T2.3 are merged:

1. Clone agentforge clean: `rm -rf ~/.openclaw/loom/agentforge/` and re-run
   the wild experiment from scratch.
2. Run `loom extract` / `loom spec` / `loom decompose --apply` against
   SPEC-43a53443.
3. Run `LOOM_TARGET_DIR=~/dev/agentforge loom_exec --next`.
4. Report:
   - End-to-end run time (model call + grading).
   - Whether the output code compiles.
   - Whether the grading test passes (if the task sets one up correctly).
   - If it fails: does the failure surface as `task_reject`, `need_context`,
     or silent bad code?
5. Update `FINDINGS-wild.md` with a "second run" section. This becomes the
   first actual end-to-end measurement on an external target.

## Order of work

```
1. T1.1 (target-dir)          ── unblocks every downstream step
2. T2.3 (doc drift)            ── trivial, close embarrassment fast
3. T2.1 (utf-8)                ── independent, low-risk
4. T2.2 (-p position)          ── independent, touches argparse
5. T1.2 (context_files)        ── requires T1.1 to be mergeable
6. Validation run on agentforge
7. Write up results, merge, close branch
```

Target effort: one focused session. If any step exceeds 45 minutes,
stop and rescope rather than churning.

## Explicit out-of-scope for this branch

- No changes to `src/store.py`, `src/docs.py`, or the MCP server.
- No new CLI verbs.
- No changes to `hooks/loom_pretool.py`.
- No new dataclasses.
- No refactor of `cmd_*` functions beyond what T2.2 forces.
- No changes to `prompts/extract.md` or `prompts/link.md`.
- No attempt to fix agentforge's own drift (F4). That's a future dogfooding
  exercise on a different branch.

## After this branch

If the re-run on agentforge works, the next productization target is
**onboarding**: `loom init` for a new target (creates `.loom-config.json`
with pinned embedding dimensions + test runner + target_dir default), and
`loom discover` for interactive requirement capture. Both are already in
the backlog from earlier conversation notes. Neither is a prereq to this
branch shipping.
