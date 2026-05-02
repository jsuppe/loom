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

Or, for a decision that builds on a prior one:

```bash
echo "REQUIREMENT: behavior | rate-limit refunds at 10/min" \
  | loom extract -p <project> --derives-from REQ-payment-rate-limit
```

`--derives-from` is repeatable and links the new requirement to existing
decisions as a structured citation chain. Reqs without rationale or links
land at status `rationale_needed` (visible debt — see `loom needs-rationale`).

Find related prior decisions before deciding:

```bash
loom related "rate-limit refunds at 10/min"
```

Domains: terminology, behavior, ui, data, architecture.

### Automatic Intake (M11.5)

In projects that install `hooks/loom_intake.py` as a `UserPromptSubmit`
hook, every chat message is classified for requirement-shape and routed
through the intake pipeline:

- **auto-link**: top-1 candidate score ≥ 0.80, no guardrails tripped →
  persists with `rationale_links=[REQ-X]` and confirms via system-reminder
- **propose**: candidates above 0.66 but below auto-link threshold →
  surfaces top-2 in the agent's context for the user to confirm
- **captured_with_rationale**: no candidates, but a verbatim rationale
  was extracted → persists with prose rationale
- **rationale_needed**: no candidates, no rationale → persists nothing,
  asks the agent to ask the user *why*

Validated by M11.5 P0 pilot: precision 95.2%, recall 100%, p50 latency
454 ms on 40 hand-labeled chat utterances. See `hooks/README.md` for
install + tuning. Three guardrails (softener detection, domain whitelist,
daily budget) keep auto-capture from polluting the store.

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
| Extract derived from prior      | `echo "REQUIREMENT: ..." \| loom extract --derives-from REQ-xxx` |
| Find related prior decisions    | `loom related "free text"` |
| List rationale debt             | `loom needs-rationale` |
| Manual intake on a chat message | `loom intake --text "..."` |
| Intake stats                    | `loom intake-stats` |
| Check file for drift            | `loom check <file>` |
| Pre-edit briefing (hook-style)  | `loom context <file> --json` |
| Link code to requirement        | `loom link <file> --req REQ-xxx` |
| Link code by symbol (LSP)       | `loom link <file> --symbol Class.method --req REQ-xxx` |
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
| Indexer pipeline health         | `loom indexer-doctor` |

## Install

```bash
pip install loom-cli       # registers `loom` and `loom_exec` on PATH
```

(Or, from a clone: `pip install -e .`. The legacy `scripts/loom` and
`scripts/loom_exec` shims also work without installing.)

## Environment Variables

| Variable                       | Purpose                                                     |
|--------------------------------|-------------------------------------------------------------|
| `LOOM_PROJECT`                 | Default project name (overrides git-repo autodetect)        |
| `LOOM_DECOMPOSER_MODEL`        | Default decomposer (`anthropic:...` or `ollama:...`)        |
| `LOOM_EXECUTOR_MODEL`          | Default executor model for `loom_exec` (e.g. `qwen3.5:latest`) |
| `LOOM_OLLAMA_KEEP_ALIVE`       | Hold the executor model resident (default `30m`; `-1` for benchmarks) |
| `LOOM_EMBEDDING_PROVIDER`      | `ollama` (default) / `openai` / `hash`                      |
| `LOOM_HOOK_BLOCK_ON_DRIFT`     | Set to `1` to hard-block Edit/Write on drift via the hook   |
| `LOOM_HOOK_LOG`                | Override pretool hook log path (default `<project>/.hook-log.jsonl`) |
| `LOOM_INTAKE_MODEL`            | Override classifier model for the intake hook               |
| `LOOM_INTAKE_DAILY_BUDGET`     | Cap on auto-link captures per day (default `30`)            |
| `LOOM_INTAKE_DEBUG`            | Set to `1` to log intake-hook activity to stderr            |
| `ANTHROPIC_API_KEY`            | Enables Opus-driven decomposition + Haiku-classified intake |
| `OPENAI_API_KEY`               | Required when `LOOM_EMBEDDING_PROVIDER=openai`              |
