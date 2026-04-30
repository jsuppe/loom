# Loom Integration

**Add this section to your AGENTS.md to enable automatic requirements tracing, spec decomposition, and small-model execution.**

---

## 🧵 Loom — Requirements Traceability & Task Execution

Loom tracks requirements from conversations, links them to code, decomposes specs into atomic tasks, and runs those tasks on a local small model. Use it at these moments:

### When a Decision is Made

When you or the user decide how something should work, extract it with a rationale:

```bash
echo "REQUIREMENT: <domain> | <requirement text>" \
  | loom extract -p <project> --rationale "<why this matters>"
```

Domains: terminology, behavior, ui, data, architecture.

### Before Modifying Code

In projects that install `hooks/loom_pretool.py` as a `PreToolUse` hook,
linked reqs/specs/drift are injected automatically on every Edit/Write —
no action required. Manual equivalent:

```bash
loom context <file> --json
loom check <file>               # exit 2 on drift
```

### After Implementing

Link your implementation to the requirement or spec it satisfies:

```bash
loom link <file> --req REQ-xxx -p <project>
# or
loom link <file> --spec SPEC-xxx -p <project>
```

### When a Spec is Ready for Implementation

Decompose it into atomic, dependency-ordered tasks:

```bash
# Opus by default if ANTHROPIC_API_KEY is set; else Ollama fallback
loom decompose SPEC-xxx --apply
```

Then run the tasks locally:

```bash
loom_exec --loop --model qwen3.5:latest
```

The executor claims each ready task, assembles its context bundle, calls
the model, runs the task's grading test in a scratch copy, and promotes
code to the working tree on pass. Failures set the task to `rejected` or
`escalated` (depending on failure mode) so you can intervene.

### During Heartbeats

Add to your HEARTBEAT.md:
```markdown
### Loom Status (weekly)
- `loom status -p <project>` — drift summary
- `loom coverage -p <project>` — requirements without tests or impls
- `loom stale --older-than 90 --json` — cold + unlinked requirements (consider `loom archive`)
- `loom metrics --since 30 --json` — coverage / drift / activity over the last 30 days
- `loom health-score --json` — single 0-100 number (alert if <50)
- `loom cost` — hook overhead (investigate if overhead_pct > 80)
- Note any drifted implementations or stalled tasks for next work session
```

---

## Quick Reference

| Action                          | Command |
|---------------------------------|---------|
| Extract requirement             | `echo "REQUIREMENT: domain \| text" \| loom extract --rationale "why"` |
| Check file for drift            | `loom check <file>` |
| Pre-edit briefing (hook-style)  | `loom context <file> --json` |
| Link code to requirement        | `loom link <file> --req REQ-xxx` |
| Link code to spec               | `loom link <file> --spec SPEC-xxx` |
| Show all requirements           | `loom list` |
| Search requirements             | `loom query "search text"` |
| Status overview                 | `loom status` |
| Decompose spec into tasks       | `loom decompose SPEC-xxx --apply` |
| List ready tasks                | `loom task list --ready` |
| Run next task (local model)     | `loom_exec --next` |
| Run task queue until empty      | `loom_exec --loop` |
| Show assembled executor prompt  | `loom task prompt TASK-xxx` |
| Hook latency/overhead           | `loom cost` |
| Effectiveness rollup            | `loom metrics --json` |
| 0-100 score for CI              | `loom health-score --json` |
| Cold/unlinked requirements      | `loom stale --older-than 90 --json` |
| Retire a requirement            | `loom archive REQ-xxx` |
| Health checks                   | `loom doctor` |

## Install

```bash
pip install loom-cli       # registers `loom` and `loom_exec` on PATH
```

(Or, from a clone: `pip install -e .`. The legacy `scripts/loom` and
`scripts/loom_exec` shims also work without installing.)

## Environment Variables

| Variable                    | Purpose                                                     |
|-----------------------------|-------------------------------------------------------------|
| `LOOM_PROJECT`              | Default project name (overrides git-repo autodetect)        |
| `LOOM_DECOMPOSER_MODEL`     | Default decomposer (`anthropic:...` or `ollama:...`)        |
| `LOOM_EXECUTOR_MODEL`       | Default executor model for `loom_exec` (e.g. `qwen3.5:latest`) |
| `LOOM_EMBEDDING_PROVIDER`   | `ollama` (default) / `openai` / `hash`                      |
| `LOOM_HOOK_BLOCK_ON_DRIFT`  | Set to `1` to hard-block Edit/Write on drift via the hook   |
| `LOOM_HOOK_LOG`             | Override hook log path (default `<project>/.hook-log.jsonl`) |
| `ANTHROPIC_API_KEY`         | Enables Opus-driven decomposition                           |
| `OPENAI_API_KEY`            | Required when `LOOM_EMBEDDING_PROVIDER=openai`              |
