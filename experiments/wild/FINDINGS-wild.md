# Experiment: `loom` in the wild — dogfooding on agentforge

**Date started:** 2026-04-22
**Target repo:** `~/dev/agentforge` (FastAPI + Python backend)
**Spec target:** `POST /projects/{project_id}/conflicts/check` — route + service wiring for existing `RequirementsService.check_conflicts()` dead code.
**Running loom against target from:** `~/dev/loom/scripts/loom` (not installed into agentforge)
**Store:** `~/.openclaw/loom/agentforge/`

## The question

Does the decompose → exec pipeline survive on an unfamiliar repo with a real (if small) spec? What rough edges surface that didn't appear in the controlled `experiments/gaps/` benchmark?

This is intentionally a stress test against cross-module change (router in `main.py` + service wiring) and a codebase the pipeline has never seen.

## Running log

Each friction point is timestamped and numbered in the order hit. No post-hoc reordering — first impressions matter.

### F1 — `-p/--project` flag position is brittle (KNOWN_ISSUES C1)

Tried: `loom doctor -p agentforge --json`
Got: `error: unrecognized arguments: -p agentforge`
Workaround: `loom -p agentforge doctor --json`

Hit within the first command of real use. Already documented in `KNOWN_ISSUES.md` C1, but the fact that a *first-use* command failed on an obvious-looking invocation is a signal: this should be fixed before anyone else touches Loom. Fix is small (duplicate the arg on each subparser).

### F2 — agentforge has no pytest declared

`src/backend/requirements.txt` lists FastAPI/uvicorn/anthropic/chromadb but no `pytest` or `pytest-asyncio`. Loom's task-grading criterion is a pytest path, so we needed to add test deps before we could even run `loom_exec`. On any target project, Loom will have to either:

- add pytest to the target's dev deps (invasive), or
- run pytest from its own venv pointed at the target's source (requires `conftest.py` + `sys.path`), or
- support non-pytest grading criteria.

Currently we're doing option 1 manually. This is a real onboarding gap.

### F3 — `loom doctor` truncates Ollama model list

Output showed 5 models; `curl /api/tags` returned 14. Cosmetic but noticed immediately. Likely capping at some arbitrary limit in `services.doctor()`.

### F4 — agentforge's own architecture has drift Loom could catch

`RequirementsService.check_conflicts()` exists fully implemented but is never called by any endpoint. The conversation path has its own separate LLM-side conflict detection. Agentforge's docstrings reference `REQ-140630c7: Conflict detection with resolution` — this is *exactly* the kind of drift Loom is designed to surface. Ironic + useful for the write-up.

### F5 — Windows cp1252 crash on emoji in `cmd_extract`

`loom extract` pipes stdin to `print("🧵 Loom Extract — Project: ...")`. On
Windows with default cp1252 stdout, this crashes when stdout is a pipe.
Workaround: `PYTHONIOENCODING=utf-8`. Real fix: `sys.stdout.reconfigure(encoding='utf-8')`
at CLI entry, or strip emoji from non-TTY output.

### F6 — SKILL.md/README.md claim `loom spec -t <title>` but CLI has no such flag

Doc drift introduced by yesterday's doc-refresh commit. Actual flags:
`--description/-d`, `--criteria/-c` (repeatable), `--status/-s`, `--source-doc`.
No `--title` or `-t`. The YAML-ish docs I wrote are already wrong.

### F7 — Decomposer doesn't populate `context_files`

Qwen3.5:latest decomposed SPEC-43a53443 in 5.4s and produced a structurally
valid task:

```yaml
files_to_modify: [src/backend/main.py]
test_to_write: tests/test_main.py::TestProjectConflictsCheck
context_reqs:    [REQ-2fc569f0]
context_specs:   [SPEC-43a53443]
context_files:   []     # <-- problem
size_budget_files: 1
size_budget_loc:   60
```

But `context_files: []`. So the assembled executor prompt gives the model
*only* the REQ text + SPEC text + acceptance criteria — nothing about how
FastAPI routes are registered in `main.py`, nothing about the signature of
`RequirementsService.check_conflicts`, nothing about how `requirements_service`
is exposed as a module global. The model would be hallucinating everything.

This is a real gap in `prompts/decompose.md`: the prompt tells the decomposer
to specify `context_files` "optional; source files to inline in full", but
offers no guidance on *when to include them*. For any task that modifies
existing code (vs. writing from scratch), the file being modified and any
service it calls should be auto-included.

**Fix candidate:** in `_build_decompose_prompt`, inject a rule like
"Always include every file in `files_to_modify` as `context_files`, plus
any service/module the task directly calls." Could also auto-augment in
`_validate_task_proposals` — if `files_to_modify` has entries not also in
`context_files`, add them.

### F8 — Task prompt is under-specified for cross-module work

Downstream consequence of F7. `loom task prompt TASK-...` shows the
assembled prompt: zero source code context. A small local model will either
hallucinate something that looks right or return `NEED_CONTEXT`. Both are
correct behaviors for the bad prompt we gave it.

### F9 — `loom_exec` is hard-coded to work on the loom repo itself

**Blocker.** `scripts/loom_exec` has:

```python
SKILL_DIR = Path(__file__).resolve().parent.parent
...
shutil.copytree(SKILL_DIR / "src", scratch / "src")     # loom's src, not target's
shutil.copytree(SKILL_DIR / "tests", scratch / "tests") # loom's tests
...
real_target = SKILL_DIR / task["files_to_modify"][0]    # writes BACK into loom
```

There is no `--target-dir` flag and no `LOOM_TARGET_DIR` env var. `LOOM_PROJECT=agentforge`
changes *which store* we use but not where code is read from or written to.

This is the biggest architectural gap between "the benchmark validated the
pipeline" and "the pipeline can be used on other projects." The benchmark
was implicitly dogfooding Loom on itself; the productization step never
happened.

**Fix:** add a `--target-dir` flag + `LOOM_TARGET_DIR` env (default: cwd).
Resolve `task["files_to_modify"]` and `test_to_write` relative to the target
dir. Keep `SKILL_DIR` for locating loom's own resources (prompts, etc.) only.

Implementing the minimal version now to continue the experiment — logging
this as F9 because a user hitting Loom cold would be stuck here without the
source fix.

## Conclusion

The experiment did not complete an end-to-end run — we stopped at F9, a
hard architectural block. That's not a failure of the experiment; it *is*
the result.

### What we learned

1. **The capability-substitution thesis (FINDINGS.md) is narrower than
   it reads.** Benchmark tasks all ran against files Loom's code already
   knew about because Loom's `loom_exec` is hard-coded to Loom's own repo.
   Moving to an unfamiliar target immediately broke at the runner layer —
   before we could even measure whether qwen3.5 could write a FastAPI route.
2. **Decompose works but context assembly is incomplete.** The decomposer
   produces syntactically valid tasks (right file paths, right size budget,
   right parent refs). It does *not* produce task prompts that would let
   any model succeed, because `context_files` is empty by default. This is
   a prompt-engineering fix, not an architectural one.
3. **First-use friction is high.** Four of the nine frictions (F1, F5, F6,
   F9) would stop any user in the first hour. Two are trivial (encoding,
   doc drift), one is known (arg position), one is architectural. That
   mix is worse than it looks — the trivial ones signal that the project
   hasn't been used by anyone besides its author.
4. **Loom does surface drift on unfamiliar projects, even from a cold
   start.** F4 — agentforge has fully-implemented dead code that its own
   docstrings advertise as "Implements: REQ-xxx". Before we wrote a line
   of new code, Loom's data model highlighted that agentforge's own
   architecture has a gap. Small validation of the *use-case* even as the
   pipeline tooling blocked us.

### Scope of validation

| Claim                                              | Status              |
|----------------------------------------------------|---------------------|
| `qwen3.5:latest` can write/extend/refactor atomic tasks given Loom context | Validated (FINDINGS.md) |
| `loom extract` / `loom spec` / `loom decompose` work against arbitrary projects | Validated (this experiment, up to decompose) |
| `loom_exec` can drive execution on arbitrary projects | **Refuted** — hard-coded to Loom repo |
| Decompose produces executor-ready prompts           | **Refuted** — `context_files` unpopulated |
| First-use UX is acceptable                          | **Refuted** — 4 first-hour frictions |

### Artifacts

- Loom store at `~/.openclaw/loom/agentforge/` contains `REQ-2fc569f0`,
  `SPEC-43a53443`, and `TASK-0696919a309e`. Retained so the next branch
  can replay the same decomposed task once the runner is generalized.
- No code changes were made to the agentforge repo. Nothing to revert.

## Recommended next step

Open a new branch, `claude/exec-generalize`, focused on the minimum
changes to turn the pipeline from "self-dogfooding only" into "runs on
arbitrary Python+pytest projects." Details in the companion plan:
`experiments/wild/PLAN-exec-generalize.md`.

---

## Second run — validation after exec-generalize fixes (2026-04-22)

After T1.1 / T1.2 / T2.1 / T2.2 / T2.3 landed on
`claude/exec-generalize`, the agentforge Loom store was wiped and the
experiment replayed clean:

```
store=~/.openclaw/loom/agentforge  (empty)
extract → REQ-2fc569f0        (no PYTHONIOENCODING needed — T2.1 works)
spec REQ-2fc569f0 …           (-p accepted after subcommand — T2.2 works)
decompose SPEC-aa563093 --target-dir ~/dev/agentforge --apply
    → 1 task (TASK-9d9beb940406)
    → context_files auto-populated: [src/backend/main.py,
                                      src/backend/requirements_service.py*]
    * hallucinated by qwen (real path: src/backend/services/requirements.py).
      The validator adds files_to_modify that exist on disk; it does NOT
      strip nonexistent context_files the model proposed. task_build_prompt
      silently skips nonexistent paths, so the hallucination just doesn't
      inline — cost is a few wasted tokens in the yaml.

loom_exec TASK-9d9beb940406 --target-dir ~/dev/agentforge --model qwen3.5:latest
    prompt: 10688 chars  (vs ~800 in first run — real source inlined)
    model:  2.3s, 230 output tokens
    grading: 0 / 0  → test_fail  → task escalated
    scratch dir discarded; agentforge working tree untouched ✓
```

### New finding surfaced by second run

#### F10 — Nobody creates the grading test file

`test_to_write: tests/test_main.py::TestProjectConflictsCheck` — but no
part of the pipeline creates `tests/test_main.py`. The decomposer
produces a task that names WHERE the test should live; the executor
expects the test to already exist when it runs pytest. Result:
`ERROR: file or directory not found: tests/test_main.py::...` →
pytest reports 0 passed / 0 total → executor classifies as `test_fail`
→ scratch is discarded.

The benchmark runners worked around this by shipping the grading test
as a fixture in `experiments/gaps/test_gaps_*.py` before the task ran.
That move hid the gap: outside the benchmark, nothing creates tests.

**Fix options (pick one in the next branch):**

1. Extend the decomposer prompt to produce a SECOND task per "feature
   task" whose `files_to_modify` is the grading test file. Pros: stays
   atomic, test-first, natural dep ordering (test task → feature task).
   Cons: doubles task count; test task has no grading criterion of its
   own (chicken-and-egg).
2. Make the executor write a **stub test** if `test_to_write` is
   missing. Bad idea: an always-green test is worse than no test.
3. Bundle the grading test into the feature task itself — require
   `files_to_modify` to include BOTH source and test, have the executor
   apply code to both. Cons: breaks the single-output-block convention;
   model has to emit two fenced blocks or one block split by a marker.
4. Move grading-test authorship upstream: when `loom spec` captures a
   spec, optionally also capture the test file skeleton
   (`spec --test tests/test_main.py::TestX`) and write it to disk.
   Then every downstream decomposition has a real file to target.
   Pros: clean separation, matches how humans work. Cons: adds a step;
   changes spec data model slightly.

Option 4 is cleanest and aligns with how people write tests. It also
gives operators an explicit moment to think about acceptance tests
before they reach for execution.

### What we now know works end-to-end on an external target

- Fresh Loom store (no PYTHONIOENCODING needed).
- `extract` → `spec` → `decompose --target-dir --apply` → `loom_exec --target-dir`.
- `-p/--project` works at every argparse position (including nested `task list -p X`).
- Context bundle includes real source (10k chars vs 800 before the fix).
- Scratch isolation holds — target repo never polluted on failure.
- Telemetry logged to `.exec-log.jsonl`.

### What still blocks real use

- F10 (grading test authorship) — next branch after this one.
- F2 (pytest not in target deps by default) — still deferred.
- F3 (doctor truncating models) — still cosmetic.

### Scoreboard

| Friction | Fixed on this branch | Notes |
|---|---|---|
| F1  `-p` position                 | ✅ | T2.2, all 3 positions |
| F2  target lacks pytest           | ⏭ deferred | onboarding story |
| F3  doctor truncates models       | ⏭ deferred | cosmetic |
| F4  agentforge has own drift      | 🗒 noted  | write-up only |
| F5  cp1252 emoji crash            | ✅ | T2.1 + `docs.py` utf-8 write |
| F6  ghost `-t` flag               | ✅ | T2.3 |
| F7  empty context_files           | ✅ | T1.2 prompt + validator |
| F8  thin prompt downstream        | ✅ | closed by F7 fix |
| F9  loom_exec hard-coded          | ✅ | T1.1 --target-dir |
| F10 grading test not created      | ⏭ new | next branch |

