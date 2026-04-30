# Contributing to Loom

Thanks for your interest in contributing to Loom! 🧵

## Getting Started

```bash
# Fork and clone the repo, then:
python3 -m venv .venv
. .venv/bin/activate          # or .venv/Scripts/activate on Windows
pip install -e '.[dev]'       # editable install + pytest

# Ollama (default embedding provider + recommended executor)
ollama pull nomic-embed-text
ollama pull qwen3.5:latest    # if you want to exercise loom_exec
```

Optional env:
- `ANTHROPIC_API_KEY` — exercises the Opus decomposer path.
- `OPENAI_API_KEY` — exercises the OpenAI embedding provider.

`pip install -e .` registers `loom` and `loom_exec` on PATH inside the venv. The `[dev]` extra adds `pytest` + `pytest-xdist`. SQLite is stdlib (no separate install).

## Repository shape

```
loom/
├── pyproject.toml             # Build config + console scripts
├── src/loom/                  # The package
│   ├── cli.py                 # Argparse CLI — one cmd_* per subcommand
│   ├── exec_cli.py            # Small-model task executor
│   ├── store.py               # SQLite LoomStore + dataclasses + _loom_meta table
│   ├── services.py            # Shared CLI/MCP logic — plain Python, JSON-able returns
│   ├── docs.py                # REQUIREMENTS.md / TEST_SPEC.md generation, traceability matrix
│   ├── testspec.py            # JSON-backed TestSpec store
│   ├── embedding.py           # Pluggable provider dispatch (ollama / openai / hash)
│   ├── conflict_verify.py     # LLM-verified conflict detection
│   ├── config.py, runners.py, templates.py
│   ├── prompts/               # In-package prompt templates
│   └── templates/             # In-package starter templates
├── scripts/loom, loom_exec    # Thin shims for repo-clone use (sys.path → loom.cli/exec_cli)
├── hooks/loom_pretool.py      # PreToolUse hook
├── mcp_server/                # Typed MCP tools over LoomStore
├── benchmarks/                # Benchmark runners + result JSON
├── experiments/               # Bake-off harnesses + findings docs
├── tests/                     # pytest suites (~313 tests)
└── docs/                      # Generated REQUIREMENTS.md/TEST_SPEC.md + GETTING_STARTED, WORKED_EXAMPLE
```

External callers (tests, mcp_server, scripts, benchmarks, experiments) use absolute imports: `from loom.store import LoomStore`. Internal modules use relative imports: `from .store import LoomStore`. Don't reintroduce bare `from store import …` patterns.

## Development

### Running tests

```bash
pytest                          # default suite, 313 tests
pytest tests/test_store.py -v   # one file
pytest -k "metrics" -v          # by keyword
```

`pyproject.toml` configures pytest to ignore `tests/test_cli.py` by default (those tests shell out to the legacy script and fail on Windows-shebang issues). Test fixtures use temp directories — nothing touches `~/.openclaw/loom/`. Sample embedding in tests is `[0.1] * 768` to match the default `nomic-embed-text` dimension.

For deterministic offline testing without Ollama, set `LOOM_EMBEDDING_PROVIDER=hash` — that path produces stable vectors without warnings.

### Manual end-to-end check

```bash
# One-time: onboard a fresh target dir
mkdir /tmp/loom-test-target && cd /tmp/loom-test-target
loom init -p test-dev
#  → writes .loom-config.json + creates tests/ + health-check

# Capture a requirement (no -p needed after init — picked up from config)
echo "REQUIREMENT: behavior | Users must confirm before deleting" \
  | loom extract --rationale "Prevent accidental data loss"

# Add a spec
loom spec REQ-xxx \
  -d "Confirmation modal: show modal before delete; require Type-to-confirm for > 10 items" \
  -c "Modal appears on delete click" \
  -c "Type-to-confirm required when deleting > 10 items"

# Decompose (Opus if ANTHROPIC_API_KEY; else Ollama)
loom decompose SPEC-xxx --apply

# Execute (config pins executor_model)
loom_exec --loop

# Regenerate docs + run the new effectiveness rollups
loom sync --output ./docs
loom metrics --json
loom health-score --json
loom cost
```

### Running the benchmarks

```bash
# Small-model capability experiment — needs Ollama with the target model pulled
python3 benchmarks/ollama_gaps.py          --model qwen3.5:latest --trials 3
python3 benchmarks/ollama_gaps_extend.py   --model qwen3.5:latest --trials 3
python3 benchmarks/ollama_gaps_refactor.py --model qwen3.5:latest --trials 3
```

Results land in `benchmarks/ollama_gaps*.json`. See `experiments/gaps/FINDINGS.md` for the full write-up and headline numbers.

### Code style

- PEP 8, type hints where practical.
- Keep `cmd_*` functions in `src/loom/cli.py` as thin wrappers over `src/loom/services.py`. Services return plain JSON-serializable data (no printing, no `sys.exit`, no argparse).
- Service functions raise `LookupError` for "not found" and `ValueError` for bad input. Write-side services like `link` return `{linked: bool, warnings: [...]}` rather than raising on partial failure.
- Touchpoint instrumentation is mandatory: any service that surfaces a requirement to the agent must call `store.touch_requirement(req_id)` (M2.1); user-meaningful operations must call `services._record_event(store, …)` (M5.1).
- `["TBD"]` empty-list sentinel: legacy convention from the prior ChromaDB backend (kept on the SQLite backend so older stores round-trip cleanly). Dataclasses substitute `["TBD"]` when serializing; readers should treat `["TBD"]` as "unset."
- Backward compatibility: `from_dict` uses `setdefault` for new fields so older stores still load.
- No linter/formatter is enforced; keep the diff tight.
- Don't add files unless necessary. The package structure under `src/loom/` is intentionally flat.

## Submitting changes

1. Create a feature branch: `git checkout -b feature/my-feature` or `claude/<slug>` for AI-assisted work.
2. Make your changes + add tests. Unit tests go in `tests/test_services.py` or `tests/test_store.py`.
3. Regenerate docs if you touched requirements/specs: `loom sync --output ./docs`.
4. Confirm `pytest` passes (313 baseline tests).
5. Open a PR against `main`.

## Reporting issues

- Check existing issues first.
- Include reproduction steps.
- Provide relevant environment info (Python version, OS, Ollama version).

## Feature requests

Welcome! Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to make development better.
