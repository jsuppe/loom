# Loom 🧵

**Weaving requirements through code — and driving small-model code execution with them.**

Loom is a semantic requirements-traceability system for AI-assisted development, and a context substrate for running atomic code tasks on small local models. It extracts requirements from conversations, embeds them in a local SQLite store, links them to code, detects drift and conflicts, and now — with the `Task` entity, `loom decompose`, and `loom_exec` — turns that context into executable work for a local LLM.

## What Loom does

1. **Captures requirements** from natural language (`loom extract`) with rationale, acceptance criteria, domain.
2. **Expands them into specifications** (`loom spec`) — the detailed "how."
3. **Links code to requirements/specs** (`loom link`) with content hashes so drift is detectable.
4. **Generates living docs** (`loom sync`) — REQUIREMENTS.md, TEST_SPEC.md, traceability matrix.
5. **Decomposes specs into atomic executor-ready tasks** (`loom decompose`) — a frontier model emits a dependency-ordered YAML task list.
6. **Executes those tasks on a small local model** (`loom_exec`) — claims, assembles context, generates code, runs grading tests, promotes on pass.
7. **Measures itself** (`loom cost`, `loom doctor`, `loom coverage`) — hook latency, coverage gaps, drift.

## The thesis (validated)

> With enough detail in requirements, spec, and context, and small enough units of work, very small models can be effective.

We tested this empirically. See [`experiments/gaps/FINDINGS.md`](experiments/gaps/FINDINGS.md) for the full write-up.

### Headline results

Three tasks of escalating difficulty on the same function (write-from-spec, extend, behavior-preserving refactor), graded by 14 → 20 → 29 pytest assertions.

| Model                | Params | Task 1 | Task 2 | Task 3 | Latency (Task 3) | Cost/run |
|----------------------|-------:|:------:|:------:|:------:|:----------------:|:--------:|
| phi4-mini            |  3.8B  | 0/3    | 0/3    | —      | —                | ~$0      |
| llama3.1:8b          |  8.0B  | 1/3    | 3/3    | **0/3** behavior-broken | ~9s    | ~$0      |
| **qwen3.5:latest**   |  9.7B  | **3/3**| **3/3**| **3/3**| **11s**          | **~$0**  |
| gpt-oss:latest       | 20.9B  | —      | —      | 0/2 (format) | —          | ~$0      |
| qwen2.5-coder:32b    | 32.8B  | —      | 1/1    | 1/1    | 455s             | ~$0      |
| Haiku 4.5 (subagent) | cloud  | 3/3    | —      | —      | ~15s             | ~$0.02   |
| Opus 4.7 (subagent)  | cloud  | 3/3    | —      | —      | ~15s             | ~$0.28   |

Format: (perfect trials) / (trials).

### What this buys

- `qwen3.5:latest` (9.7B, local, commodity hardware) matched Opus 4.7 on every trial when given Loom context.
- Determinism at `temperature=0`: byte-identical output across repeated trials.
- Architectural cost split: Opus decomposes & reviews at spec boundaries (~$0.30 × 2/spec); qwen3.5 executes tasks (~$0/task). On a 100-task project, frontier-only ≈ $30; hybrid ≈ $0.60–1 — a 30–50× reduction, not an optimization.
- Capability floor depends on task shape: ~8B for template-driven extension, ~10B for write-from-spec and refactor. Below that, failures are silent — e.g., llama3.1:8b's refactor was structurally correct (9/9 helper tests pass) but broke behavior (10/20 regressions).
- Baseline Opus without Loom context underperformed enhanced Haiku with Loom context — the bundle structure matters more than the order-of-magnitude model gap.

See [`experiments/gaps/FINDINGS.md`](experiments/gaps/FINDINGS.md) for methodology, caveats, reproduction steps, and the benchmark runners in `benchmarks/ollama_gaps*.py`.

## Validation — what's been measured (~830 trials)

Loom has been tested across multiple phases of bake-off experiments
(A–S, plus cross-language smokes covering 9 languages). All run
summaries are committed under
[`experiments/bakeoff/runs-v2/`](experiments/bakeoff/runs-v2/).
Findings docs synthesize the methodology and headline results;
detailed evidence is per-trial JSON in `runs-v2/`.

### What Loom is, in light of the data

The smoke series isolated **what mechanism actually carries the
lift**: structured rule injection delivered through the standard
`task_build_prompt` pipeline. The store layer alone is
invisible to the executor; the *delivery* matters. And the lift
is **language-fitness-dependent** — it amplifies executors that
treat structured prompts as authoritative in the target language,
and provides little or no lift where the executor weighs rules
equal-or-less to task instinct.

The honest claim Loom can make:

> *"Loom's persistent structured-rule injection drives small-model
> executors toward consistent compliance with stored decisions —
> when the executor model treats structured prompts as authoritative
> in the target language. It amplifies fluent executors; it does
> not bring marginally-fluent executors over the threshold."*

### Top-line numbers (cumulative across all phases)

| measure | value |
|---|---|
| Total trials | **~830** across the bake-off series |
| Languages tested | **9** (Python, Java, JS, TS, Go, C, C++, Rust, Asm) |
| Cross-language S1 cells | **9 langs × 4 cells × N=5** = 180 trials in the cross-language smoke alone |
| Storage backend | SQLite (single `loom.db` per project, brute-force cosine NN) |
| Errors (harness crashes) | **0** |

### Headline finding 1: delivery is the mechanism (D2 vs D3)

In the python-first smoke, five cells isolated where the lift comes
from on a refactor task (add a `RegexField` class). Same Loom store
contents in D2 and D3; only the task's `context_specs` linkage
differed:

| cell | code state | Loom store | spec → exec prompt | acceptance |
|---|---|---|---|---|
| D0 greenfield | empty | full build spec (5 tasks) | yes | 99 % |
| D1 qwen-only | pre-written | placeholder only | no | **0 %** |
| **D2 stored, undelivered** | pre-written | seeded refactor spec | **no** | **0 %** |
| **D3 standard delivery** | pre-written | seeded refactor spec | **yes** | **95 %** |
| D4 + LOOM_TYPELINK | pre-written | seeded refactor spec | yes | 100 % |

**D2 vs D3 = 0 % vs 95 %** — same data in ChromaDB, only the task
linkage differs. The +95pp lift comes entirely from including the
spec text in the executor's prompt body via `task_build_prompt`.
Stored data alone is invisible to the executor.

Detail: [`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md).

### Headline finding 2: the cross-language Loom-lift map

Same scenario logic (S1: swallow vs propagate contrarian), same
qwen3.5:latest model, same 4-cell harness, ported across 9 languages:

| language | off | on-rule | +placebo | +rat | regime |
|---|---|---|---|---|---|
| **Python** | 80 % | 100 % | 100 % | 100 % | already-saturated |
| **Rust** | 0 % | 100 % | 100 % | 100 % | rule-saturates **(+100 pp)** |
| **Java** | 0 % | 60 % | 100 % | 100 % | bridging |
| **TypeScript** | 0 % | 40 % | 80 % | 100 % | bridging-graduated ✓ |
| **JavaScript** | 0 % | 20 % | 40 % | 60 % | graded, no saturation |
| **Go** | 20 % | 60 % | 100 % | 60 % | volatile |
| **C** | 50 % | 50 % | 60 % | 60 % | resistant-mid |
| **C++** | 0 % | 0 % | 100 %* | 67 % | collapsed (*placebo artifact) |
| **Asm (NASM x86-64)** | 0 % | 100 % | 100 % | 100 % | rule-saturates **(+100 pp)** |

**Off-cell fitness alone does NOT predict Loom lift.** Five languages
with off=0 % (Java, TS, JS, Rust, C++) span the full Loom-response
spectrum — Rust gains +100pp from rule alone, C++ gains 0. The
hidden variable is qwen's *rule-followingness* in that language.

**Loom's strong-fit zone:** Python, Java, TypeScript, Rust.
**Mixed:** JavaScript (caps at 60 %).
**Weak:** C, Go, C++.

Detail: [`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).

### Other validated claims

| claim | phase | result | data |
|---|---|---|---|
| Pre-edit hook lifts compliance at sub-frontier tiers | E | **+93 pp Sonnet, +60 pp Haiku, 0 pp Opus** | 30+60 trials |
| Hard-block-on-drift mechanism is reliable | E.block | 30/30 reliable across tiers | 30 trials |
| Hook latency is constant under scale | E.scale | ~800 ms floor at 100 / 500 files | 16 trials |
| Drift detected and surfaced end-to-end | F | gap closed; verified | committed |
| Asymmetric pipeline matches frontier quality at lower cost | D | **~8× cheaper at N=20 matched-pricing**, parity quality | 60 trials |
| Pipeline transfers to single-file C++ | C/cpp-orders | 6/6 = 100 % (qwen2.5-coder:32b) | 6 trials |
| Pipeline transfers to small multi-file Dart | C/dart-orders | 40 % → **100 %** after Tier 1+2 (qwen3.5) | 25 trials |
| Pipeline transfers to 9-file Python | C/python-inventory | **5/5 = 100 %** (qwen3.5) | 5 trials |

### Honest null / mixed / rolled-back results

| claim | phase | result |
|---|---|---|
| Loom helps in-session at saturated benchmarks | A | Honest null — bounded cost overhead, no measurable correctness lift on benchmarks every Claude tier already passes (TaskQueue) |
| Asymmetric pipeline scales to 9-file Dart | C/dart-inventory | **0/35** across executors — Dart-specific failure cluster |
| Contract binding lifts the dart-inventory ceiling | C/dart-inventory | Cell A 0/15 vs Cell B 0/15 — no separation |
| Cross-session rationale beats rule alone | phK | Honest null on Python S1/S2/S3: rule = rule+rationale = 100 %. Rationale-as-distinct-lever isn't supported by the data. JS is the lone counter-example (60 % vs 40 %). |
| typelink (Milestone 7) verifier earns its keep | M7 | **Removed.** 50+ trials produced typelink_fail = 0 across every run. Reverted (~1300 LoC). The data plane (`*-contract` fences in spec text) is what carried the R1 lift, not the structured public_api parsing. |
| Loom mechanism generalizes to all qwen-readable languages | phL/M/S | **Partially false.** C/Go/C++ show flat or absent lift on the same scenario where Python/Java/Rust/TS show clean bridging. |

### Documents

- **[`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md)** — **the headline document.** Cross-language Loom-lift map across 9 languages, with regime classification.
- **[`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md)** — D2 vs D3 = 0 → 95 % isolation of delivery as the mechanism. R2 (rename) replication showing Loom adds nothing when task is easy.
- **[`FINDINGS-bakeoff-v2-crosssession.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-crosssession.md)** — Phase K cross-session smoke; rationale field is decorative on Python S1/S2/S3.
- **[`FINDINGS-bakeoff-v2-cpp-comparison.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cpp-comparison.md)** — Phase L; first evidence the Loom mechanism collapses outside Python.
- **[`FINDINGS-bakeoff-v2-milestone7.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-milestone7.md)** — typelink rationale, validation, and rollback.
- **[`FINDINGS-bakeoff-v2-phaseA.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-phaseA.md)** — Phase A (TaskQueue saturated, cost-overhead measurement).
- **[`FINDINGS-bakeoff-v2-phaseC-inventory.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md)** — Phase C cross-language inventory benchmarks; H1 vs H2 disambiguation.
- **[`FINDINGS-bakeoff-v1.md`](experiments/bakeoff/FINDINGS-bakeoff-v1.md)** + **[`FINDINGS-bakeoff-v2-pilot.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-pilot.md)** — earlier methodology and direction-reversal notes.
- **[`docs/WORKED_EXAMPLE.md`](docs/WORKED_EXAMPLE.md)** — end-to-end production-mode walkthrough on a real benchmark.
- **[`experiments/bakeoff/EVIDENCE_REPORT.md`](experiments/bakeoff/EVIDENCE_REPORT.md)** — earlier auto-generated evidence rollup (covers Phases A–C/E/F, before the smoke series).

## Features

- **Requirement extraction** — Parse decisions from natural language into structured requirements with rationale and domain.
- **Specification layer** — Detailed HOW for each requirement; the anchor for tasks and implementations.
- **Pattern entity** — Shared design standards applied across multiple requirements.
- **Task entity** — Atomic, dependency-ordered work items with lifecycle (pending → claimed → complete | rejected | escalated) and atomicity budget (≤2 files, ≤80 LoC by default).
- **Semantic search** — Find requirements by meaning via Ollama embeddings (`nomic-embed-text`, 768-dim).
- **Conflict detection (LLM-verified)** — Embedding overlap surfaces candidates; an LLM pass confirms real conflicts before they're reported.
- **Drift detection** — Content hashes on `Implementation` records let `loom check` flag code linked to superseded requirements.
- **Traceability** — `loom trace`, `loom chain`, `loom coverage` give bidirectional req ↔ spec ↔ impl ↔ test visibility.
- **Living documentation** — `loom sync` generates REQUIREMENTS.md and TEST_SPEC.md with a traceability matrix; PRIVATE.md filters sensitive reqs from public docs.
- **Hook instrumentation** — `hooks/loom_pretool.py` injects Loom context as a system-reminder on Edit/Write; logs per-fire latency and bytes to JSONL.
- **Cost measurement** — `loom cost` reports p50/p95/p99 hook latency, total injected bytes, and skipped-vs-fired ratio.
- **Spec → task decomposition** — `loom decompose SPEC-xxx --apply` uses a frontier model (or local fallback) to emit atomic tasks with full context bundles.
- **Small-model task execution** — `scripts/loom_exec` claims the next ready task, calls Ollama, applies code to a scratch copy, runs grading tests, and promotes on pass.
- **MCP server** — Phase A (read) and Phase B (write) tools shipped; wraps `LoomStore` as typed MCP tools for Claude Code and other clients. See [`mcp_server/README.md`](mcp_server/README.md).

## Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running on `localhost:11434`
  - `nomic-embed-text` — embeddings
  - `qwen3.5:latest` — recommended local executor (see findings above)
- SQLite (stdlib via `sqlite3` — no separate install)
- Optional: `ANTHROPIC_API_KEY` in the environment if you want Opus-driven decomposition

### As an OpenClaw skill

```bash
git clone https://github.com/jsuppe/loom.git ~/.openclaw/skills/loom
cd ~/.openclaw/skills/loom
python3 -m venv .venv
.venv/bin/pip install pyyaml    # sqlite3 is stdlib
ollama pull nomic-embed-text
ollama pull qwen3.5:latest    # for loom_exec
```

### Standalone

```bash
git clone https://github.com/jsuppe/loom.git
cd loom
python3 -m venv .venv
.venv/bin/pip install pyyaml    # sqlite3 is stdlib
ollama pull nomic-embed-text
export PATH="$PWD/scripts:$PATH"
```

## Quick start

```bash
# One-time: onboard the target repo (writes .loom-config.json, health-checks)
cd ~/path/to/my-project
loom init

# Capture a requirement (no more -p flag once .loom-config.json exists)
echo "REQUIREMENT: behavior | Users must confirm before deleting" \
  | loom extract --rationale "Prevent accidental data loss"

# Expand it into a spec
loom spec REQ-abc12345 \
  -d "Confirmation modal: show modal on delete button; require Type-to-confirm for > 10 items" \
  -c "Modal appears on delete click" \
  -c "Type-to-confirm required when deleting > 10 items" \
  --test tests/test_delete_confirm.py::TestDeleteConfirm
# --test writes a failing-placeholder skeleton so the executor has a
# real grading target. Replace the placeholder assertions before
# running loom_exec.

# Decompose spec into atomic tasks (Opus by default if ANTHROPIC_API_KEY is set)
loom decompose SPEC-xxx --apply

# Execute the next ready task on the local small model
# (executor_model comes from .loom-config.json — no flag needed)
loom_exec --next

# Or run until the queue is empty
loom_exec --loop

# Regenerate living docs
loom sync

# Check what the PreToolUse hook is costing you
loom cost
```

## End-to-end pipeline

```
┌──────────────┐  loom extract  ┌─────────────┐  loom spec  ┌──────────────┐
│ Conversation │ ─────────────> │ Requirement │ ──────────> │Specification │
└──────────────┘                └─────────────┘             └──────┬───────┘
                                                                   │ loom decompose --apply
                                                                   ▼
┌──────────────┐  loom_exec    ┌──────────────────────────────────────┐
│ code + tests │ <──────────── │ Task(s): atomic, ≤2 files, ≤80 LoC,  │
│  (promoted)  │               │ single grading criterion, dep-ordered│
└──────────────┘               └──────────────────────────────────────┘
       │                                                  ▲
       │ loom link / hook                                 │ loom_exec --next
       ▼                                                  │
┌───────────────┐   loom sync   ┌──────────────────┐      │
│Implementation │ ────────────> │ REQUIREMENTS.md  │      │
│  + hash       │               │ TEST_SPEC.md     │      │
└───────────────┘               │ Traceability mat │      │
                                └──────────────────┘      │
                                                          │
                                ┌─────────────────────────┘
                                │ loom cost / loom doctor / loom coverage
                                ▼
                        Telemetry, drift, gap analysis
```

## Usage patterns

### For humans (chat-based)

```
"The app should require email verification before posting"
```

If the agent has Loom wired in, that becomes a REQ. For precision, use the structured form:

```
REQUIREMENT: behavior | Email verification required before first post
```

### For agents

Add Loom to your `AGENTS.md` — see [`agents.d/loom-integration.md`](agents.d/loom-integration.md). Key moments:

- **On decision** — `loom extract` with `--rationale`.
- **Before editing** — the `loom_pretool.py` hook auto-injects linked reqs/specs/drift into context (no agent effort required).
- **After implementing** — `loom link <file> --req REQ-xxx` or `--spec SPEC-xxx`.
- **For large work** — `loom decompose SPEC-xxx --apply` then `loom_exec --loop`.
- **During heartbeats** — `loom status --json` to surface drift.

### For CI/automation

```bash
cat decisions.txt | loom extract -p myproject
loom check src/auth/login.py -p myproject                    # exit 2 on drift
loom tests -p myproject --public | grep -q "⚠️" && exit 1   # fail CI on uncovered reqs
loom cost --json | jq '.overhead_pct > 80 and "warn"'         # catch runaway hook overhead
```

## Commands

Read-only commands support `--json` / `-j`. Exit codes: **0** success, **1** error, **2** drift/conflicts.

| Command                  | Purpose                                                              | `--json` |
|--------------------------|----------------------------------------------------------------------|----------|
| `extract`                | Parse `REQUIREMENT: domain \| text` from stdin (`--rationale`)       | —        |
| `check <file>`           | Detect drift in a file                                               | yes      |
| `context <file>`         | Pre-edit briefing: linked reqs, specs, drift (used by the hook)      | yes      |
| `link <file>`            | Link code to reqs (`--req`) or specs (`--spec`)                      | —        |
| `status`                 | Project overview with drift summary                                  | yes      |
| `query <text>`           | Semantic search                                                      | yes      |
| `list`                   | List requirements                                                    | yes      |
| `sync`                   | Regenerate REQUIREMENTS.md + TEST_SPEC.md                            | —        |
| `conflicts --text`       | Detect conflicting/overlapping reqs (LLM-verified)                   | yes      |
| `supersede <id>`         | Mark a requirement as superseded                                     | —        |
| `test` / `verify` / `tests` / `test-generate` | Manage test specs                               | `tests`  |
| `trace <target>`         | Bidirectional traceability (req↔files)                               | yes      |
| `chain <req_id>`         | Full traceability chain (req→patterns→specs→impls→tests)             | yes      |
| `coverage`               | Show requirements missing implementations or tests                   | yes      |
| `refine` / `set-status` / `incomplete` | Elaborate and status-manage reqs                       | —        |
| `spec` / `specs` / `spec-link` | Specification management                                       | `specs`  |
| `pattern` / `patterns` / `pattern-apply` | Shared design patterns                               | `patterns` |
| `doctor`                 | Health checks (Ollama, store, orphans, drift, coverage)              | yes      |
| **`init`**               | Onboard a target repo: write `.loom-config.json` + health-check      | —        |
| `init-private`           | Create `PRIVATE.md` template                                         | —        |
| **`cost`**               | Summarize PreToolUse hook cost (latency, bytes, overhead)            | yes      |
| **`task`**               | Atomic work-item CRUD (`add`/`list`/`show`/`claim`/`release`/`complete`/`reject`/`prompt`) | yes |
| **`decompose <SPEC>`**   | Propose atomic-task decomposition (`--apply` persists)               | —        |

Separate entry point for execution:

| Tool                 | Purpose |
|----------------------|---------|
| `scripts/loom_exec`  | Drive Ollama against the Task queue. Flags: `--next`, `--loop`, `--dry-run`, `--model`, `-p`. Default model from `LOOM_EXECUTOR_MODEL`, falling back to `qwen3.5:latest`. |

Project is auto-detected from the git repo name; override with `-p/--project` or the `LOOM_PROJECT` env var.

## Per-project configuration (`.loom-config.json`)

`loom init` writes a `.loom-config.json` at the root of the target repo. It pins defaults so you don't have to pass `-p` / `--target-dir` / `--model` on every invocation. Precedence for every setting: **CLI flag > environment variable > `.loom-config.json` > built-in default.**

```json
{
  "project": "myapp",
  "target_dir": ".",
  "decomposer_model": null,
  "executor_model": "qwen3.5:latest",
  "embedding_model": "nomic-embed-text",
  "test_runner": "pytest",
  "test_dir": "tests",
  "ignore": [".git", "__pycache__", ".venv", "venv", "node_modules", ...]
}
```

`loom init` also runs a health-check on the way in — Ollama reachable, required models pulled, pytest declared in the target's deps, `tests/` directory present (creating it if not). A warning lists anything missing without blocking.

### Templates (`loom init --template`)

Scaffold files into the target repo from a template. Four starters ship as **reference implementations** — intentionally opinion-free, one per shipped test runner:

| Starter | Runner | Install | Test |
|---|---|---|---|
| `python-minimal` | pytest | `pip install -e '.[dev]'` | `pytest` |
| `dart-minimal` | dart_test | `dart pub get` | `dart test` |
| `flutter-minimal` | flutter_test | `flutter pub get` | `flutter test` |
| `typescript-minimal` | vitest | `npm install` | `npm test` |

Fork any of them into `~/.loom/templates/<your-name>/` and customize — the shipped ones are not a canonical set.

```bash
loom init --template flutter-minimal \
  --var app_name=myapp --var description="my app" \
  --var author="me" --var sdk_constraint="^3.0.0"

loom init --list-templates
```

Each template's `manifest.yaml` can declare `config_overrides` that are merged into `.loom-config.json` on init — that's how `flutter-minimal` pins `test_runner: flutter_test` and `test_dir: test` automatically.

Template structure:
```
~/.loom/templates/my-fastapi/
├── manifest.yaml          # name, description, variables[]
└── files/                 # copied verbatim, with {{ var }} substitution
    ├── pyproject.toml
    ├── src/{{ app_name }}/__init__.py    # names are substituted too
    └── tests/test_smoke.py
```

Discovery precedence: `~/.loom/templates/<name>/` wins over `<loom-repo>/templates/<name>/`, so user-authored templates can override shipped ones with the same name. Missing variables without defaults are prompted interactively when stdin is a TTY, or passed via `--var KEY=VALUE` (repeatable). Existing files in the target are never overwritten unless `--force` is set.

### Test runners (`.loom-config.json` → `test_runner`)

`loom_exec` grades through a pluggable runner registry (`src/runners.py`). Shipped runners:

| `test_runner`    | Language    | apply_mode | Grading command                            |
|------------------|-------------|------------|--------------------------------------------|
| `pytest`         | Python      | `append`   | `python -m pytest <path>::<Class>`         |
| `dart_test`      | Dart        | `replace`  | `dart test <path> --plain-name <name>`     |
| `flutter_test`   | Dart        | `replace`  | `flutter test <path> --plain-name <name>`  |
| `vitest`         | TypeScript  | `replace`  | `npx vitest run <path> -t <name>`          |

The runner decides: (a) the command and how to parse pass/total from its output, (b) the code-block fence in the executor prompt (`python` / `dart` / `typescript`), (c) the apply mode (Python can append because last-definition wins; Dart/TS require full-file replacement), (d) the failing-placeholder test skeleton `loom spec --test` writes.

`test_to_write` stays pytest-style (`path::Name`) everywhere — Loom translates it per runner.

Authoring a new runner: add a `Runner(...)` entry to `RUNNERS` in `src/runners.py`. No other changes required.

## Hook instrumentation

See [`hooks/README.md`](hooks/README.md) for install instructions. Summary:

- `hooks/loom_pretool.py` registers as a `PreToolUse` hook on `Edit|Write|MultiEdit|NotebookEdit`.
- On each fire: runs `loom context <file>`, injects linked reqs/specs/drift as a system-reminder, logs `{ts, tool, file, latency_ms, bytes, reqs, specs, drift, fired, skipped}` to `<project>/.hook-log.jsonl`.
- `LOOM_HOOK_BLOCK_ON_DRIFT=1` turns drift into a hard block on the tool call.
- `loom cost` aggregates the log: p50/p95/p99 latency, injected bytes, overhead percentage (fires where nothing was injected).

Hook is designed never to block unrelated work — missing CLI, malformed stdin, or context errors all exit 0 silently.

## Data model

All dataclasses ship with `to_dict`/`from_dict` for serialization. Empty lists are stored as `["TBD"]` (legacy convention from the prior ChromaDB backend, kept on the SQLite backend so older stores round-trip cleanly; read them back as "unset.")

- **Requirement** — `id`, `domain`, `value`, `rationale`, `status` (pending/in_progress/implemented/verified/superseded), `acceptance_criteria`, `elaboration`, `test_spec_id`, `source_msg_id`, `source_session`, `timestamp`, optional `superseded_at`.
- **Specification** — Detailed HOW for a `parent_req`. Status: draft/approved/implemented/verified/superseded.
- **Pattern** — Shared design standard with an `applies_to` list.
- **Implementation** — Code chunk linked to reqs/specs with a content hash (drift detection).
- **Task** — Atomic work item. Fields: `title`, `files_to_modify`, `test_to_write`, `context_reqs`/`specs`/`patterns`/`sidecars`/`files`, `size_budget_files`, `size_budget_loc`, `depends_on`, `status`, `claimed_by`, `claimed_at`, `completed_at`, `rejected_reason`, `escalated_reason`, `created_by`, `parent_spec`.
- **TestSpec** (JSON-backed, not in the SQLite store) — steps, expected outcome, automated flag, links to reqs/specs.

Six tables in `loom.db`: `requirements`, `specifications`, `patterns`, `implementations`, `chat_messages`, `tasks`. Each row carries `id` (PK), `embedding` (BLOB), `metadata` (JSON), `document` (TEXT). Brute-force cosine similarity for nearest-neighbor search — no HNSW indexing.

## Source of truth

```
Loom Store (SQLite at ~/.openclaw/loom/<project>/loom.db)
    ↓ loom sync
REQUIREMENTS.md + TEST_SPEC.md  (generated — do NOT edit by hand)
    ↓ git push
Repo (for sharing)
```

To modify requirements: `loom extract` / `loom refine` / `loom supersede` — never edit generated files.

## Privacy

Create `PRIVATE.md` in your project to exclude sensitive requirements from public docs:

```markdown
# Private Requirements
- REQ-abc123 — Internal security policy
- REQ-def456 — Proprietary algorithm details
```

Generate public docs: `loom sync --public`.

## Data storage

```
~/.openclaw/loom/<project>/
├── loom.db                  # SQLite (6 tables)
├── .loom-specs.json        # Test specifications
├── .hook-log.jsonl         # PreToolUse hook activity log
├── .exec-log.jsonl         # loom_exec run log
└── PRIVATE.md              # Private requirement IDs
```

## Requirement format

```
REQUIREMENT: <domain> | <requirement text>
```

Domains: **terminology**, **behavior**, **ui**, **data**, **architecture**.

## How it works (under the hood)

1. **Extraction** — Structured text parsed into `Requirement` dataclass.
2. **Embedding** — `nomic-embed-text` via Ollama (768 dimensions) with a process-local LRU cache (max 500); 3× retry with fallback to a deterministic hash-based vector if Ollama is down.
3. **Storage** — SQLite persists embeddings + metadata across six tables in a single `loom.db` file.
4. **Search** — Semantic similarity over the appropriate collection.
5. **Conflict detection** — Nearest-neighbor search surfaces overlap candidates; an LLM pass (`src/conflict_verify.py`) confirms real conflicts before surfacing.
6. **Drift** — `Implementation.content_hash` is compared against the current file; linked reqs that have been superseded flag the impl as drifted.
7. **Decomposition** — `loom decompose` builds a prompt from the spec + parent req + applicable patterns, calls the decomposer (Anthropic or Ollama, selected by `provider:model` prefix), parses the YAML task list, validates atomicity + dep graph, and persists if `--apply`.
8. **Execution** — `loom_exec` selects the next ready task (dependencies complete), assembles its context bundle from `context_reqs`/`specs`/`patterns`/`sidecars`/`files`, calls the executor model, extracts the code block, applies to a scratch copy, runs the grading test, promotes to the real tree on pass.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`ROADMAP.md`](ROADMAP.md).

## License

MIT — see LICENSE.
