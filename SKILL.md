---
name: loom
description: Extract requirements from conversations, link to code, detect drift, decompose specs into atomic tasks, and run those tasks on a local small model. Use when making decisions, before modifying code, when a spec is ready for implementation, or to check staleness.
---

# Loom 🧵 — Requirements Traceability & Small-Model Task Execution Skill

**Weaving requirements through code — and driving small-model code execution with them.**

Loom captures decisions as versioned requirements, expands them into specifications, links code back to them with content hashes for drift detection, and (as of the `Task` + `loom decompose` + `loom_exec` layer) decomposes specs into atomic, executor-ready tasks that a local small model can complete against a full context bundle.

## When to use

This skill is always active via AGENTS.md integration. Invoke at these moments:

| Moment                               | Action                                  | Command                          |
|--------------------------------------|-----------------------------------------|----------------------------------|
| Decision made in chat                | Extract requirement (with rationale)    | `loom extract --rationale ...`   |
| Before modifying code (automatic)    | Pre-edit briefing                       | `hooks/loom_pretool.py` (hook)   |
| Manual drift check                   | Inspect a file                          | `loom check <file>`              |
| After implementing                   | Link to reqs or specs                   | `loom link <file> --req/--spec`  |
| Spec ready for implementation        | Decompose into atomic tasks             | `loom decompose SPEC-xxx --apply`|
| Task queue has ready work            | Execute locally                         | `scripts/loom_exec --next`       |
| Heartbeat                            | Surface staleness / drift               | `loom status --json`             |
| Any time                             | Measure hook cost                       | `loom cost`                      |

## Core commands

### Traceability

- **`loom extract [--rationale "why"]`** — Parses `REQUIREMENT: domain | text` from stdin. Emits versioned records; supersedes conflicting prior requirements on request.
- **`loom check <file>`** — Drift check. Exits 2 if any linked req has been superseded.
- **`loom context <file>`** — The briefing the hook injects: linked reqs, specs, drift. JSON-first.
- **`loom link <file> [--req REQ-xxx | --spec SPEC-xxx]`** — Link code, with content-hash capture for later drift.
- **`loom status`**, **`loom query "text"`**, **`loom list`**, **`loom trace <target>`**, **`loom chain <req_id>`**, **`loom coverage`** — read-only views.
- **`loom conflicts --text "..."`** — Detect conflicts. Now LLM-verified (embedding overlap surfaces candidates; an LLM confirms before reporting).

### Specifications & patterns

- **`loom spec REQ-xxx -d <description> [-c <criterion>]... [-s <status>]`** — Detailed HOW for a requirement. `-c` is repeatable for each acceptance criterion.
- **`loom pattern`, `loom patterns`, `loom pattern-apply`** — Shared design standards across requirements.

### Tasks & execution (new)

- **`loom decompose SPEC-xxx [--model provider:name] [--apply] [--out file.yaml]`** — Proposes atomic tasks. Defaults to `anthropic:claude-opus-4-7` if `ANTHROPIC_API_KEY` is set, else `ollama:qwen2.5-coder:32b`. Validates atomicity (≤2 files, ≤80 LoC, single grading criterion) and the dep graph before persisting.
- **`loom task {add|list|show|claim|release|complete|reject|prompt}`** — Atomic-task lifecycle. `loom task list --ready` filters by dependency completion.
- **`scripts/loom_exec [TASK-id | --next | --loop]`** — Drives Ollama end-to-end: claims, assembles context bundle, calls executor, applies code to scratch copy, runs grading test, promotes on pass. Default model from `LOOM_EXECUTOR_MODEL`, falling back to `qwen3.5:latest`.

### Docs & measurement

- **`loom sync`** — Regenerate REQUIREMENTS.md and TEST_SPEC.md from the store.
- **`loom cost`** — Aggregate `hooks/loom_pretool.py` log: p50/p95/p99 latency, bytes injected, overhead (fires with nothing to inject).
- **`loom doctor`** — Full health check (Ollama reachable, store integrity, orphan impls, drift, coverage).

## Validated thesis

> With enough detail in requirements, spec, and context, and small enough units of work, very small models can be effective.

Benchmarks in `benchmarks/ollama_gaps*.py` ran three tasks of increasing difficulty (write, extend, behavior-preserving refactor) against several local and cloud models. `qwen3.5:latest` (9.7B, local) matched Opus 4.7 on 3/3 trials across all three tasks. See [`experiments/gaps/FINDINGS.md`](experiments/gaps/FINDINGS.md).

### What this means operationally

- Decomposition is the expensive step. Run it once per spec with a frontier model.
- Execution is the cheap step. A 9.7B local model produces deterministic, passing output at `temperature=0` when handed the right context bundle.
- Architectural cost split on a 100-task project: frontier-only ≈ $30, hybrid (Opus-decompose + qwen3.5-execute + Opus-review) ≈ $0.60–1.

## AGENTS.md integration

```markdown
## Loom Integration

When a decision is made about how something should work:
→ `echo "REQUIREMENT: domain | text" | loom extract --rationale "why"`

When a spec is ready for implementation:
→ `loom decompose SPEC-xxx --apply` then `scripts/loom_exec --loop`

Before modifying code (automatic via PreToolUse hook):
→ Linked reqs, specs, and drift are injected as a system-reminder.
  Manual equivalent: `loom context <file> --json`.

After implementing a feature:
→ `loom link <file> --req REQ-xxx` (or `--spec SPEC-xxx`)

During heartbeats:
→ `loom status --json` to surface drift
→ `loom cost` to keep an eye on hook overhead
```

## Requirement domains

- **terminology** — What things are called ("posts are called boats")
- **behavior** — How features work ("reset requires 3-second hold")
- **ui** — Visual/UX decisions ("mobile-friendly", "no markdown tables")
- **data** — Data model constraints ("timestamps in UTC")
- **architecture** — Technical decisions ("use PostgreSQL")

## Data storage

```
~/.openclaw/loom/<project>/
├── chroma.sqlite3          # ChromaDB — 6 collections (reqs, specs, patterns,
│                           #   implementations, chat_messages, tasks)
├── .loom-specs.json        # TestSpec JSON store
├── .hook-log.jsonl         # PreToolUse hook activity (read with `loom cost`)
├── .exec-log.jsonl         # loom_exec run log (per-task latency, tokens, pass/fail)
└── PRIVATE.md              # Private requirement IDs (excluded from public docs)
```

## Example flow (three-layer + execution)

```
User: "The app should use half-hour increments for time selection"

Agent:    loom extract --rationale "Matches appointment-booking domain"
          → REQ-042 {domain: data, value: "Time selection uses half-hour increments"}

Agent:    loom spec REQ-042 -d "TimeSelector component: dropdown 00:00..23:30 step=30min; default round down; TZ local" \
                   -c "Dropdown options every 30 minutes" \
                   -c "Values round down to nearest 30min on arbitrary input"
          → SPEC-042a

Agent:    loom decompose SPEC-042a --apply
          → 3 tasks persisted: dataclass, widget, wiring

Agent:    scripts/loom_exec --loop --model qwen3.5:latest
          → T1 passes 4/4 tests in 4.6s
          → T2 passes 6/6 tests in 8.1s
          → T3 passes 3/3 tests in 5.2s
          → All code promoted to the working tree

Later, on Edit to time_selector.py:
  PreToolUse hook → loom context file
  → "Linked to REQ-042, SPEC-042a — no drift"

User: "Actually, let's use 15-minute increments"

Agent:    loom extract → supersedes REQ-042, creates REQ-043
Next heartbeat:
Agent:    loom status --json
          → DRIFT: lib/widgets/time_selector.py linked to superseded REQ-042
```

## Files

- `scripts/loom` — Main CLI (argparse, ~2100 lines)
- `scripts/loom_exec` — Small-model task executor
- `src/store.py` — ChromaDB interface + dataclasses (Requirement, Specification, Pattern, Implementation, Task)
- `src/services.py` — Shared logic between CLI and MCP server (includes `decompose`, `apply_decomposition`, task lifecycle, cost aggregation, conflict verification)
- `src/docs.py` — REQUIREMENTS.md / TEST_SPEC.md generation, traceability matrix
- `src/testspec.py` — JSON-backed TestSpec store
- `src/embedding.py` — Ollama embedding wrapper + LRU cache
- `src/conflict_verify.py` — LLM-verified conflict pass
- `hooks/loom_pretool.py` — PreToolUse hook that injects context on Edit/Write
- `mcp_server/server.py` — MCP server exposing LoomStore as typed tools (Phase A + B shipped)
- `prompts/extract.md`, `prompts/link.md`, `prompts/decompose.md` — prompt templates
- `benchmarks/` — ollama_gaps_*.py runners + results JSON
- `experiments/gaps/` — experiment artifacts + FINDINGS.md
