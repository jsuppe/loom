# Contributing to Loom

Thanks for your interest in contributing to Loom! 🧵

## Getting Started

1. Fork and clone the repo.
2. Create a virtual environment: `python3 -m venv .venv`
3. Install dependencies: `.venv/bin/pip install chromadb pyyaml pytest`
4. Make sure Ollama is running with `nomic-embed-text` pulled.
5. Optional: pull `qwen3.5:latest` if you want to exercise `loom_exec` or the Ollama decomposer path.
6. Optional: set `ANTHROPIC_API_KEY` if you want to exercise the Opus decomposer path.

## Repository shape

```
loom/
├── scripts/loom              # Argparse CLI — one cmd_* per subcommand
├── scripts/loom_exec         # Small-model task executor (Ollama)
├── src/
│   ├── store.py              # ChromaDB wrapper + dataclasses (6 collections)
│   ├── services.py           # Shared CLI/MCP logic — plain Python, returns JSON-able data
│   ├── docs.py               # REQUIREMENTS.md / TEST_SPEC.md generation, traceability matrix
│   ├── testspec.py           # JSON-backed TestSpec store
│   ├── embedding.py          # Ollama embedding + LRU cache
│   └── conflict_verify.py    # LLM-verified conflict detection
├── hooks/loom_pretool.py     # PreToolUse hook: context injection + JSONL telemetry
├── mcp_server/               # Typed MCP tools over LoomStore (Phase A + B shipped)
├── prompts/                  # extract.md, link.md, decompose.md
├── benchmarks/               # Benchmark runners + result JSON (ollama_gaps_*)
├── experiments/gaps/         # Small-model capability experiment + FINDINGS.md
├── tests/                    # pytest suites (test_store.py, test_services.py, test_cli.py, test_hook.py)
└── docs/                     # Generated REQUIREMENTS.md / TEST_SPEC.md examples
```

`scripts/loom` inserts `src/` on `sys.path` and imports the modules directly (not as a package). `mcp_server/server.py` uses the same pattern. `src/__init__.py` exists for library-style imports.

## Development

### Running tests

```bash
# Store + dataclasses (incl. Task) — uses temp dir fixtures, fully self-contained
python -m pytest tests/test_store.py -v

# Service layer — covers all CLI verbs, decomposer parsing/validation, task lifecycle, cost, gaps
python -m pytest tests/test_services.py -v

# Subprocess tests for the PreToolUse hook
python -m pytest tests/test_hook.py -v

# CLI subprocess tests — require the skill installed at ~/.openclaw/skills/loom/
python -m pytest tests/test_cli.py -v
```

Sample embedding in tests is `[0.1] * 768` to match `nomic-embed-text` dimensions.

### Manual end-to-end check

```bash
# Capture a requirement
echo "REQUIREMENT: behavior | Users must confirm before deleting" \
  | python3 scripts/loom extract -p test-dev --rationale "Prevent accidental data loss"

# Add a spec
python3 scripts/loom -p test-dev spec REQ-xxx \
  -d "Confirmation modal: show modal before delete; require Type-to-confirm for > 10 items" \
  -c "Modal appears on delete click" \
  -c "Type-to-confirm required when deleting > 10 items"

# Decompose (Opus if ANTHROPIC_API_KEY; else Ollama)
python3 scripts/loom decompose SPEC-xxx --apply -p test-dev

# Execute
LOOM_PROJECT=test-dev python3 scripts/loom_exec --loop

# Regenerate docs
python3 scripts/loom sync -p test-dev --output ./docs

# Health check
python3 scripts/loom doctor -p test-dev --json

# Hook cost (if the hook has been firing)
python3 scripts/loom cost -p test-dev
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
- Keep `cmd_*` functions in `scripts/loom` as thin wrappers over `src/services.py`. Services return plain JSON-serializable data (no printing, no `sys.exit`, no argparse).
- Service functions raise `LookupError` for "not found" and `ValueError` for bad input. Write-side services like `link` return `{linked: bool, warnings: [...]}` rather than raising on partial failure.
- ChromaDB metadata rules: empty lists are rejected. Dataclasses substitute `["TBD"]` when serializing; readers should treat `["TBD"]` as "unset."
- Backward compatibility: `from_dict` uses `setdefault` for new fields so older stores still load.
- No linter/formatter is enforced; keep the diff tight.
- Don't add files unless necessary. The project intentionally keeps a flat structure.

## Submitting changes

1. Create a feature branch: `git checkout -b feature/my-feature` or `claude/<slug>` for AI-assisted work.
2. Make your changes + add tests. Unit tests go in `tests/test_services.py` or `tests/test_store.py`. CLI-shape tests go in `tests/test_cli.py` (note: requires the skill installed — see `KNOWN_ISSUES.md` T1).
3. Regenerate docs if you touched requirements/specs: `loom sync --output ./docs`.
4. Open a PR against `main`.

## Reporting issues

- Check existing issues first.
- Include reproduction steps.
- Provide relevant environment info (Python version, OS, Ollama version, chromadb version).

## Feature requests

Welcome! Open an issue describing:
- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

## Code of Conduct

Be respectful, constructive, and inclusive. We're all here to make development better.
