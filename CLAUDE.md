# CLAUDE.md

Guidance for Claude Code (and other AI assistants) when working in this repository.

## Project Overview

**Loom** is a semantic requirements traceability system for AI-assisted development. It extracts requirements from conversations, embeds them as vectors in a local SQLite store, links them to code, detects drift/conflicts, and generates living documentation.

Loom installs from PyPI as `loom-cli` and registers two console scripts (`loom`, `loom_exec`). The package is `loom` (`from loom.store import LoomStore`). The legacy `scripts/loom` and `scripts/loom_exec` shims still exist for users running directly out of a clone, but they only `sys.path`-bootstrap the package and delegate to `loom.cli:main` / `loom.exec_cli:main`.

The source of truth is the **Loom store** (SQLite at `~/.openclaw/loom/<project>/loom.db`), not the generated markdown files.

## Repository Layout

```
loom/
├── pyproject.toml              # Build config + console scripts (loom, loom_exec)
├── src/loom/                   # The package
│   ├── __init__.py             # Public API: LoomStore, Requirement, Implementation, …
│   ├── cli.py                  # Main CLI entry point (~2.3k lines, argparse-based)
│   ├── exec_cli.py             # Small-model task executor (~560 lines)
│   ├── store.py                # SQLite-backed LoomStore + dataclasses
│   ├── services.py             # Shared logic layer between CLI and MCP server
│   ├── embedding.py            # Pluggable provider dispatch (ollama / openai / hash)
│   ├── docs.py                 # REQUIREMENTS.md / TEST_SPEC.md generators
│   ├── testspec.py             # JSON-backed TestSpec store (.loom-specs.json)
│   ├── config.py               # .loom-config.json reader + precedence resolver
│   ├── runners.py              # Pluggable test runner registry (pytest, vitest, …)
│   ├── conflict_verify.py      # LLM-verified conflict detection
│   ├── templates.py            # `loom init --template` scaffolding
│   ├── prompts/                # In-package: decompose/extract/link prompt templates
│   └── templates/              # In-package: starter templates per runtime
├── scripts/loom, loom_exec     # Thin shims that delegate to the package (clone-mode)
├── hooks/loom_pretool.py       # PreToolUse hook for Claude Code (lives outside the package on purpose)
├── hooks/loom_intake.py        # UserPromptSubmit hook (M11.5) — same outside-package rationale
├── mcp_server/                 # MCP server wrapping LoomStore as typed tools
├── agents.d/                   # Drop-in snippets for AGENTS.md integration
├── tests/                      # pytest suite (~410 tests, 0 require Ollama in default mode)
├── docs/                       # GETTING_STARTED.md, WORKED_EXAMPLE.md, generated REQUIREMENTS.md/TEST_SPEC.md
├── benchmarks/                 # capability + retrieval microbenchmarks
├── experiments/                # bake-off harnesses + findings docs (~830 trials)
├── ROADMAP.md                  # Milestones (M0–M9 mostly DONE, plus M2/M3/M5/M9 for v1)
├── README.md                   # User-facing overview
├── CLAUDE.md                   # This file
├── SKILL.md                    # OpenClaw skill manifest
├── KNOWN_ISSUES.md
└── CONTRIBUTING.md
```

### Key modules

- **`src/loom/store.py`** — Core dataclasses and `LoomStore` (SQLite-backed; one `loom.db` per project with six entity tables and a small `_loom_meta` key/value table that pins `embedding_dim` on first write). ID helpers: `generate_impl_id`, `generate_content_hash`. Raises `EmbeddingDimensionMismatch` when a write conflicts with the pinned dimension (M3.2).
- **`src/loom/services.py`** — Shared logic layer between `loom.cli`, `loom.exec_cli`, and `mcp_server/server.py`. Each function returns plain, JSON-serializable data — no printing, no `sys.exit`, no argparse. The CLI's `cmd_*` functions call these and add pretty printing + exit codes. Service functions raise `LookupError` for "target not found" and `ValueError` for invalid input; callers decide how to surface. Write services like `link` return `{linked: bool, ..., warnings: [...]}` rather than raising on partial failure. Touchpoints (`query`, `check`, `link`, `trace`, `chain`) stamp `Requirement.last_referenced` (M2.1) and append a typed event to `<data_dir>/.loom-events.jsonl` via `_record_event` (M5.1) so `services.metrics` and `services.health_score` can aggregate effectiveness data.
- **`src/loom/docs.py`** — Markdown generators (`generate_requirements_doc`, `generate_test_spec_doc`) + embedding-overlap helpers (`check_conflicts`, `analyze_test_impact`). Honors `PRIVATE.md` allow/deny list and `public_mode`.
- **`src/loom/testspec.py`** — JSON-backed store for test specs (separate from SQLite). Lives at `~/.openclaw/loom/<project>/.loom-specs.json`.
- **`src/loom/embedding.py`** — Pluggable provider dispatcher: `ollama` (default, `nomic-embed-text` 768d), `openai` (`text-embedding-3-small` 1536d via urllib, no SDK), `hash` (deterministic). Selection precedence: explicit arg → `LOOM_EMBEDDING_PROVIDER` env → `.loom-config.json::embedding_provider` → `ollama`. Cache key includes `(provider, model)` so providers don't collide. Process-local LRU (max 500). Single source of truth — do not duplicate this logic.
- **`src/loom/config.py`** — `.loom-config.json` reader + the `resolve()` helper that implements precedence: CLI flag > env > config > built-in default.
- **`src/loom/runners.py`** — Pluggable test-runner registry. Shipped: `pytest`, `dart_test`, `flutter_test`, `vitest`. Each runner owns its command shape, result parser, code-block fence, and failing-placeholder skeleton.
- **`src/loom/conflict_verify.py`** — LLM-verified conflict detection. Embedding overlap surfaces candidates; an LLM pass confirms before `loom conflicts` reports.
- **`src/loom/cli.py`** — Argparse CLI. Each subcommand is a `cmd_*` function. Entry point is `main()`. Registered as `loom` console script via pyproject.
- **`src/loom/exec_cli.py`** — Small-model task executor. Claims the next ready `Task`, assembles its context bundle, calls Ollama, extracts the code block, applies to a scratch copy, runs the grading test, and promotes on pass. Logs to `<project>/.exec-log.jsonl`. Default model from `LOOM_EXECUTOR_MODEL`, falling back to `qwen3.5:latest`. Registered as `loom_exec` console script.
- **`hooks/loom_pretool.py`** — `PreToolUse` hook. Runs `loom context <file>` on Edit/Write/MultiEdit/NotebookEdit, injects linked reqs + rationale + drift as a system-reminder, and appends `{ts, tool, file, latency_ms, bytes, reqs, specs, drift, fired, skipped}` to `<project>/.hook-log.jsonl`. `LOOM_HOOK_BLOCK_ON_DRIFT=1` turns drift into a hard block. Lives outside the package because it's a script users register in their `.claude/settings.json`, not Python they import.
- **`hooks/loom_intake.py`** — `UserPromptSubmit` hook (M11.5). Classifies the user's chat message as requirement-shape, runs `services.find_related_requirements`, and routes to one of six branches (auto_link / propose / captured_with_rationale / rationale_needed / duplicate / noop). Persists captures via `services.extract` with `rationale_links` when applicable; injects a `<system-reminder>` describing the action so the agent knows what was just captured. Logs every fire to `<project>/.intake-log.jsonl` for `loom intake-stats`. Three guardrails (softener detection, domain whitelist, daily auto-link budget) keep auto-capture from polluting the store. Backed by the testable core in `src/loom/intake.py`.
- **`src/loom/intake.py`** — testable core for the intake hook. Six-branch decision tree, classifier prompt, JSONL log helpers. Importable as `from loom import intake`.
- **`src/loom/indexers.py` + `src/loom/indexers_js.py`** — pluggable `SemanticIndexer` registry (M10.1) plus the LSP-backed `JsIndexer` for JavaScript/TypeScript via `typescript-language-server` (M10.3c). Powers the `## Semantic context` block in `loom_exec` prompts and the structural-drift channel in `services.check`.

## CLI Commands (reference)

| Command | Purpose | `--json` |
|---|---|---|
| `extract` | Parse `REQUIREMENT: domain \| text` from stdin. Accepts `--rationale`, `--derives-from REQ-xxx` (M11.1) | — |
| `related <text>` | Find existing requirements semantically related to the query (M11.1) | Yes |
| `needs-rationale` | List requirements captured without rationale or linkage (M11.1) | Yes |
| `intake [--text "..."]` | Manually run the intake hook on a chat message (M11.5 P1) | Yes |
| `intake-stats` | Aggregate intake-hook activity from `.intake-log.jsonl` (M11.5 P3) | Yes |
| `indexer-doctor` | Health check for the semantic-indexer pipeline (M10.5) | Yes |
| `check <file>` | Multi-channel drift detection (content/structural/superseded; M10.4) | Yes |
| `link <file>` | Link code to requirements (auto, `--req`, or `--symbol`) | — |
| `status` | Project overview with drift summary | Yes |
| `query <text>` | Semantic search | Yes |
| `list` | List requirements | Yes |
| `sync` | Regenerate REQUIREMENTS.md + TEST_SPEC.md | — |
| `conflicts --text` | Detect conflicting/overlapping requirements | Yes |
| `supersede <id>` | Mark a requirement as superseded | — |
| `archive <id>` | Mark a requirement as archived (recoverable; hidden from list/query) | — |
| `stale` | Rank reqs by `last_referenced` (`--older-than N`, `--unlinked`) | Yes |
| `test` / `verify` / `tests` / `test-generate` | Manage test specs | `tests`: Yes |
| `init` / `init-private` | Onboard a target repo (`init`) / create `PRIVATE.md` | — |
| `doctor` | Health checks (Ollama, store, orphans, drift, coverage) | Yes |
| `trace <target>` | Bidirectional traceability (req→files or file→reqs) | Yes |
| `chain <req_id>` | Full traceability chain (req→patterns→specs→impls→tests) | Yes |
| `refine` / `set-status` / `incomplete` | Elaborate & status-manage requirements | — |
| `spec` / `specs` / `spec-link` | Specification management | `specs`: Yes |
| `pattern` / `patterns` / `pattern-apply` | Shared design patterns | `patterns`: Yes |
| `context <file>` | Pre-edit briefing (used by the PreToolUse hook) | Yes |
| `cost` | Summarize hook log (p50/p95/p99 latency, overhead %) | Yes |
| `metrics` | Effectiveness rollup (coverage / drift / conflicts / activity / staleness; `--since N`) | Yes |
| `health-score` | Single 0-100 score for CI gating | Yes |
| `task {add,list,show,claim,release,complete,reject,prompt}` | Atomic-task lifecycle | `list`/`show`: Yes |
| `decompose SPEC-xxx [--apply]` | Propose atomic-task decomposition via Opus or Ollama | — |

The top-level CLI also accepts `--embedding-provider {ollama,openai,hash}` (M3.1).

Separate entry point: **`loom_exec`** (or `python -m loom.exec_cli`) drives the task queue against a local model (`--next`, `--loop`, `--dry-run`, `--model`).

### Exit codes

- **0** — Success
- **1** — Error (bad input, missing resource, store failure)
- **2** — Warning condition detected (drift found, conflicts found)

Project is auto-detected from git repo name via `get_project_name()`, overridable with `-p/--project` or the `LOOM_PROJECT` env var.

## Data Model (src/loom/store.py)

All dataclasses use `to_dict`/`from_dict` for serialization. Empty lists become `["TBD"]` (legacy convention from the prior ChromaDB backend, kept on the SQLite backend so old serialized data round-trips cleanly; on read, treat `["TBD"]` as "unset").

- **`Requirement`**: `id`, `domain`, `value`, `source_msg_id`, `source_session`, `timestamp`, optional `superseded_at`, `elaboration`, `rationale` (why this requirement exists, surfaced through `services.context()` and the PreToolUse hook), `status` (pending/in_progress/implemented/verified/superseded/**archived**), `acceptance_criteria`, `test_spec_id`, `conversation_context`, `last_referenced` (M2.1: ISO timestamp stamped by every read/link operation; consumed by `loom stale` and `loom health-score`). `is_complete()` requires elaboration + ≥1 criterion.
- **`Specification`**: detailed HOW for a `parent_req`. Status: draft/approved/implemented/verified/superseded.
- **`Pattern`**: shared design standard applied across multiple requirements (`applies_to`).
- **`Implementation`**: code chunk linked to requirements/specs with a content hash (used to detect drift).
- **`Task`**: atomic work item. Fields: `title`, `files_to_modify`, `test_to_write`, `context_reqs`/`specs`/`patterns`/`sidecars`/`files`, `size_budget_files`, `size_budget_loc`, `depends_on`, `status` (pending/claimed/complete/rejected/escalated), `claimed_by`, `claimed_at`, `completed_at`, `rejected_reason`, `escalated_reason`, `created_by`, `parent_spec`. Store methods: `add_task`, `get_task`, `list_tasks`, `list_ready_tasks` (dep-complete filter), `update_task`, `set_task_status`, `search_tasks`.
- **`TestSpec`** (testspec.py): steps/expected/automated flag, lives in JSON, not the SQLite store.

Six entity tables in `loom.db`: `requirements`, `specifications`, `patterns`, `implementations`, `chat_messages`, `tasks`. Each has columns `id` (PK), `embedding` (BLOB), `metadata` (JSON TEXT), `document` (TEXT). Brute-force cosine similarity for nearest-neighbor search.

A seventh small table, **`_loom_meta`** (key/value), holds per-store invariants — currently `embedding_dim`, pinned on the first vector write (M3.2). Mismatched writes raise `EmbeddingDimensionMismatch`.

### Per-project files at `~/.openclaw/loom/<project>/`

| file | written by | consumed by |
|---|---|---|
| `loom.db` | `LoomStore` | everything |
| `.loom-specs.json` | `TestSpecStore` | `loom test` / `verify` / `tests` |
| `.loom-events.jsonl` | `services._record_event` (extract / link / check) | `loom metrics`, `loom health-score` (M5) |
| `.hook-log.jsonl` | `hooks/loom_pretool.py` | `loom cost` |
| `.intake-log.jsonl` | `hooks/loom_intake.py` (via `services.intake._record`) | `loom intake-stats` (M11.5) |
| `.exec-log.jsonl` | `loom_exec` | bake-off harnesses, manual inspection |
| `PRIVATE.md` | user | `loom sync --public` |

## Generated Documentation

`loom sync` produces two markdown files. Both now include implementation links:

- **REQUIREMENTS.md** — Each requirement shows its status, linked implementation files (with line ranges), and drift warnings. Ends with a **Traceability Matrix** table mapping every requirement to its files and test spec.
- **TEST_SPEC.md** — Each test spec shows "Covered code" (linked files). Requirements without test specs show "Uncovered code" to highlight what needs testing.

## Development Workflow

### Environment setup

```bash
python3 -m venv .venv
. .venv/bin/activate            # or .venv/Scripts/activate on Windows
pip install -e '.[dev]'         # editable install + pytest
ollama pull nomic-embed-text    # required for real embeddings (default provider)
ollama pull qwen3.5:latest      # recommended local executor for loom_exec
ollama serve                    # must be running on localhost:11434
```

`pip install -e .` registers `loom` and `loom_exec` as console scripts on PATH inside the venv. The `[dev]` extra adds `pytest` + `pytest-xdist`.

Without Ollama the default `ollama` provider falls back to a hash-based pseudo-embedding with a printed warning (see `get_embedding` in `src/loom/embedding.py`). For deterministic offline tests, set `LOOM_EMBEDDING_PROVIDER=hash` — that path doesn't print a warning.

### Running tests

```bash
# Default suite (313 tests; CLI subprocess tests are skipped via pyproject)
pytest

# Or full path explicitly
python -m pytest tests/

# A single file
pytest tests/test_store.py -v
```

Notes:
- The pytest config in `pyproject.toml` ignores `tests/test_cli.py` by default — those tests shell out to `scripts/loom` and have Windows-shebang issues that are irrelevant to behavior coverage.
- Test fixtures use temp directories; nothing touches `~/.openclaw/loom/` for the unit/service tests.
- Sample embedding in tests is `[0.1] * 768` to match the default `nomic-embed-text` dimension.

### Manual end-to-end check

```bash
echo "REQUIREMENT: behavior | Users must confirm before deleting" \
  | loom extract -p test-dev --rationale "Prevent accidental data loss"
loom list -p test-dev --json
loom query "deletion" -p test-dev --json
loom sync -p test-dev --output ./docs
loom doctor -p test-dev --json
loom metrics -p test-dev --json   # check the event log got written
loom health-score -p test-dev --json
```

If `loom` isn't on PATH (e.g. running from a clone without an install), substitute `python3 scripts/loom ...` — the shim still works.

## Conventions & Gotchas

- **Do not edit `docs/REQUIREMENTS.md` or `docs/TEST_SPEC.md` by hand** — they are regenerated by `loom sync` and direct edits are overwritten. To change requirements, use `loom extract` / `loom supersede` / `loom refine` / `loom archive`.
- **`["TBD"]` empty-list sentinel**: legacy serialization convention (from the prior ChromaDB backend that rejected empty-list metadata). Kept on the SQLite backend so older stores round-trip cleanly. On read, treat `["TBD"]` as "unset".
- **Backward compatibility**: `from_dict` methods use `setdefault` for newly added fields — preserve this pattern when adding fields so older stores still load. New fields added in v1: `Requirement.last_referenced` (M2.1).
- **Loom is a real Python package now (M9).** Internal modules use relative imports (`from .store import LoomStore`); external callers use absolute (`from loom.store import LoomStore`). `scripts/loom` and `scripts/loom_exec` are thin shims that `sys.path`-bootstrap then call `loom.cli:main` / `loom.exec_cli:main`. Do not reintroduce `from store import …` patterns anywhere.
- **Embedding cache**: `_embedding_cache` in `src/loom/embedding.py` is an in-process LRU (max 500), keyed by `(provider, model, text-sha)` so two providers can't collide. Not shared across CLI invocations; persistent within a long-lived process (e.g. the MCP server).
- **Embedding fallback semantics differ by provider**: the default `ollama` provider falls back to a deterministic hash on outage (with a warning). `openai` and explicit `hash` raise / return cleanly — they don't silently degrade. This is intentional: a misconfigured OpenAI key should surface, not produce useless vectors.
- **Dimension pinning**: a store records its `embedding_dim` on the first vector write. Switching `LOOM_EMBEDDING_PROVIDER` after that point raises `EmbeddingDimensionMismatch` with actionable advice.
- **`--json` flag**: Most read-only commands support `--json` / `-j`. Use it when invoking from hooks/agents to avoid parsing emoji-decorated text.
- **Touchpoint instrumentation**: any service that surfaces a requirement to the agent (`query`, `check`, `link`, `trace`, `chain`) MUST call `store.touch_requirement(req_id)` (M2.1). Any service that performs a user-meaningful operation MUST call `services._record_event(store, event_type, …)` (M5.1). Skipping those breaks the staleness/metrics signals.
- **Python style**: PEP 8, type hints where practical, keep `cmd_*` functions focused on argparse + pretty printing. Business logic belongs in `services.py`. No formal linter/formatter is enforced.
- **Don't add files unless necessary.** The package structure is intentionally flat under `src/loom/`. New entity types or major features get one file each; small helpers belong with their callers.

## Privacy / PRIVATE.md

`PRIVATE.md` in the project dir lists REQ-IDs to exclude from public doc generation (`loom sync --public`). `docs.py` parses it as a set of IDs referenced anywhere in the markdown.

## Agent Integration

When Loom is enabled in an AGENTS.md (see `agents.d/loom-integration.md`):
- Extract a requirement whenever a decision is made (include `--rationale` for the why — the PreToolUse hook surfaces rationale to future agents).
- Run `loom check <file> --json` before modifying code.
- Run `loom link <file> --req REQ-xxx` after implementing.
- Run `loom status --json` during heartbeats to surface drift.
- For health visibility in CI, gate on `loom health-score --json | jq .score`.

## Git / Branch Conventions

- Feature branches: `feature/<name>` or `claude/<slug>` for AI-assisted work.
- Do not push to `main`/`master` directly; open a PR.
- Do not commit `.venv/`, `__pycache__/`, `.pytest_cache/`, or user data under `~/.openclaw/loom/` (already in `.gitignore`).
