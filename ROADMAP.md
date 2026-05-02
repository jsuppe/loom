# Loom Roadmap

## Milestone 10: Semantic indexer integration (PLANNED — v1.x)

**Motivation.** The cross-language map (M8.4) showed C++ in a "collapsed"
regime: off=0%, on-rule=0%, +placebo=100%* (artifact), +rat=67%. C/Go
share the resistant-mid neighborhood. The hypothesis is that the
"include the file body" context bundle is too thin for languages where
meaning lives in headers, templates, ADL, and call-graph context that
the local file doesn't carry.

Before building anything heavy, the falsifying experiment is to swap
qwen3.5:latest → **qwen2.5-coder:32b** on S1 C++ (cpp-orders already
hit 6/6 with that executor at single-file in Phase C). If 32b bridges
S1, C++ is an executor-capacity ceiling, not a context ceiling — and
indexers are overkill. If it stays flat, semantic context becomes the
next lever, and this milestone defines how it integrates with Loom.

### 10.1 `SemanticIndexer` interface (DOES NOT REQUIRE Kythe)

A pluggable registry mirroring `runners.py`. Lives at `src/loom/indexers.py`.

```python
class SemanticIndexer:
    def supports(self, language: str) -> bool: ...
    def context_for(self, file: Path) -> str:
        """Symbol-level context for the executor prompt — definitions of
        referenced symbols, override chains, call sites. Empty string
        when no signal."""
    def resolve_symbol(self, ref: str) -> SymbolHit | None:
        """`app::OrderService::commit` → (file, byte-range, ticket)."""
    def signature_of(self, ticket: str) -> str | None:
        """Stable hash of the symbol's structural signature, for
        drift detection."""
```

`INDEXERS` registry holds zero or more registered indexers. Default is
**`NoOpIndexer`** — `supports()` returns False for everything;
`context_for()` returns `""`; `resolve_symbol()` returns `None`. Loom
keeps working unchanged when no real indexer is plugged in.

### 10.2 Context-bundle enrichment

When `loom_exec` builds a task prompt, it asks the registered indexer
for the target file's language: `context_for(file)`. The returned
string gets stitched into the prompt above the file body as
`// SEMANTIC CONTEXT`. Smallest invasive change — no data-model edits,
no link-surface changes.

This is the falsifying experiment for "is C++'s ceiling about
context, not capacity." Run S1 C++ with the indexer-enriched prompt
and compare against the cross-language map's baseline.

### 10.3 Symbol-level linking — `loom link --symbol`

Today: `loom link app/orders.cpp --req REQ-xxx` records a `(file,
line-range)` link. With an indexer:

```bash
loom link --symbol 'app::OrderService::commit' --req REQ-xxx
```

resolves the symbol via `indexers.resolve_symbol()` to a concrete
`(file, byte-range, kythe-ticket)`. The `Implementation` row gains two
new optional fields:

| field | purpose |
|---|---|
| `symbol_ticket: Optional[str]` | indexer's stable identity for the symbol |
| `symbol_signature_hash: Optional[str]` | hash of the symbol's structural signature at link time |

Both default to `None` (`setdefault` in `from_dict` for backward
compat). Existing stores keep loading; existing `--req` / `--spec`
links keep working.

### 10.4 Structural drift detection

Today: drift = `content_hash(file) != stored_hash`. A whitespace edit
trips drift; a function-signature change can hide if the bytes happen
to match. With `symbol_signature_hash` recorded:

```
drift_signals = {
    "content": stored.content_hash != recompute_content_hash(file),
    "structural": indexer.signature_of(ticket) != stored.symbol_signature_hash,
}
```

Reports both. The structural signal is far more useful for catching
"someone changed the API of the function this requirement is linked
to" — which is the actual concern requirements traceability is
trying to surface.

### 10.5 Build-time pipeline (the hard part)

Kythe's clang indexer needs a `compile_commands.json` extracted by
your build system. For a `pip install loom-cli` user that's
non-trivial onboarding. Realistic shape: **Loom integrates with your
existing Kythe deployment**, opinionated infra rather than bundled.
A `loom indexer doctor` health-check tells the user whether their
project has a working Kythe corpus before they try `--symbol`.

Other languages, other indexers. The registry pattern means each
plugs in independently:

| language | likely indexer | invocation |
|---|---|---|
| C++ | Kythe (clang-based) | `kythe -corpus loom -build_config compile_commands.json` |
| Java | Kythe (javac extractor) | same Kythe pipeline |
| Go | Kythe (Go indexer) | same Kythe pipeline |
| Python | Pyright (LSP) | runtime, no extraction step |
| TypeScript | tsserver (LSP) | runtime, no extraction step |
| Rust | rust-analyzer (LSP) | runtime, no extraction step |

LSP-backed indexers (Python/TS/Rust) are operationally cheaper than
Kythe — no graphstore to maintain, no extraction step. The Kythe
languages get the richest cross-references but pay for it in build-
pipeline complexity.

### 10.6 Tasks (status)

- [x] **10.1a Roadmap captured** — this section.
- [x] **10.1b Falsification: qwen2.5-coder:32b on S1 C++** — 20 trials
      (4 cells × N=5), 5.9 min wall. Result: **0/10 off, 0/10 on-rule,
      2/10 +placebo (noise), 0/10 +rat**. The bigger executor did NOT
      bridge S1 C++ — actually scored *worse* on the rat cell than
      qwen3.5's 67%. Conclusion: **C++ ceiling is NOT executor
      capacity**, semantic context becomes the next defensible lever.
      See `FINDINGS-bakeoff-v2-cpp-executor-falsification.md`.
- [x] **10.1c `SemanticIndexer` abstract interface + registry +
      `NoOpIndexer`** — `src/loom/indexers.py`.
- [x] **10.1d `Implementation.symbol_ticket` + `symbol_signature_hash`
      fields** — backward-compatible via `setdefault`.
- [x] **10.1e `loom link --symbol` plumbing** — works as a stub error
      path until a real indexer is registered.
- [x] **10.2 Context-bundle enrichment falsified with stub indexer**
      — phL2 ran 20 trials (4 cells × N=5) with a hand-authored
      `StubCppIndexer` that returns Kythe-shaped semantic context
      for `retry.hpp`. Same model as M10.1b (qwen2.5-coder:32b).
      Result vs the falsification baseline:
      | cell | baseline | with stub | delta |
      |---|---|---|---|
      | off | 0% | 0% | +0pp |
      | on-rule | 0% | 20% | **+20pp** |
      | on-rule+placebo | 20% | 60% | **+40pp** |
      | on-rule+rat | 0% | 40% | **+40pp** |
      Conclusion: **semantic context is the M10 lever for C++.** Lift
      is real but partial (peak 60%, not saturation) — context is
      necessary but not sufficient on this scenario. Wiring through
      `loom_exec` proper is now blocked only on a real indexer
      backend; the prompt-assembly seam is validated. Findings doc:
      `FINDINGS-bakeoff-v2-cpp-stub-indexer.md`.

- [x] **10.3 Multi-language stub-indexer extension** — extended the
      M10.2 falsification to two more languages from the cross-
      language map: C (resistant-mid) via phM2 + `StubCIndexer`,
      and JavaScript (graded-no-saturation) via phQ2 + `StubJsIndexer`.
      Same architecture, same `qwen2.5-coder:32b` executor, ~30
      trials (some cells N<5 due to runner crashes). Three different
      responses to the same intervention:

      | language | regime | rat baseline | with stub | takeaway |
      |---|---|---|---|---|
      | **C++** | collapsed | 0% (32b-no-stub) | **40%** | partial bridge |
      | **C** | resistant-mid | 60% | 50% | no measurable lift |
      | **JS** | graded-no-sat | 60% | **100%** | saturating lift |

      JS additionally jumped from 0% → 60% in the *off* cell —
      meaning the JSDoc-style stub was encoding an implicit rule.
      Conclusion: **the M10 architecture (pluggable per-language
      indexers) is right, but per-language plug-ins do different
      things.** The "one-indexer-fixes-all-resistant-languages"
      framing is wrong; C needs different signal than C++ and JS.
      Findings doc:
      `FINDINGS-bakeoff-v2-stub-indexer-multilang.md`.

      Side fix: phL2/phM2/phQ2 harnesses patched to write summary
      files even on Ollama-call failure, so future 32b crashes don't
      silently drop trials.
- [x] **10.3a phQ3 — clean-stub falsification of phQ2 (JS).** Stripped
      the JSDoc-style contract assertions from the JS stub, leaving
      peek-references-style structural facts only. N=40 (4 cells × 10).
      Result: phQ2's striking 0→60% off-cell lift was the JSDoc rule
      leak; on the clean stub it collapses back to 0%. The on-rule
      cell collapses below the no-stub baseline (0% vs 20%) — bare
      structural facts can be an *active distractor* without
      explanation alongside. Placebo and rationale cells stay near
      saturation (90% / 100%). Findings:
      [`FINDINGS-bakeoff-v2-js-stub-clean.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md).
- [x] **10.3b phQ4 — 32b no-stub baseline (JS).** Holds the model at
      qwen2.5-coder:32b and removes the stub. N=40. Decomposes the
      phQ3 vs phQ baseline +rat 60→100% lift into +20pp model tier
      and +20pp stub effect (additive). Surfaces a counter-intuitive
      finding: **the bigger code-specialist model HURTS bare-rule
      cells on contrarian specs** (-20pp on rule, -30pp on placebo
      vs qwen3.5). qwen2.5-coder:32b's "good practice" priors fight
      the contrarian rule. The stub effect is concentrated on
      placebo (**+80pp**, 10→90%) — strongest cell-specific stub
      effect across all M10 experiments. Reframes the JsIndexer
      product pitch: the indexer **amplifies the rationale signal**,
      it doesn't fix bare rule compliance. Findings:
      [`FINDINGS-bakeoff-v2-js-no-stub-32b.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-no-stub-32b.md).
- [x] **10.3c First real indexer: `JsIndexer` (LSP-backed,
      typescript-language-server).** `src/loom/indexers_js.py`.
      Subprocess wraps `typescript-language-server --stdio` over
      JSON-RPC, surfaces peek-references-style context shaped to
      match the phQ3 stub. Soft-fails to empty context with a one-
      time warning when the binary isn't on PATH. Validated against
      a JS fixture: cross-file references resolve correctly through
      ES module imports (CommonJS `require()` is a known limitation
      of `tsserver` checkJs mode — pending follow-up). 13 unit +
      integration tests pass. Install: `npm install -g
      typescript-language-server typescript`.
- [x] **10.3d phQ5 — JsIndexer end-to-end validation.** Authored
      a parallel ESM scenario (`s1_swallow_error_esm/`) with real
      sibling files (`retry.js` + `backoff_loop.js` + `sync_worker.js`
      + `package.json` + `jsconfig.json`) so typescript-language-server
      could index a real project. N=40, 4 cells × 10. **Validated
      partially:** rat cell saturates at 100% (matches phQ3 stub),
      confirming the rationale-amplification pitch holds with real
      LSP output. **Falsified partially:** placebo cell drops 90%
      → 20% (-70pp) — the phQ3 stub's lift on placebo was not pure
      structural facts. The hand-authored stub had additional
      curated content (test references, adjacent type definitions)
      that real `textDocument/references` doesn't surface. Identifies
      two concrete follow-ups to close the gap (import-filtering,
      adjacent type defs). Findings:
      [`FINDINGS-bakeoff-v2-js-real-lsp.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp.md).
- [x] **10.3e JsIndexer v2: filter import refs + adjacent type defs.**
      Both improvements landed in `src/loom/indexers_js.py`:
      `_is_import_ref` heuristic skips import-statement references
      before emission, and `_collect_adjacent_type_defs` queries
      `documentSymbol` on each sibling file with surviving refs and
      appends top-level Class signatures. 22 unit + integration tests
      pass (13 from M10.3c + 9 new). Validation via phQ6 (N=40)
      lifted placebo from 20% → **30%** (+10pp) — useful but well
      short of phQ3's 90%. Rationale held at 100%, off / on-rule
      held at 0%. **Falsifies** the M10.3d hypothesis that adjacent
      type defs were the load-bearing missing piece (phQ6 v2 has
      MORE type defs than phQ3, still 60pp short on placebo).
      Identifies the test-reference (`assert(result === null)`) as
      the most likely remaining missing ingredient. Findings:
      [`FINDINGS-bakeoff-v2-js-real-lsp-v2.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp-v2.md).
- [x] **10.3f phQ7 — test-reference surfacing experiment.** Tested
      the phQ6 hypothesis that test references were the load-bearing
      missing piece. **Confirmed strongly.** No JsIndexer code
      change required — `_walk_project` already includes test files
      because they're not in `_PROJECT_GLOB_IGNORE_DIRS`. The phQ5/
      phQ6 placebo gap was an artifact of harness workspace setup
      excluding `tests/`. With test file copied alongside source
      (one-line `setup_workspace` change), the LSP indexes it
      naturally and surfaces its references with the load-bearing
      `if (result === null) { console.log("PASS: ...") }` snippets.
      Result: placebo **30% → 70% (+40pp)**, the largest single-
      intervention effect across the entire M10 series. Rationale
      held at 100%, off / on-rule held at 0%. Remaining 20pp gap
      to phQ3's stub (90%) is plausibly N=10 noise. Operational
      guidance: instantiate `JsIndexer(root=...)` with the project
      root, not a subset that excludes tests. Findings:
      [`FINDINGS-bakeoff-v2-js-test-refs.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-js-test-refs.md).
- [x] **10.4 Multi-channel drift detection in `services.check`.**
      The original task was structural drift; investigation showed
      content-hash drift wasn't actually wired in either, so this
      milestone delivers both. `services.check` now returns a
      `drift_signals` dict alongside the existing `drift_detected`
      boolean, with three channels:
      - **content**: file's current content_hash differs from the
        impl's stored content_hash at link time (whitespace-sensitive,
        always available). The plain "the code changed since you
        linked it" signal that was missing.
      - **structural**: when an indexer's `signature_of()` returns
        a different hash than the impl's stored
        `symbol_signature_hash`. Catches API-shape changes that
        whitespace-sensitive content drift would either miss
        (renamed function with same bytes) or false-flag (whitespace
        edit to function body). Always False for impls without a
        `symbol_ticket` (i.e. impls linked without `loom link
        --symbol`); architecture is in place for users with
        registered indexers + symbol-resolved links.
      - **superseded**: existing signal — at least one linked
        requirement has been superseded since link time.
      `drift_detected` is the OR of all three (backwards-compatible
      with existing callers). `drift_detected` events in the M5.1
      log now also record which `signals` fired, so future metrics
      can break drift down by channel. CLI's `loom check` surfaces
      content + structural drift in the human-readable output.
      Tests: 5 new (8 total in TestCheck), full suite passes.
      Implementation note: JsIndexer's `signature_of()` MVP is a
      separate follow-up — until that lands, the structural channel
      is wired but reports False for JS impls. Other indexers
      (Pyright, Kythe, …) can light it up immediately by
      implementing `signature_of()` and registering.
- [x] **10.5 `loom indexer-doctor`** — health check for the
      semantic-indexer pipeline. `services.indexer_doctor(store)`
      enumerates registered indexers, calls each one's `health()`
      method (added to the `SemanticIndexer` interface as a default
      no-op; `JsIndexer` overrides to verify
      typescript-language-server is on PATH), and walks the store for
      symbol-linked `Implementation` rows to flag any whose language
      lacks a registered indexer (their structural drift channel is
      silently broken). CLI subcommand: `loom indexer-doctor [--json]`.
      Exit code 1 when not OK. Roll-up `ok` requires (a) at least one
      non-NoOp indexer registered, (b) all registered indexers report
      healthy, (c) every symbol-linked impl has an indexer for its
      language. Tests: 6 (TestIndexerDoctor). Full suite passes.
      Side-effect: added `LoomStore.list_implementations()` since the
      doctor needs a store-wide impl walk and only per-req/spec/pattern
      lookups existed before.

### 10.7 Open questions

- **Cache invalidation.** Kythe graphs go stale on file edits. Watch
  with inotify, re-run on every `loom link`, or accept eventual-
  consistency with surfaced "stale-index" warnings? Probably the third
  for v1.x.
- **Pricing.** Indexer infra is opinionated. Whether `loom-cli[kythe]`
  ships a Kythe deployment or just connects to a user-supplied one is
  a deployment-shape decision tied to the broader Loom-as-product story.
- **Python and friends.** LSP-backed indexers can run inline without
  any extraction step — they may be the cheaper proving ground for the
  whole architecture even though Python isn't the language with the
  ceiling. A `PyrightIndexer` would prove the seams without the Kythe
  build complexity.

## Milestone 9: PyPI packaging (DONE)

Loom installs from PyPI as `loom-cli`. Two console scripts (`loom`,
`loom_exec`) plus a real Python package (`import loom`,
`from loom.store import LoomStore`).

- [x] **9.1 Package layout** — `src/loom/` is the canonical package
      (was bare `src/*.py`). Internal imports use relative form
      (`from .store import …`); external callers (tests, scripts,
      mcp_server, experiments) use absolute (`from loom.store import …`).
- [x] **9.2 In-package data** — `prompts/` and `templates/` moved
      under `src/loom/` so they ship in the wheel; lookups switched
      to `Path(__file__).parent / "prompts"` etc.
- [x] **9.3 CLI entry points** — `scripts/loom` and `scripts/loom_exec`
      reduced to thin shims (`from loom.cli import main`); the real
      argparse logic lives in `src/loom/cli.py` and
      `src/loom/exec_cli.py`. `pyproject.toml::project.scripts`
      registers `loom = loom.cli:main` and
      `loom_exec = loom.exec_cli:main` so a `pip install` exposes
      both on PATH.
- [x] **9.4 pyproject.toml** — setuptools backend, Python 3.10+,
      single runtime dep (`PyYAML`); optional `mcp` and `dev`
      extras. `pip install -e .` validated end-to-end (313/313 tests
      pass against the editable install).

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
- [x] **0.4 Task entity** — `Task` dataclass + `tasks` table +
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

## Milestone 2: Requirement Hygiene (DONE — minus optional 2.4)

Surfaces staleness without automatic deletion. Requirements are decisions
— Loom helps users review and decide, never silently deletes.

- [x] **2.1 `last_referenced` timestamp** — `Requirement.last_referenced`
      is stamped by every read/link operation: `services.query`, `check`,
      `link`, `trace`, and `chain` all call `store.touch_requirement(req_id)`
      on each requirement they surface. Backward-compatible via
      `setdefault(None)` in `Requirement.from_dict`.
- [x] **2.2 `loom stale` command** — `services.stale()` ranks
      requirements by `last_referenced` ascending (never-referenced
      coldest, sorted by creation timestamp). Filters: `--older-than N`
      (days), `--unlinked` (no Implementation rows), `--include-archived`.
      `--json` for agent consumption. Superseded requirements are always
      excluded.
- [x] **2.3 `loom archive` command** — `archived` is a fifth state in
      `VALID_STATUSES`, distinct from `superseded`. `services.archive()`
      sets it; recoverable via `set_status(req_id, "pending")`. Filtered
      from `list`, `query`, and `stale` by default; opt in via
      `--include-archived` (or `--all` on `list`).
- [ ] **2.4 `loom review` (optional)** — Interactive walkthrough of
      stale requirements. Skipped for v1: the non-interactive flow
      (`loom stale --json` + `loom archive`/`set-status`) is sufficient
      for agent + scripted use cases. Revisit if interactive UX
      becomes a real demand.

Design principle: **surface, don't delete.**
1. `last_referenced` tracks activity passively (zero effort)
2. `loom stale` shows what's cold (read-only, safe)
3. User/agent decides: keep, archive, or supersede (explicit action)

## Milestone 3: Pluggable Embeddings (DONE)

Removes hard dependency on local Ollama. Three providers ship; the
SQLite store pins its embedding dimension on first write so a
provider switch can't silently corrupt search.

- [x] **3.1 Provider interface** — `src/embedding.py` dispatches to
      `ollama` (default; `nomic-embed-text` @ 768d), `openai`
      (`text-embedding-3-small` @ 1536d via `OPENAI_API_KEY`, urllib
      no-SDK), and `hash` (explicit deterministic, dim configurable
      via `model="hash:N"`). Selection precedence: `--embedding-provider`
      → `LOOM_EMBEDDING_PROVIDER` → `.loom-config.json::embedding_provider`
      → `ollama`. Cache key includes (provider, model) so switching
      providers can't return a stale vector. The Ollama-outage hash
      fallback is preserved (back-compat); other providers raise
      explicitly so misconfiguration surfaces.
- [x] **3.2 Dimension validation** — `LoomStore` adds a `_loom_meta`
      table that pins `embedding_dim` on the first vector write. All
      six collections route their writes through one `_check_embedding_dim`
      callback; mismatched writes raise `EmbeddingDimensionMismatch`
      with actionable advice ("provider likely changed; revert,
      use a fresh -p, or re-embed"). Legacy stores back-fill the
      dim from existing data on next open.

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

## Milestone 5: Metrics & Effectiveness Measurement (DONE)

Tracks whether Loom is actually helping. Without measurement, you can't
tell if the token cost is justified.

### 5.1 Event log (DONE)

Append-only JSONL log at `<store.data_dir>/.loom-events.jsonl`. One
JSON object per line, written by `services._record_event` from the
five canonical touchpoints:

| event | written by |
|---|---|
| `requirement_extracted` | `services.extract` |
| `conflict_found` | `services.extract` (per conflict it surfaces) |
| `implementation_linked` | `services.link` (per linked req) |
| `drift_detected` | `services.check` (when drift seen) |
| `check_clean` | `services.check` (when no drift) |

The `cost` log (`.hook-log.jsonl`) and `exec` log (`.exec-log.jsonl`)
remain separate — they capture different layers (PreToolUse hook
firings, executor task runs). The events log is for *user-meaningful*
operations.

### 5.2 `loom metrics` command (DONE)

Reads the event log and store state, returns a structured snapshot:

```
loom metrics -p proj                # human-readable
loom metrics -p proj --json         # for agents / CI
loom metrics -p proj --since 30d    # clip activity window to N days
```

Output shape:
- **requirements:** total / active / archived / superseded
- **coverage:** with_impls (count + %), with_test_specs (count + %)
- **drift:** events / files_affected / clean_checks / drift_ratio_pct
- **conflicts:** caught (count of conflict_found events)
- **activity:** extracted / linked (windowed by `--since`)
- **staleness:** never / over_30d / over_60d / over_90d buckets
                  (driven by `last_referenced` from M2.1)

### 5.3 `loom health-score` (DONE)

Single 0-100 score, equal-weighted average of four components:

| component | meaning |
|---|---|
| `impl_coverage` | % of active reqs with at least one linked Implementation |
| `test_coverage` | % of active reqs with a TestSpec |
| `freshness`     | % of active reqs referenced in the last 90 days |
| `non_drift`     | % of recent (90-day) checks that found no drift; 100 when no checks recorded yet (no signal ≠ degradation) |

```bash
SCORE=$(loom health-score -p proj --json | jq '.score')
[ "$SCORE" -lt 50 ] && echo "Requirements health is degrading"
```

Empty stores return `score=0`, never crash. Useful for CI gates.

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

## Milestone 6: Cross-language validation (DONE)

**Last updated:** 2026-04-30

This milestone tracks empirical evidence for *where* the asymmetric
pipeline works (Opus plans, qwen executes), broken down by language
and project size. Original Phase C companion:
[`FINDINGS-bakeoff-v2-phaseC-inventory.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-phaseC-inventory.md).
Headline expansion (9 languages × S1 cross-session smoke):
[`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).

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
| **Flutter Dart** | (skipped, multi-file by nature) | ✅ **3/3 = 100%** capability (qwen2.5-coder:32b) | ❓ untested (no `flutter-inventory` benchmark) | use for ≤ 3 widgets; widget-tree + ScaffoldMessenger + Key selectors all carry |

**Cross-language S1 smoke (Milestone 8)** added 7 more languages on
a focused contrarian-rule scenario (single file, qwen3.5):

| language | regime | rule lift | rationale lift |
|---|---|---|---|
| Java | bridging | +60 pp | +40 pp |
| TypeScript | bridging-graduated | +40 pp | +60 pp |
| JavaScript | graded (caps at 60%) | +20 pp | +40 pp |
| Go | volatile | +40 pp | +0 pp |
| C | resistant-mid | +0 pp | +10 pp |
| Rust | rule-saturates | **+100 pp** | +0 pp |
| Asm (NASM x86-64) | rule-saturates | **+100 pp** | +0 pp |

See [`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md) for the full classification + per-trial behavior.

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

### 6.6 Tasks (DONE)

- [x] **6.6.1 Python N=5 at 9 files** — **5/5 = 100%**.
- [x] **6.6.2 C++ N=5 at 9 files** — v1: 2/5 = 40%, v2 split: 4/5 = 80%.
- [x] **6.6.3 qwen2.5-coder:32b on dart-inventory N=5** — 0/5 = 0%, ceiling holds.
- [x] **6.6.4 Per-language static check between body and grading** — `LOOM_EXEC_STATIC_CHECK=1`.
- [x] **6.6.5 Worked-example demo** — `docs/WORKED_EXAMPLE.md`.
- [x] **6.6.6 Flutter multi-widget benchmark** — authored + run.
      6 trials on `qwen2.5-coder:32b`, 3/3 = 100% capability when
      the chain ran end-to-end. Naive 4/6 = 67% — pre-patch losses
      were Ollama keep_alive eviction races (fixed in commit
      `4c66c13`). Findings:
      [`FINDINGS-bakeoff-v2-flutter-counter.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-flutter-counter.md).

### 6.7 Pointers to data and code

- **Bake-off run summaries:** `experiments/bakeoff/runs-v2/`
- **Benchmarks:** `experiments/bakeoff/benchmarks/<lang>-<scope>/ground_truth/`
- **Drivers:** `experiments/bakeoff/v2_driver/`
- **Findings docs:** `experiments/bakeoff/FINDINGS-bakeoff-v2-*.md`

---

## Milestone 7: typelink (ROLLED BACK)

**Status:** Removed in commit `2599f15` after empirical validation
showed the verifier never intervened.

The hypothesis: a per-file public-API contract (extracted from
`*-contract` fenced blocks in the spec) would let `loom_exec`
catch surface drift between body-pass output and the spec's
declared shape, before grading. ~1300 LoC delivered: extractors
(Python ast, Dart regex), `Specification.public_api_json` field,
`Symbol`/`TypeContract` dataclasses, `type_contracts` ChromaDB
collection, post-task hook in `loom_exec`, CLI subcommands.

The rollout: 50+ trials with `LOOM_TYPELINK=1` produced
`typelink_fail = 0` across every run. The R1 lift in the python-
first smoke came entirely from Opus authoring contract-rich spec
text that gets injected into the executor's prompt via
`task_build_prompt` — *the contract reaches qwen whether or not
typelink parses it into structured form.*

The verifier hadn't earned its keep. ~1300 LoC removed in
`2599f15`. The data-plane lessons (contract-fence authoring is
the load-bearing part) are preserved in
[`FINDINGS-bakeoff-v2-milestone7.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-milestone7.md).

---

## Milestone 8: Python-first smoke series + cross-language map (DONE)

**Last updated:** 2026-04-30

After the Phase C cross-language ceiling work, a focused smoke
series isolated *what mechanism actually carries the lift* and
*how it generalizes across languages*. Headline result reframes
the Loom value claim.

### 8.1 D-smoke (R1 add a class) — delivery is the mechanism

5-cell A/B/C/D/E refactor smoke on `pyschema` library
(R1: add `RegexField`). 25 trials. Findings doc:
[`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md).

| cell | acceptance | what's in Loom | spec → exec prompt |
|---|---|---|---|
| D0 greenfield | 99 % | full build spec | yes |
| D1 qwen-only | 0 % | placeholder | no |
| D2 stored, undelivered | **0 %** | seeded refactor spec | **no** |
| D3 standard delivery | **95 %** | seeded refactor spec | **yes** |
| D4 + LOOM_TYPELINK=1 | 100 % | seeded refactor spec | yes |

**D2 vs D3 = 0 % vs 95 %** — same data in store; only `task.context_specs`
differs. The +95pp lift comes entirely from the standard
`task_build_prompt` injection. The Loom value-add is in delivery, not
storage.

### 8.2 R2-smoke (rename) — Loom adds nothing when task is easy

Same 5-cell shape on `pubsub` library, R2 rename refactor. 25 trials.

D1 = D3 = 100 %. qwen3.5 alone handles a pure rename perfectly given
the file context + clear task title. Loom's pipeline cannot lift a
100 % baseline. **The R1 result is real but task-specific.**

### 8.3 Cross-session smoke (3 contrarian scenarios on Python)

Tests Loom's longitudinal claim: agent B reads agent A's stored
rationale via Loom and respects a constraint it would otherwise
contradict. 3 scenarios × 4 cells × N=5 = 60 trials. Findings:
[`FINDINGS-bakeoff-v2-crosssession.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-crosssession.md).

Result: **rule-alone saturates compliance at 100 % across all 3
scenarios** in Python. Adding `Requirement.rationale` field provides
zero measurable lift over the rule. Pre-registered hypothesis (rationale
> rule by ≥10pp) is not supported in Python.

### 8.4 Cross-language map (9 languages, S1 contrarian)

Direct port of S1 to 7 more languages (C++, C, Java, Go, Rust, JS,
TS) plus Asm (NASM x86-64). 180 trials. **The headline finding.**
[`FINDINGS-bakeoff-v2-cross-language-map.md`](experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).

| language | off | on-rule | +placebo | +rat | regime |
|---|---|---|---|---|---|
| Python | 80 % | 100 % | 100 % | 100 % | already-saturated |
| Rust | 0 % | 100 % | 100 % | 100 % | rule-saturates **(+100 pp)** |
| Java | 0 % | 60 % | 100 % | 100 % | bridging |
| TypeScript | 0 % | 40 % | 80 % | 100 % | bridging-graduated ✓ |
| JavaScript | 0 % | 20 % | 40 % | 60 % | graded, no saturation |
| Go | 20 % | 60 % | 100 % | 60 % | volatile |
| C | 50 % | 50 % | 60 % | 60 % | resistant-mid |
| C++ | 0 % | 0 % | 100 %* | 67 % | collapsed |
| Asm | 0 % | 100 % | 100 % | 100 % | rule-saturates (+100 pp) |

**Off-cell fitness alone does NOT predict Loom lift.** Five languages
at off=0 % span the full Loom-response spectrum. The hidden variable
is qwen's "rule-followingness" in the language — a property of training
data + language characteristics, not raw fluency.

**Loom strong-fit zone:** Python, Java, TypeScript, Rust.
**Mixed:** JavaScript.
**Weak:** C, Go, C++.

### 8.5 Storage backend — SQLite swap

ChromaDB had intermittent cross-process flakiness ("hnsw segment
reader: Nothing found on disk") that bit the bakeoff harness.
Replaced with single-file SQLite + Python-side cosine NN
(commit `b8376d8`). 200/200 tests pass post-swap. 53KB single
file per project, inspectable with `sqlite3` CLI, zero new
dependencies (sqlite3 is stdlib). For Loom's actual scale (≤2k
vectors per collection in real projects), brute-force cosine is
faster than HNSW indexing — no approximation error, simpler code.

### 8.6 Recommended next experiments

1. **Rerun cross-language matrix with `qwen2.5-coder:32b`.** Most
   likely to shift C/Go/C++ from resistant to bridging at a higher
   model tier. Tests whether the regime pattern is qwen3.5-tier-
   specific.
2. **Re-run Go at higher N.** The +rat dropping below +placebo's
   100 % to 60 % is suspicious — N=10/20 would clarify.
3. **JS rule+rat at higher N.** The 60 % plateau is the most
   informative "graduated" result; tightening its CI would either
   confirm a real ceiling or reveal noise.
4. **S2 + S3 ports across languages.** Test whether per-language
   regime classification is stable across scenario types.

---

## Older feature work and contract data plane

`claude/bakeoff-v1` branch.
