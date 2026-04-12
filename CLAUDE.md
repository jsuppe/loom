# CLAUDE.md

Guidance for Claude Code (and other AI assistants) when working in this repository.

## Project Overview

**Loom** is a semantic requirements traceability system for AI-assisted development. It extracts requirements from conversations, embeds them as vectors in ChromaDB, links them to code, detects drift/conflicts, and generates living documentation.

It is designed to run as either:
- an **OpenClaw skill** installed at `~/.openclaw/skills/loom/`, or
- a **standalone CLI** via `scripts/loom`.

The source of truth is the **Loom store** (ChromaDB at `~/.openclaw/loom/<project>/`), not the generated markdown files.

## Repository Layout

```
loom/
├── scripts/loom             # Main CLI entry point (Python, ~1700 lines, argparse-based)
├── src/
│   ├── __init__.py          # Re-exports LoomStore, Requirement, Implementation
│   ├── store.py             # ChromaDB-backed store + dataclasses (Requirement, Specification, Pattern, Implementation)
│   ├── docs.py              # Generators for REQUIREMENTS.md / TEST_SPEC.md, conflict detection, traceability matrix
│   └── testspec.py          # TestSpec dataclass + JSON-backed TestSpecStore (.loom-specs.json)
├── tests/
│   ├── test_store.py        # Unit tests for LoomStore + doc generation (pytest, uses temp dirs)
│   └── test_cli.py          # Subprocess tests for the `loom` CLI
├── prompts/                 # Extraction/linking prompt templates (extract.md, link.md)
├── agents.d/                # Drop-in snippets for AGENTS.md integration
├── docs/                    # REQUIREMENTS.md, TEST_SPEC.md (generated examples)
├── SKILL.md                 # OpenClaw skill manifest + usage guide
├── README.md                # User-facing overview
└── CONTRIBUTING.md
```

### Key modules

- **`src/store.py`** — Defines the core dataclasses and `LoomStore` (ChromaDB wrapper with five collections: requirements, implementations, chat_messages, specifications, patterns). All persistence lives here. ID helpers: `generate_impl_id`, `generate_content_hash`.
- **`src/docs.py`** — Functions that render the store into Markdown (`generate_requirements_doc`, `generate_test_spec_doc`) and compare embeddings (`check_conflicts`, `analyze_test_impact`). Includes implementation links and a traceability matrix in generated docs. Honors a `PRIVATE.md` allow/deny list and `public_mode`.
- **`src/testspec.py`** — JSON-backed store for test specs (separate from ChromaDB). Data lives at `~/.openclaw/loom/<project>/.loom-specs.json`.
- **`scripts/loom`** — Argparse CLI. Each subcommand is a `cmd_*` function. Inserts `src/` on `sys.path` and imports `store` directly (not as a package). Also handles Ollama embedding calls with retries + LRU cache (`_embedding_cache`, max 500).

## CLI Commands (reference)

| Command | Purpose | `--json` |
|---|---|---|
| `extract` | Parse `REQUIREMENT: domain \| text` from stdin. Accepts `--rationale` | — |
| `check <file>` | Detect drift in a file | Yes |
| `link <file>` | Link code to requirements (auto or `--req`) | — |
| `status` | Project overview with drift summary | Yes |
| `query <text>` | Semantic search | Yes |
| `list` | List requirements | Yes |
| `sync` | Regenerate REQUIREMENTS.md + TEST_SPEC.md | — |
| `conflicts --text` | Detect conflicting/overlapping requirements | Yes |
| `supersede <id>` | Mark a requirement as superseded | — |
| `test` / `verify` / `tests` / `test-generate` | Manage test specs | `tests`: Yes |
| `init-private` | Create `PRIVATE.md` template | — |
| `doctor` | Health checks (Ollama, store, orphans, drift, coverage) | Yes |
| `trace <target>` | Bidirectional traceability (req→files or file→reqs) | Yes |
| `chain <req_id>` | Full traceability chain (req→patterns→specs→impls→tests) | Yes |
| `refine` / `set-status` / `incomplete` | Elaborate & status-manage requirements | — |
| `spec` / `specs` / `spec-link` | Specification management | `specs`: Yes |
| `pattern` / `patterns` / `pattern-apply` | Shared design patterns | `patterns`: Yes |

### Exit codes

- **0** — Success
- **1** — Error (bad input, missing resource, store failure)
- **2** — Warning condition detected (drift found, conflicts found)

Project is auto-detected from git repo name via `get_project_name()`, overridable with `-p/--project` or the `LOOM_PROJECT` env var.

## Data Model (src/store.py)

All dataclasses use `to_dict`/`from_dict` for ChromaDB metadata (empty lists become `["TBD"]` because ChromaDB rejects empty lists in metadata).

- **`Requirement`**: `id`, `domain`, `value`, `source_msg_id`, `source_session`, `timestamp`, optional `superseded_at`, `elaboration`, `rationale` (why this requirement exists), `status` (pending/in_progress/implemented/verified/superseded), `acceptance_criteria`, `test_spec_id`, `conversation_context`. `is_complete()` requires elaboration + ≥1 criterion.
- **`Specification`**: detailed HOW for a `parent_req`. Status: draft/approved/implemented/verified/superseded.
- **`Pattern`**: shared design standard applied across multiple requirements (`applies_to`).
- **`Implementation`**: code chunk linked to requirements/specs with a content hash (used to detect drift).
- **`TestSpec`** (testspec.py): steps/expected/automated flag, lives in JSON, not ChromaDB.

## Generated Documentation

`loom sync` produces two markdown files. Both now include implementation links:

- **REQUIREMENTS.md** — Each requirement shows its status, linked implementation files (with line ranges), and drift warnings. Ends with a **Traceability Matrix** table mapping every requirement to its files and test spec.
- **TEST_SPEC.md** — Each test spec shows "Covered code" (linked files). Requirements without test specs show "Uncovered code" to highlight what needs testing.

## Development Workflow

### Environment setup

```bash
python3 -m venv .venv
.venv/bin/pip install chromadb pytest
ollama pull nomic-embed-text    # required for real embeddings
ollama serve                    # must be running on localhost:11434
```

Without Ollama the CLI falls back to a hash-based pseudo-embedding (see `get_embedding` in `scripts/loom`).

### Running tests

```bash
# All tests (14 tests: 9 store + 5 doc generation)
python -m pytest tests/test_store.py -v

# CLI tests spawn `scripts/loom` as a subprocess and need the installed skill
python -m pytest tests/test_cli.py -v
```

Notes:
- `tests/test_store.py` uses a temp directory fixture (`temp_store`) — self-contained.
- `tests/test_cli.py` shells out to `~/.openclaw/skills/loom/scripts/loom`. It expects the skill to be installed at that path and writes to real `~/.openclaw/loom/test_cli_project/` (cleaned up in fixtures).
- Sample embedding in tests is `[0.1] * 768` to match `nomic-embed-text` dimensions.

### Manual end-to-end check

```bash
echo "REQUIREMENT: behavior | Users must confirm before deleting" \
  | python3 scripts/loom extract -p test-dev --rationale "Prevent accidental data loss"
python3 scripts/loom list -p test-dev --json
python3 scripts/loom query "deletion" -p test-dev --json
python3 scripts/loom sync -p test-dev --output ./docs
python3 scripts/loom doctor -p test-dev --json
```

## Conventions & Gotchas

- **Do not edit `docs/REQUIREMENTS.md` or `docs/TEST_SPEC.md` by hand** — they are regenerated by `loom sync` and direct edits are overwritten. To change requirements, use `loom extract` / `loom supersede` / `loom refine`.
- **ChromaDB metadata rules**: empty lists are rejected, so dataclasses substitute `["TBD"]` when serializing. When reading back, treat `["TBD"]` as "unset".
- **Backward compatibility**: `from_dict` methods use `setdefault` for newly added fields — preserve this pattern when adding fields so older stores still load.
- **Shebang in `scripts/loom`** uses `#!/usr/bin/env python3` for portability. Invoke via `python3 scripts/loom ...` if your PATH doesn't include it.
- **src is not a package when invoked via CLI**: `scripts/loom` does `sys.path.insert(0, SKILL_DIR/"src")` and imports `store` directly. The tests do the same. The `src/__init__.py` package form is used if you `import loom` as a library.
- **Embedding cache**: `_embedding_cache` in `scripts/loom` is an in-process LRU (max 500). Not shared across invocations.
- **Ollama retries**: `get_embedding` retries up to 3 times with backoff. If Ollama is down, it falls back to a deterministic hash-based vector — fine for dev, unsuitable for semantic search.
- **`--json` flag**: Most read-only commands support `--json` / `-j` for machine-readable output. Use this when invoking from hooks or agents to avoid parsing emoji-decorated text.
- **Python style**: PEP 8, type hints where practical, keep `cmd_*` functions focused. No formal linter/formatter is enforced.
- **Do not add files** unless necessary. The project intentionally keeps a flat structure: CLI + 3 src modules + tests.

## Privacy / PRIVATE.md

`PRIVATE.md` in the project dir lists REQ-IDs to exclude from public doc generation (`loom sync --public`). `docs.py` parses it as a set of IDs referenced anywhere in the markdown.

## Agent Integration

When Loom is enabled in an AGENTS.md (see `agents.d/loom-integration.md`):
- Extract a requirement whenever a decision is made (include `--rationale` for the why).
- Run `loom check <file> --json` before modifying code.
- Run `loom link <file> --req REQ-xxx` after implementing.
- Run `loom status --json` during heartbeats to surface drift.

## Git / Branch Conventions

- Feature branches: `feature/<name>` or `claude/<slug>` for AI-assisted work.
- Do not push to `main`/`master` directly; open a PR.
- Do not commit `.venv/`, `__pycache__/`, `.pytest_cache/`, or user data under `~/.openclaw/loom/` (already in `.gitignore`).
