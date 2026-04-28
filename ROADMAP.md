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
- [x] **0.5i Duplicate-spec detection (D1 from sparkeye audit)** —
      `services.spec_add` refuses to create a second non-superseded
      spec under the same parent requirement (raises `DuplicateSpecError`
      with the siblings on it); CLI prints the existing spec(s) and the
      two options (supersede or `--force`). `services.doctor` gains a
      `duplicate_specs` check that surfaces the same condition in
      existing stores — validated on the sparkeye store where the check
      correctly flags `REQ-ef81f657 → {SPEC-c6aa6b90, SPEC-30fdda42}`.
      Caught at creation time for new specs; surfaced retroactively for
      existing ones. Addresses the "agent generated duplicate specs
      with different path conventions, nothing flagged it" failure mode
      from yesterday's sparkeye audit.

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

## Milestone 6: Cross-language validation (in progress)

**Last updated:** 2026-04-28

This milestone tracks empirical evidence for *where* the asymmetric
pipeline works (Opus plans, qwen executes), broken down by language
and project size. Companion writeup:
[`experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md).

### 6.0 Original objectives (recap)

1. **Capture** decisions and their rationale into a structured store,
   not just chat history.
2. **Surface** those decisions back to the agent before it edits the
   relevant code.
3. **Detect drift** when code changes diverge from documented
   decisions.
4. **Coordinate** an asymmetric pipeline: a frontier model plans, a
   small local model executes.
5. **Persist** rationale across separate sessions so a successor
   agent can pick up an absent predecessor's intent.

### 6.1 Data-backed claims

| claim | phase | result | data |
|---|---|---|---|
| Pre-edit hook lifts compliance at sub-frontier tiers | E | **+93 pp Sonnet, +60 pp Haiku, 0 pp Opus** | 30 trials |
| Hook lift transfers across model tiers | E.cross-tier | confirmed Haiku→Sonnet→Opus | 60 trials |
| Hook hard-block reliably stops drift | E.block | 30/30 mechanism reliable | 30 trials |
| Hook latency is constant at scale | E.scale | ~800 ms floor at 100/500 files | 16 trials |
| File-content drift is detected and surfaced | F | gap closed; end-to-end verified | committed |
| Asymmetric pipeline matches frontier quality at lower cost (single-file Python) | D | **~8× cheaper at N=20 matched-pricing**, parity quality | 60 trials |
| Cross-session rationale carries forward | G | **100 % citation Haiku, 93 % Sonnet** vs 0 % placebo | 120 trials |
| Pipeline transfers to single-file C++ | C/cpp-orders | 5/5 = 100% (qwen2.5-coder:32b) | 11 trials |
| Pipeline transfers to small multi-file Dart | C/dart-orders | 40 % → **100 %** after Tier 1+2 (qwen3.5) | 25 trials |

### 6.2 Null / mixed results

| claim | phase | result |
|---|---|---|
| Loom helps in-session at saturated benchmarks | A | Honest null — bounded cost overhead, no measurable correctness lift on benchmarks every Claude tier already passes |
| Asymmetric pipeline scales to 9-file Dart with qwen3.5 | C/dart-inventory | **0/30** — Dart-specific failure cluster (named-args, `const`, records) |
| Contract binding lifts the dart-inventory ceiling | C/dart-inventory | Cell A 0/15 vs Cell B 0/15 — no separation |

### 6.3 Per-language fitness map

| language | single-file | small multi-file (≤3) | large multi-file (~9) | verdict |
|---|---|---|---|---|
| **Python** | ✅ 100% (Phase D) | (skipped) | ✅ **5/5 = 100%** (qwen3.5) | use it freely up to ~9 files |
| **Dart (pure)** | (skipped) | ✅ 100% after Tier 2 | ❌ 0/35 (qwen3.5 + qwen2.5-coder:32b) | use for ≤ 3 files; ceiling robust to executor at 9 |
| **C++** | ✅ 100% (cpp-orders) | (skipped) | v1 header-only: 2/5 = 40% · **v2 split:** **4/5 = 80%** (qwen2.5-coder:32b) | use split `.h/.cpp` convention; matching qwen's native idiom doubled the pass rate |
| **Flutter Dart** | ❓ untested | ❓ untested | ❓ untested | benchmark + driver authored, not run |
| **JS/TS/Go/Rust** | ❓ untested | ❓ untested | ❓ untested | unknown |

### 6.4 Project-size fit (qwen3.5:latest as default executor)

- **≤ 250 LoC, ≤ 3 files of any tested language**: well-supported.
- **Single-header C++**: well-supported with qwen2.5-coder:32b.
- **9-file Python**: directionally supported (N=1).
- **9-file Dart**: not supported. Bring a different executor or a
  Dart-aware validator.
- **9-file C++**: unknown.
- **> 9 files**: unknown.

### 6.5 Design work the data points to

1. **Per-language semantic validators between body pass and grading.**
   The dart-inventory failures are deterministic and detectable:
   missing required getter, positional-vs-named arg mismatch,
   stripped `const`. A `dart analyze` / `pyright` / `clang-tidy`
   pass between body-write and grading would catch those before
   they cascade into the next task.

2. **Executor selection should be language-aware.** qwen3.5:latest
   is fine for Python; insufficient for 9-file Dart. A
   `LOOM_EXEC_MODEL_FOR_LANG` map (qwen2.5-coder:32b for Dart/C++,
   qwen3.5:latest for Python) is a small change with potentially
   large lift.

3. **Negotiated-contract architecture: revisit but evolve.** The
   `Specification.contracts_json` + `ContractAmendment` data plane
   was rolled back after experiments showed contracts can't
   manufacture executor capability. If reintroduced, the binding
   should focus on *cross-file invariants* (e.g. "every service
   constructor takes `Store&` first") that qwen *can* follow, not
   on signatures qwen reproducibly violates.

4. **Production-mode demonstration is missing.** The "your Claude
   Code session is the architect; loom_exec dispatches body work to
   qwen; failures surface back as structured tool output" workflow
   has the data plane to support it but no end-to-end demonstration
   trial. A worked example on a real (small) project is the
   clearest sales pitch.

5. **N-confidence on the 9-file Python claim.** N=1 is enough for
   direction but not for stat confidence. N≥5 in Python at 9 files
   is the cheapest experiment to firm up the cross-language story.

6. **Flutter / TS / real-world coverage.** Sales-relevant gaps —
   Flutter especially, given the audience.

### 6.6 In-flight tasks

- [x] **6.6.1 Python N=5 at 9 files** — **5/5 = 100%** (every trial 28/28). Median wall 224s, Opus $0.50. H1 confirmed at N=5.
- [x] **6.6.2 C++ N=5 at 9 files (header-only v1 + split v2)** — v1 header-only: **2/5 = 40%** with qwen2.5-coder:32b (header-only linker errors dominate). v2 split-convention restructure: **4/5 = 80%** — doubling the pass rate by matching qwen's native `.h/.cpp` style. v2 wall ~1100s, Opus $0.74 median.
- [x] **6.6.3 qwen2.5-coder:32b on dart-inventory N=5** — **0/5 = 0%**. The ceiling holds across local executors; bigger code-specialized model does not cross it. All 5 chains break on `lib/errors.dart` or `lib/types/customers.dart`.
- [x] **6.6.4 Wire `dart analyze` between body and grading** — `LOOM_EXEC_STATIC_CHECK=1` opt-in; runs `dart analyze --fatal-warnings` (Dart), `ast.parse` (Python), `g++ -fsyntax-only` (C++) before grading.
- [x] **6.6.5 Worked-example demo** — `docs/WORKED_EXAMPLE.md` walks through extract → spec → decompose → loom_exec → grade on python-inventory.
- [x] **6.6.6 Flutter multi-widget benchmark** — `flutter-counter` benchmark + 17/17 reference tests + driver. Driver authored as `phC_flutter_counter_oneshot_auto.py`; not yet executed.

Status updated as items land.

### 6.7 Pointers to data and code

- **Bake-off run summaries:** `experiments/bakeoff/runs-v2/`
- **Benchmarks:** `experiments/bakeoff/benchmarks/<lang>-<scope>/ground_truth/`
- **Drivers:** `experiments/bakeoff/v2_driver/phC_*_oneshot_auto.py`
- **Findings docs:** `experiments/bakeoff/FINDINGS-bakeoff-v2-*.md`
- **Phase C inventory writeup:** `experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md`
- **Older feature work and contract data plane:** `claude/bakeoff-v1` branch
