# Loom Roadmap

## Milestone 0: Small-model execution pipeline (DONE)

Capability-substitution thesis validated empirically. See
[`experiments/gaps/FINDINGS.md`](experiments/gaps/FINDINGS.md).

- [x] **0.1 Hook instrumentation** — `hooks/loom_pretool.py` injects linked
      reqs/specs/drift on Edit/Write as a system-reminder; logs per-fire
      `{latency_ms, bytes, reqs, specs, drift, fired, skipped}` to
      `<project>/.hook-log.jsonl`.
- [x] **0.2 `loom cost`** — Aggregates the hook log. Reports p50/p95/p99
      latency, total injected bytes, overhead percentage, skipped-vs-fired.
- [x] **0.3 LLM-verified conflict detection** — `src/conflict_verify.py`
      adds an LLM confirmation pass over embedding-overlap candidates so
      `loom conflicts` reports real conflicts only.
- [x] **0.4 Task entity** — `Task` dataclass + `tasks` ChromaDB collection +
      `add_task`/`list_tasks`/`list_ready_tasks`/`update_task`/
      `set_task_status`/`search_tasks` store methods. Lifecycle: pending →
      claimed → complete | rejected | escalated. Atomicity budget (≤2 files,
      ≤80 LoC default) and dep DAG enforced at validation time.
- [x] **0.5 `loom task` CLI** — add/list/show/claim/release/complete/reject/
      prompt verbs. `loom task prompt` emits the assembled executor prompt
      for a task (context bundle included).
- [x] **0.6 `loom decompose`** — Propose atomic-task decomposition for a
      spec. Dispatches to Anthropic or Ollama by `provider:model` prefix.
      Defaults: `anthropic:claude-opus-4-7` if `ANTHROPIC_API_KEY` set, else
      `ollama:qwen2.5-coder:32b`. Validates atomicity + dep graph before
      persisting. `--apply` writes to the store.
- [x] **0.7 `scripts/loom_exec`** — End-to-end runner: claim next ready
      task, assemble context bundle, call Ollama, extract code, apply to
      scratch copy, run grading test, promote on pass. Logs to
      `<project>/.exec-log.jsonl`. Default model `LOOM_EXECUTOR_MODEL`
      falling back to `qwen3.5:latest`.
- [x] **0.8 Capability validation** — `benchmarks/ollama_gaps*.py` runners
      across three task shapes (write, extend, behavior-preserving
      refactor). `qwen3.5:latest` (9.7B, local) matched Opus 4.7 on every
      trial; findings documented in `experiments/gaps/FINDINGS.md`.

**Headline:** `qwen3.5:latest` local execution at `temperature=0` is
byte-deterministic and matches frontier cloud models on atomic Loom-specced
tasks at effectively zero marginal cost.

**Carry-overs (not blockers):**
- Cross-module tasks are untested — benchmark covers single-file mods only.
- Ambiguous specs (require design judgment) are untested.
- Non-Python codebases untested.
- `loom_exec` currently supports a single grading-test-runs-pytest
  criterion; multi-criteria grading (lint + type + test) is future work.

## Milestone 0.5: Onboarding & generalization (DONE)

Turn the pipeline from "dogfoods on Loom" into "works on any Python+pytest
repo." Validated against agentforge in
[`experiments/wild/FINDINGS-wild.md`](experiments/wild/FINDINGS-wild.md).

- [x] **0.5a `loom_exec --target-dir` / `LOOM_TARGET_DIR`** — Runner no
      longer hard-coded to Loom's own repo. Separates "store name" from
      "source root."
- [x] **0.5b `loom decompose --target-dir`** — Validator auto-adds
      `files_to_modify` entries that exist on disk to `context_files`,
      so the executor sees real source instead of hallucinating.
- [x] **0.5c UTF-8 stdout** — Emoji no longer crash the CLI on Windows
      cp1252 when output is piped.
- [x] **0.5d `-p` at every position** — `loom doctor -p foo` works (was
      KNOWN_ISSUES C1).
- [x] **0.5e `loom init`** — Writes `.loom-config.json` at the target
      repo root, runs health-check (Ollama, models, pytest, tests/),
      prints next-steps. Everything downstream picks up defaults from
      the config so `loom extract` / `loom decompose` / `loom_exec`
      don't need flags once init has run.
- [x] **0.5f Config precedence** — CLI flag > env > config > built-in
      default. `src/config.py` owns the resolution.

- [x] **0.5g Templates (Interpretation B)** — `loom init --template
      <name>` scaffolds files from a template. Template registry:
      `~/.loom/templates/<name>/` wins over `<loom-repo>/templates/
      <name>/`. One starter ships (`python-minimal`) as a reference;
      users are expected to fork it. Variables declared in
      `manifest.yaml`, prompted interactively or passed via `--var
      KEY=VALUE`. `{{ var }}` substitution in file contents and
      file/directory names. Shipped starter validated end-to-end: scaffold
      → `pip install -e '.[dev]'` → `pytest` passes.
- [x] **0.5h₂ Per-runtime starter templates** — Three new starters
      ship (`dart-minimal`, `flutter-minimal`, `typescript-minimal`) to
      pair with each shipped runner. Template manifests gain a
      `config_overrides` section — `services.init()` merges those into
      `.loom-config.json`, so `loom init --template flutter-minimal`
      produces a Flutter-shaped config without manual editing. The
      runner-dep health-check also dispatches by runner (pytest in
      requirements.txt / pubspec.yaml for Dart / package.json for TS)
      so non-Python projects stop getting spurious "pytest not
      declared" warnings. All four starters validated end-to-end: fresh
      scaffold → native deps install → smoke test passes.
- [x] **0.5h Multi-runtime `loom_exec`** — Pluggable test-runner
      registry (`src/runners.py`) replaces the hardcoded pytest call.
      Shipped runners: `pytest` (Python, append-mode), `dart_test` /
      `flutter_test` (Dart, replace-mode), `vitest` (TypeScript,
      replace-mode). Each runner owns its command shape, result parser,
      code-block fence, apply mode, and failing-placeholder skeleton.
      `.loom-config.json`'s `test_runner` selects which. Downstream
      (`loom_exec`, `task_build_prompt`, `loom spec --test`, decompose
      prompt) all dispatch through the registry. Validated end-to-end
      against real `dart test` and `npx vitest run` output. Authoring
      a new runner = a single `Runner(...)` entry; no other code changes.

## Milestone 1: CLI Foundations (DONE)

Make Loom reliable for tool use by AI agents.

- [x] **1.1 Portable shebang** — `#!/usr/bin/env python3`
- [x] **1.2 `--json` output** — 11 commands now support `--json` / `-j`
- [x] **1.3 Exit codes** — 0=success, 1=error, 2=drift/conflicts
- [x] **1.4 `rationale` field** — `--rationale` on `extract`, included in docs and JSON
- [x] **1.5 Implementation links in docs** — REQUIREMENTS.md shows linked files, drift warnings, traceability matrix; TEST_SPEC.md shows covered/uncovered code

## Milestone 2: Requirement Hygiene

Surface staleness without automatic deletion. Requirements are decisions — Loom should help users review and decide, never silently delete.

- [ ] **2.1 `last_referenced` timestamp** — Track when a requirement was last touched by `query`, `check`, `link`, `trace`, or `chain`. `setdefault` to `None` for backward compat.
- [ ] **2.2 `loom stale` command** — List requirements sorted by staleness. Flags: `--older-than 90d`, `--unlinked`. Read-only, `--json` from day one.
- [ ] **2.3 `loom archive` command** — New `archived` status (distinct from `superseded`). Excluded from `list`, `query`, `conflicts` by default. Recoverable via `loom set-status REQ-xxx pending`.
- [ ] **2.4 `loom review` (optional)** — Interactive walkthrough of stale requirements: keep / archive / supersede / skip. Non-interactive equivalent: `loom stale --json` + explicit commands.

Design principle: **surface, don't delete.**
1. `last_referenced` tracks activity passively (zero effort)
2. `loom stale` shows what's cold (read-only, safe)
3. User/agent decides: keep, archive, or supersede (explicit action)

## Milestone 3: Pluggable Embeddings

Remove hard dependency on local Ollama.

- [ ] **3.1 Provider interface** — Abstract `get_embedding()` to support `ollama` (default), `openai` (via `OPENAI_API_KEY`), and `hash` (deterministic fallback). Selection via `LOOM_EMBEDDING_PROVIDER` env var or `--embedding-provider` flag. Config stored in `.loom-config.json` per project.
- [ ] **3.2 Dimension validation** — Record embedding dimensions on first use. Reject mismatched dimensions with a clear error on subsequent calls.

## Milestone 4: Claude Code Integration (PARTIAL)

First-class tool integration with Claude Code sessions.

- [x] **4.1 Hooks** — `.claude/settings.json` with SessionStart (doctor + status), PostToolUse on Edit/Write (drift check), PostToolUse on Bash git commit (sync docs). Plus `hooks/loom_pretool.py` (Milestone 0.1) with JSONL telemetry.
- [x] **4.2 MCP server (Phase A + B)** — Thin Python MCP server wrapping `LoomStore` as typed MCP tools. Phase A (read) and Phase B (write) tools are shipped. Only `init-private` remains CLI-only. See `mcp_server/README.md`.

### 4.2 MCP server — design

**Location:** `mcp_server/server.py` (thin) + `mcp_server/tools.py` (handlers). Imports `src/store.py` directly — same `sys.path` trick as `scripts/loom`. Do not duplicate business logic.

**Phase A — read tools (ship first):**
| Tool | Wraps | Notes |
|---|---|---|
| `loom_query` | `LoomStore.query` | `text`, `project?`, `limit?` |
| `loom_list` | `LoomStore.list_requirements` | `project?`, `status?` |
| `loom_status` | `cmd_status` logic | drift summary |
| `loom_trace` | `cmd_trace` | bidirectional |
| `loom_chain` | `cmd_chain` | full req→specs→impls→tests |
| `loom_doctor` | `cmd_doctor` | health checks |
| `loom_coverage` | `cmd_coverage` | gap analysis |

**Phase B — write tools:**
| Tool | Wraps | Confirmation? |
|---|---|---|
| `loom_extract` | `cmd_extract` | ask (creates requirement) |
| `loom_link` | `cmd_link` | ask (mutates store) |
| `loom_check` | `cmd_check` | no (read-only) |
| `loom_spec_create` | `cmd_spec` | ask |
| `loom_supersede` | `cmd_supersede` | ask (destructive-ish) |
| `loom_sync` | `cmd_sync` | no (regenerates docs) |

**Resources:**
- `loom://requirements/{project}` — live REQUIREMENTS.md
- `loom://testspec/{project}` — live TEST_SPEC.md
- `loom://drift/{project}` — current drift report (JSON)

**Project scoping:** every tool takes optional `project`. Default from `LOOM_PROJECT` env var, then falls back to `get_project_name()` from the MCP server's cwd (usually the project dir the user launched Claude Code from).

**State wins:** per-session embedding cache survives across tool calls (vs. cold cache on every CLI subprocess).

**Registration:** ship a sample `.mcp.json` in the repo root so users can enable Loom in their Claude Code session with one file.

**Non-goals for 4.2:**
- Don't reimplement the CLI. The MCP server and CLI must call the same `LoomStore` methods.
- Don't replace hooks. Hooks fire on deterministic events (Edit/Write, SessionStart); MCP tools are model-initiated. They're complementary.

## Milestone 5: Metrics & Effectiveness Measurement

Track whether Loom is actually helping. Without measurement, you can't tell if the token cost is justified.

### 5.1 Event log

Append-only JSON log at `~/.openclaw/loom/<project>/.loom-events.json`. Each entry:

```json
{"event": "drift_detected", "file": "src/auth.py", "req_id": "REQ-042", "timestamp": "..."}
{"event": "conflict_found", "new_text": "...", "existing_id": "REQ-015", "timestamp": "..."}
{"event": "requirement_extracted", "req_id": "REQ-043", "domain": "behavior", "timestamp": "..."}
{"event": "implementation_linked", "file": "src/auth.py", "req_id": "REQ-043", "timestamp": "..."}
{"event": "check_clean", "file": "src/auth.py", "timestamp": "..."}
```

Events logged by existing commands — `check`, `conflicts`, `extract`, `link` — with a one-line append per action. No new dependencies.

### 5.2 `loom metrics` command

Reads the event log and reports effectiveness:

```
loom metrics -p myproject
loom metrics -p myproject --json
loom metrics -p myproject --since 30d
```

Output:
- **Requirements:** total extracted, active, archived, superseded
- **Coverage:** requirements with implementations / total, requirements with test specs / total
- **Drift:** times drift was detected, files affected, avg time from supersede to detection
- **Conflicts:** conflicts caught before implementation
- **Activity:** requirements extracted per week, links created per week
- **Staleness:** requirements with no references in 30/60/90 days

### 5.3 `loom health-score`

Single 0-100 score combining:
- Implementation coverage (% of reqs with linked code)
- Test spec coverage (% of reqs with test specs)
- Freshness (% of reqs referenced in last 90 days)
- Drift ratio (% of implementations not drifted)

Useful for CI gates or status dashboards:

```bash
SCORE=$(loom health-score -p myproject --json | jq '.score')
[ "$SCORE" -lt 50 ] && echo "Requirements health is degrading"
```

## Dependency Graph

```
Milestone 1 (DONE)
       │
       ├──────────────────────────┐
       ▼                          ▼
Milestone 2 (Hygiene)    Milestone 3 (Embeddings)
       │                          │
       ▼                          ▼
Milestone 4 (Integration) ◄──────┘
       │
       ▼
Milestone 5 (Metrics)
  5.1 Event log (needs extract/check/link/conflicts to log events)
  5.2 loom metrics (needs event log)
  5.3 loom health-score (needs metrics + coverage data)
```

Milestones 2 and 3 are independent and can run in parallel. Milestone 5 depends on Milestone 1 (JSON output) and benefits from 2 (staleness data feeds metrics).
