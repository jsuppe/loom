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
├── scripts/loom             # Main CLI entry point (Python, ~1650 lines, argparse-based)
├── src/
│   ├── __init__.py          # Re-exports LoomStore, Requirement, Implementation
│   ├── store.py             # ChromaDB-backed store + dataclasses (Requirement, Specification, Pattern, Implementation)
│   ├── docs.py              # Generators for REQUIREMENTS.md / TEST_SPEC.md, conflict detection
│   └── testspec.py          # TestSpec dataclass + JSON-backed TestSpecStore (.loom-specs.json)
├── tests/
│   ├── test_store.py        # Unit tests for LoomStore (pytest, uses temp dirs)
│   └── test_cli.py          # Subprocess tests for the `loom` CLI
├── prompts/                 # Extraction/linking prompt templates (extract.md, link.md)
├── agents.d/                # Drop-in snippets for AGENTS.md integration
├── docs/                    # REQUIREMENTS.md, TEST_SPEC.md (generated examples)
├── SKILL.md                 # OpenClaw skill manifest + usage guide
├── README.md                # User-facing overview
└── CONTRIBUTING.md
```

### Key modules

- **`src/store.py`** — Defines the core dataclasses and `LoomStore` (ChromaDB wrapper with three+ collections: requirements, implementations, chat_messages, specifications, patterns). All persistence lives here. ID helpers: `generate_impl_id`, `generate_content_hash`.
- **`src/docs.py`** — Pure functions that render the store into Markdown (`generate_requirements_doc`, `generate_test_spec_doc`) and compare embeddings (`check_conflicts`, `analyze_test_impact`). Honors a `PRIVATE.md` allow/deny list and `public_mode`.
- **`src/testspec.py`** — JSON-backed store for test specs (separate from ChromaDB). Data lives at `~/.openclaw/loom/<project>/.loom-specs.json`.
- **`scripts/loom`** — Argparse CLI. Each subcommand is a `cmd_*` function. Inserts `src/` on `sys.path` and imports `store` directly (not as a package). Also handles Ollama embedding calls with retries + LRU cache (`_embedding_cache`, max 500).

## CLI Commands (reference)

Implemented in `scripts/loom` (`cmd_*` functions around these line numbers):

| Command | Function | Purpose |
|---|---|---|
| `extract` | `cmd_extract` (L135) | Parse `REQUIREMENT: domain \| text` from stdin |
| `check` | `cmd_check` (L206) | Detect drift in a file |
| `link` | `cmd_link` (L252) | Link code to requirements (auto or `--req`) |
| `status` | `cmd_status` (L316) | Project overview |
| `query` | `cmd_query` (L353) | Semantic search |
| `list` | `cmd_list` (L378) | List requirements |
| `sync` | `cmd_sync` (L441) | Regenerate REQUIREMENTS.md + TEST_SPEC.md |
| `conflicts` | `cmd_conflicts` (L480) | Detect conflicting/overlapping requirements |
| `supersede` | `cmd_supersede` (L537) | Mark a requirement as superseded |
| `test` / `verify` / `tests` / `test-generate` | `cmd_test_*` | Manage test specs |
| `init-private` | `cmd_init_private` | Create `PRIVATE.md` template |
| `doctor` | `cmd_doctor` (L752) | Health checks |
| `trace` / `chain` | `cmd_trace` / `cmd_chain` | Bidirectional traceability |
| `refine` / `set-status` / `incomplete` | | Elaborate & status-manage requirements |
| `spec` / `specs` / `spec-link` | `cmd_spec_*` | Specification management |
| `pattern` / `patterns` / `pattern-apply` | `cmd_pattern_*` | Shared design patterns |

Project is auto-detected from git repo name via `get_project_name()`, overridable with `-p/--project` or the `LOOM_PROJECT` env var.

## Data Model (src/store.py)

All dataclasses use `to_dict`/`from_dict` for ChromaDB metadata (empty lists become `["TBD"]` because ChromaDB rejects empty lists in metadata).

- **`Requirement`**: `id`, `domain`, `value`, `source_msg_id`, `source_session`, `timestamp`, optional `superseded_at`, `elaboration`, `status` (pending/in_progress/implemented/verified/superseded), `acceptance_criteria`, `test_spec_id`, `conversation_context`. `is_complete()` requires elaboration + ≥1 criterion.
- **`Specification`**: detailed HOW for a `parent_req`. Status: draft/approved/implemented/verified/superseded.
- **`Pattern`**: shared design standard applied across multiple requirements (`applies_to`).
- **`Implementation`**: code chunk linked to requirements/specs with a content hash (used to detect drift).
- **`TestSpec`** (testspec.py): steps/expected/automated flag, lives in JSON, not ChromaDB.

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
# All tests
python -m pytest tests/ -v

# Unit tests only (no subprocess / CLI)
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
  | python3 scripts/loom extract -p test-dev
python3 scripts/loom list -p test-dev
python3 scripts/loom query "deletion" -p test-dev
python3 scripts/loom sync -p test-dev --output ./docs
```

## Conventions & Gotchas

- **Do not edit `docs/REQUIREMENTS.md` or `docs/TEST_SPEC.md` by hand** — they are regenerated by `loom sync` and direct edits are overwritten. To change requirements, use `loom extract` / `loom supersede` / `loom refine`.
- **ChromaDB metadata rules**: empty lists are rejected, so dataclasses substitute `["TBD"]` when serializing. When reading back, treat `["TBD"]` as "unset".
- **Backward compatibility**: `from_dict` methods use `setdefault` for newly added fields — preserve this pattern when adding fields so older stores still load.
- **Shebang in `scripts/loom`** points at a hard-coded venv path (`/home/melchior/.openclaw/skills/loom/.venv/bin/python3.12`). On other machines, invoke via `python3 scripts/loom ...` or update the shebang — do not commit a machine-specific path change.
- **src is not a package when invoked via CLI**: `scripts/loom` does `sys.path.insert(0, SKILL_DIR/"src")` and imports `store` directly. The tests do the same. The `src/__init__.py` package form is used if you `import loom` as a library.
- **Embedding cache**: `_embedding_cache` in `scripts/loom` is an in-process LRU (max 500). Not shared across invocations.
- **Ollama retries**: `get_embedding` retries up to 3 times with backoff. If Ollama is down, it falls back to a deterministic hash-based vector — fine for dev, unsuitable for semantic search.
- **Python style**: PEP 8, type hints where practical, keep `cmd_*` functions focused. No formal linter/formatter is enforced.
- **Do not add files** unless necessary. The project intentionally keeps a flat structure: CLI + 3 src modules + tests.

## Privacy / PRIVATE.md

`PRIVATE.md` in the project dir lists REQ-IDs to exclude from public doc generation (`loom sync --public`). `docs.py` parses it as a set of IDs referenced anywhere in the markdown.

## Agent Integration

When Loom is enabled in an AGENTS.md (see `agents.d/loom-integration.md`):
- Extract a requirement whenever a decision is made.
- Run `loom check <file>` before modifying code.
- Run `loom link <file> --req REQ-xxx` after implementing.
- Run `loom status` during heartbeats to surface drift.

## Git / Branch Conventions

- Feature branches: `feature/<name>` or `claude/<slug>` for AI-assisted work.
- Do not push to `main`/`master` directly; open a PR.
- Do not commit `.venv/`, `__pycache__/`, `.pytest_cache/`, or user data under `~/.openclaw/loom/` (already in `.gitignore`).
