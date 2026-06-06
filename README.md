# Loom 🧵

**Weaving requirements through code — and driving small-model code execution with them.**

Loom is a semantic requirements-traceability system for AI-assisted development, and a context substrate for running atomic code tasks on small local models. It extracts requirements from conversations, embeds them in a local SQLite store, links them to code, detects drift and conflicts, and now — with the `Task` entity, `loom decompose`, and `loom_exec` — turns that context into executable work for a local LLM.

> **Evaluating Loom for your team?** Read [`docs/EFFECTIVENESS.md`](docs/EFFECTIVENESS.md) — the empirical case for Loom organized by user benefit, with citations to ~1,050 trials. ~5 minute read.

## What Loom does

1. **Captures requirements** from natural language (`loom extract`) with rationale, acceptance criteria, domain.
2. **Captures research artifacts alongside requirements** — the same store records `kind=finding`, `methodology`, `process_rule`, and `hypothesis` with their own lifecycle states (M12). One traceable substrate covers both *what we decided* and *what we observed*.
3. **Auto-captures decisions from chat** — the `UserPromptSubmit` intake hook (M11.5) classifies user messages, surfaces semantic neighbors, and routes to one of six branches (auto-link, propose, capture-with-rationale, ask-for-rationale, dedupe, no-op) under daily auto-link budget guardrails.
4. **Expands them into specifications** (`loom spec`) — the detailed "how."
5. **Links code to requirements/specs** (`loom link`) with content hashes so drift is detectable.
6. **Generates living docs** (`loom sync`) — REQUIREMENTS.md, TEST_SPEC.md, FINDINGS.md, METHODOLOGY.md, PROCESS-RULES.md, HYPOTHESES.md (per-kind renderers, M12.2), with a traceability matrix.
7. **Decomposes specs into atomic executor-ready tasks** (`loom decompose`) — a frontier model emits a dependency-ordered YAML task list.
8. **Executes those tasks on a small local model** (`loom_exec`) — claims, assembles context, generates code, runs grading tests, promotes on pass. The context bundle now includes a structured **Semantic context** block from the pluggable `SemanticIndexer` registry (M10) — TypeScript/JavaScript via `typescript-language-server`, plus simpler stub-indexers for C/C++/JS.
9. **Pushes warrants to a claim graph (Driftgraph) and surfaces foundation drift back into edits** — outbound, validated through `Toulmin@v1` and `Falsifiability@v1` philosophical validators (M13.L2/L3); inbound through a three-tier channel (cache → HTTP → Cypher fallback) so structural drift in upstream claims appears as a `GRAPH-DRIFT` flag in `loom context`. A scope-qualified drift warning closes the over-firing gap to **100 % recall / 12 % FPR** on the locked m13_v1 evaluation set (M13.7d).
10. **Measures itself** (`loom cost`, `loom doctor`, `loom metrics`, `loom health-score`) — hook latency, coverage gaps, drift, kind-aware rollups, single 0–100 CI gate. `doctor` also warns on stale-pending requirements (>30 days, no impls — M15.3) and provisional-intake backlog (M14.4).
11. **Auto-advances requirement lifecycle** (M15) — `loom link` bumps `pending → in_progress`; passing `loom verify` bumps to `implemented`; `loom verify-stable --apply` promotes drift-free implemented reqs to `verified`. Multi-hop `set-status` fast-forwards through a strict transition graph with audit-log events per hop.
12. **Validates its own research methodology** — A 5-step pattern (independent design review → pre-registration → independent-taxonomy check → cross-vendor judge calibration → honest falsifier verdict) is captured as REQ-3896db58 and followed by all M22-era studies. Caught fatal flaws in 2 designs pre-launch and produced honest "refined" / "partially refuted" verdicts on 2 run studies.

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

## Validation — what's been measured (~1,050 trials)

Loom has been tested across multiple phases of bake-off experiments
(A–S, plus cross-language smokes covering 9 languages, plus the M22a
augmentation-effectiveness study + 4-bin re-grade). All run summaries
are committed under
[`experiments/bakeoff/runs-v2/`](experiments/bakeoff/runs-v2/),
[`experiments/bakeoff/runs-m22a-pilot/`](experiments/bakeoff/runs-m22a-pilot/),
and `runs-v3/`. Findings docs synthesize the methodology and headline
results; detailed evidence is per-trial JSON.

A 5-step methodology pattern (independent design review → pre-registration
→ independent-taxonomy check → cross-vendor judge calibration → honest
falsifier verdict) is captured as a process_rule (REQ-3896db58) and
followed by all M22-era studies. It earned its keep 4-for-4 in the
M22 arc — caught fatal flaws in two pre-launch designs and produced
honest "refined" / "partially refuted" verdicts in the run studies.

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

A second, complementary claim from the M22a augmentation-effectiveness
study (Headline Finding 4 below):

> *"Loom-augmented prompts enable confident scope-aware decisions
> — committed action with explicit reasoning about why a stored
> constraint does or doesn't apply — at rates 6-7× higher than
> equally-long irrelevant context or no context. The value is not
> 'pause more,' it's 'know what to proceed with and why.'"*

### Top-line numbers (cumulative across all phases)

| measure | value |
|---|---|
| Total trials | **~1,050+** across the bake-off series |
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

**D2 vs D3 = 0 % vs 95 %** — same data in the Loom store, only the
task linkage differs. The +95pp lift comes entirely from including
the spec text in the executor's prompt body via `task_build_prompt`.
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

### Headline finding 3: drift warnings can be tuned for high recall + low FPR (M13.7)

The locked **m13_v1** evaluation set — 170 stratified scenarios across
21 (stratum × edit_type) cells — measures whether `loom check` /
`loom context`'s drift surfacing actually produces correct
pause/proceed decisions on a downstream agent. Three strata:
`should_pause` (drift truly relevant), `should_proceed_no_drift`
(no upstream drift in context), `should_proceed_fp_trap` (drift
present in context but unrelated to the edit).

| variant | recall (should_pause) | FPR (fp_trap) | FPR (no_drift) | F1 strict |
|---|---|---|---|---|
| no_signal (drift hidden from context) | 85.3 % | 18.0 % | 2.0 % | 0.859 |
| no_warning (drift surfaced, no warning text) | 100 % | 18.0 % | 2.0 % | 0.944 |
| bare_rule ("Drift detected on REQ-X") | 100 % | 20.0 % | 2.0 % | 0.932 |
| **v2 (M13.6d, L9 imperative, no scope)** | 100 % | **48.0 %** | 2.0 % | **0.855** |
| **v3 (M13.7d, L9 + scope qualifier — current production)** | **100 %** | **12.0 %** | 2.0 % | **0.965** |

Wilson 95 % CIs on v3: recall ≥ 94.8 %, fp_trap FPR 4.5–24.1 %,
no_drift FPR 0.1–10.5 %. Run on qwen3.5/temp=0; cross-model
replication (Anthropic Haiku) is queued.

**The honest framing.** The counterfactual ablation (M13.7e)
falsified the original "L9 imperative pattern transfers to drift
warnings" claim — four simpler variants match v3 within 3-5pp F1
at 27-31% lower prompt length. v2 is the *outlier* among
warning-bearing variants, not v3 the breakthrough; the L9 imperative
naively applied actively over-fires without scope guards. The
load-bearing mechanism is **structural drift surfacing** (the
`GRAPH-DRIFT` flag + foundation-drift section in `loom context`,
M13.5a-c) — warning text refinements are second-order.

Detail: [`FINDINGS-bakeoff-v3-scope-qualifier.md`](experiments/bakeoff/FINDINGS-bakeoff-v3-scope-qualifier.md), with [`FINDINGS-bakeoff-v3-drift-effectiveness.md`](experiments/bakeoff/FINDINGS-bakeoff-v3-drift-effectiveness.md), [`FINDINGS-bakeoff-v3-evidence-dependent.md`](experiments/bakeoff/FINDINGS-bakeoff-v3-evidence-dependent.md), and [`FINDINGS-bakeoff-v3-payload-sharpening.md`](experiments/bakeoff/FINDINGS-bakeoff-v3-payload-sharpening.md) for the M13.6 ablation pipeline.

### Headline finding 4: loom rationale → scope-aware proceeding, not just pausing (M22a-pilot + 4-bin re-grade)

The augmentation effectiveness study (N=120 across 4 arms on m13_v1
scenarios, qwen3.5 subject) plus a pre-registered 4-bin re-grade
refined what loom-augmentation actually does. Both reports are
honest-null-friendly: pre-registered falsifiers, locked exclusions,
independent-taxonomy check, cross-vendor judge calibration.

| arm | engaged-with-context | proceeded_with_reasoning |
|---|---|---|
| **hook** (loom production payload) | **93.1 %** (27/29) | **41 %** (12/29) |
| placebo (length-matched irrelevant project text) | 70.6 % (12/17) | 6 % (1/17) |
| pre_loaded (project-docs preamble) | 62.5 % (5/8) — N too small | 25 % |
| no_context (bare task) | 25.9 % (7/27) | 0 % |

Two surprises beyond the original binary-grader story:

* **Most of the "loom helps" lift is "any project context primes
  engaged behavior."** Placebo (length-matched irrelevant project
  text) drives +50pp engagement over no_context — paired McNemar
  p=0.008. Loom's structured rationale adds a smaller increment
  (+17.6pp over placebo, NS at n=17 paired).
* **Loom uniquely enables `proceeded_with_reasoning`.** Hook
  produces "committed to action AND explained why scope doesn't
  apply" responses in 41% of trials; placebo and no_context get ≤6%.
  The loom value-prop at this measurement level is not "pause more"
  but "know what's safe to proceed with, and explain why."

**Refined value-prop framing:**
* *Original*: "loom rationale → more cautious behavior"
* *Refined*: **"loom rationale → confident scope-aware decisions,
  including knowing what to safely proceed on"**

Detail: [`FINDINGS-bakeoff-m22a-pilot.md`](experiments/bakeoff/FINDINGS-bakeoff-m22a-pilot.md), the pre-registered [`REGRADE_PREREGISTRATION.md`](experiments/bakeoff/m22a_pilot/REGRADE_PREREGISTRATION.md), and the 4-bin re-grade writeup [`FINDINGS-bakeoff-m22a-regrade.md`](experiments/bakeoff/FINDINGS-bakeoff-m22a-regrade.md).

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
| Length-matched placebo rules out token-count confound (F1) | M22a-pilot | **Partially refuted by re-grade.** Binary grader showed placebo ≈ no_context (45.8 % vs 48.3 %). 4-bin re-grade showed placebo engages with project context at 70.6 % vs no_context's 25.9 % (paired McNemar p=0.008). "Any project context primes engaged behavior" is most of the lift; loom's structured rationale adds a smaller increment. |
| Hook signal beyond token-count is statistically significant (F2) | M22a-pilot | **Refined, not confirmed.** Re-grade hook vs placebo: +17.6pp engaged-with-context, direction-positive but McNemar p=0.45 at n=17 paired. Magnitude smaller than binary grader claimed. Loom-specific signal exists but underpowered at pilot N. |

### Documents

- **[`FINDINGS-bakeoff-m22a-pilot.md`](experiments/bakeoff/FINDINGS-bakeoff-m22a-pilot.md)** + **[`FINDINGS-bakeoff-m22a-regrade.md`](experiments/bakeoff/FINDINGS-bakeoff-m22a-regrade.md)** — **M22 augmentation-effectiveness arc.** Pilot (4-arm, 120 trials) showed suggestive lift; 4-bin re-grade pre-registered with falsifiers refined F2 and partially refuted F1. Together they ground Headline Finding 4. The re-grade's [`REGRADE_PREREGISTRATION.md`](experiments/bakeoff/m22a_pilot/REGRADE_PREREGISTRATION.md) is the working template for future loom-effectiveness studies.
- **[`FINDINGS-bakeoff-m22b-design-review.md`](experiments/bakeoff/FINDINGS-bakeoff-m22b-design-review.md)** — M22b multi-file pilot designed-but-not-run after methodology-review sub-agent caught three structural blockers (factual error + answer-leak + reference-file leak). γ-pivot demonstrates the pre-launch review pattern saving 1-2 weeks of harness work on a flawed design.
- **[`FINDINGS-bakeoff-v3-scope-qualifier.md`](experiments/bakeoff/FINDINGS-bakeoff-v3-scope-qualifier.md)** — **the M13.7 headline.** v3 scope-qualified drift warning closes the v2 over-firing gap on the locked m13_v1 set.
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
- **Specification layer (required intermediate)** — Detailed HOW for each requirement; the anchor for tasks and implementations. As of **M25 (REQ-7df25683)**, requirements MUST link to implementations through a `Specification`; direct `Requirement → Implementation` links are rejected by `loom link` with a citation to the rule. `loom doctor` warns on any legacy direct links left over from pre-M25 stores.
- **Local web UI (M23)** — `loom ui -p <project>` starts a read-only FastAPI server on `localhost:8090` with HTML views for reqs / findings / specs / files plus semantic search and `/api/*` JSON mirrors. Opt-in via `pip install loom-cli[ui]`. Server-rendered, no JS build step, single-project per server start.
- **Team-shareable text snapshot (M24)** — `loom export` writes `.loom/*.jsonl` (one file per kind, sorted by id, canonical field order, LF newlines) into the repo; `loom import` materializes it into another developer's local store, auto-rebuilding embeddings via the configured provider. The SQLite store stays per-developer in `$HOME`; `.loom/` is the canonical text that travels with the repo. Embeddings, audit logs, and `Implementation.content` excluded by design. Round-trip is byte-deterministic (modulo manifest timestamp). Format locked in [`docs/specs/M24_LOOM_EXPORT_FORMAT.md`](docs/specs/M24_LOOM_EXPORT_FORMAT.md).
- **Pattern entity** — Shared design standards applied across multiple requirements.
- **Task entity** — Atomic, dependency-ordered work items with lifecycle (pending → claimed → complete | rejected | escalated) and atomicity budget (≤2 files, ≤80 LoC by default).
- **Semantic search** — Find requirements by meaning via Ollama embeddings (`nomic-embed-text`, 768-dim).
- **Conflict detection (LLM-verified)** — Embedding overlap surfaces candidates; an LLM pass confirms real conflicts before they're reported.
- **Drift detection** — Content hashes on `Implementation` records let `loom check` flag code linked to superseded requirements.
- **Traceability** — `loom trace`, `loom chain`, `loom coverage` give bidirectional req ↔ spec ↔ impl ↔ test visibility.
- **Living documentation** — `loom sync` generates REQUIREMENTS.md and TEST_SPEC.md with a traceability matrix; PRIVATE.md filters sensitive reqs from public docs.
- **Hook instrumentation** — `hooks/loom_pretool.py` injects Loom context (rule + rationale) as a system-reminder on Edit/Write; logs per-fire latency and bytes to JSONL.
- **Cost measurement** — `loom cost` reports p50/p95/p99 hook latency, total injected bytes, and skipped-vs-fired ratio.
- **Effectiveness metrics** — `loom metrics` aggregates an event log into coverage / drift / conflicts / activity / staleness counts; `loom health-score` rolls them into a single 0-100 number for CI gating.
- **Hygiene** — `Requirement.last_referenced` is stamped passively by every read/link operation; `loom stale` surfaces cold requirements; `loom archive` retires them (recoverable) without forced deletion.
- **Pluggable embeddings** — Three providers: `ollama` (default, `nomic-embed-text` 768d), `openai` (`text-embedding-3-small` 1536d), `hash` (deterministic). Selectable via `--embedding-provider`, env, or config. The store pins `embedding_dim` on first write and rejects mismatched providers.
- **Spec → task decomposition** — `loom decompose SPEC-xxx --apply` uses a frontier model (or local fallback) to emit atomic tasks with full context bundles.
- **Small-model task execution** — `loom_exec` claims the next ready task, calls Ollama, applies code to a scratch copy, runs grading tests, and promotes on pass.
- **Research mode (kinds + per-kind lifecycles)** — Every entry carries a `kind` (`requirement` / `finding` / `methodology` / `process_rule` / `hypothesis`); each kind has its own lifecycle (e.g. findings: proposed → refined → confirmed → falsified) and its own renderer. `loom sync` emits FINDINGS.md / METHODOLOGY.md / PROCESS-RULES.md / HYPOTHESES.md alongside REQUIREMENTS.md (M12).
- **Intake hook (chat → store)** — `hooks/loom_intake.py` is a `UserPromptSubmit` hook that classifies the user's message kind-aware (M12.5), runs `loom related` to find semantic neighbors, and routes to one of six branches (auto-link / propose / captured-with-rationale / rationale-needed / duplicate / no-op). Three guardrails (softener detection, domain whitelist, daily auto-link budget) keep auto-capture clean, plus **four lexical screens** (session-scoped phrases / scenario-paste / tool-docs / speculation) for the M14.2 noise-pollution fix that took dogfooded intake precision from 55 % to 100 % on the audit corpus. Logs to `.intake-log.jsonl`; `loom intake-stats` rolls it up (M11.5).
- **Provisional capture + triage (M14.3-.4)** — Intake captures can land in a `provisional` status (opt-in via `LOOM_INTAKE_PROVISIONAL=1`) that's hidden from REQUIREMENTS.md until promoted. `loom triage --json` surfaces the backlog; `loom doctor` warns when the queue exceeds `LOOM_PROVISIONAL_BACKLOG_WARN` (default 10).
- **Requirement lifecycle (M15)** — `kind=requirement` entries follow a strict transition graph (`pending → in_progress → implemented → verified`) with three auto-advance hooks (first `loom link` → in_progress; `loom verify` on a passing test spec → implemented; `loom verify-stable` after N drift-free days → verified). Multi-hop `set-status` fast-forwards through legal edges and records one `status_changed` event per hop in `.loom-events.jsonl`. Manual transitions soft-require `--reason`. Other kinds (finding/methodology/hypothesis/process_rule) keep free per-kind enums.
- **POSIX-relative impl paths (M17.1)** — `loom link` stores POSIX-relative paths from the project root so impl rows round-trip cleanly across machines. Out-of-root paths stay absolute. Migration script provided.
- **Line-range rendering + hook auto-capture (M16)** — Doc renderer surfaces line ranges as `path:42-87` (GitHub-permalink style) when available; the PreToolUse hook auto-captures the edited line range from Edit/MultiEdit tool inputs and logs it to `.hook-log.jsonl` (just-log, not auto-link).
- **Supersession workflow closure (M20.1)** — `loom unlink <file>` removes implementation rows; `loom supersede` enumerates affected impls and suggests cleanup commands. Closes the drift-signal-without-affordance gap.
- **Idempotent doc sync (Fix A)** — `loom sync` skips writing files when only the auto-generated timestamp differs. Keeps `git status` clean after no-op regenerations.
- **Rationale tracking** — `Requirement.rationale` (free text) plus `rationale_links` (M11.1) form a DAG of "why" pointers. `loom chain` traverses both directions (M12.4); `loom audit-rationale` previews the impact of `LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=1` before flipping it (M11.4). `loom needs-rationale` lists captures missing both prose and links.
- **Semantic indexers** — Pluggable `SemanticIndexer` registry (M10) injects a structured **Semantic context** block into `loom_exec` prompts and powers a structural-drift channel in `loom check`. Shipped: an LSP-backed `JsIndexer` (TypeScript / JavaScript via `typescript-language-server`), an LSP-backed `PyIndexer` (Python via `python-lsp-server` invoked through `[sys.executable, "-m", "pylsp"]`, M16.3), plus stub indexers for C/C++/JS. `loom indexer-doctor` health-checks the pipeline.
- **Driftgraph integration (warrants + foundation drift)** — Outbound: every captured finding / methodology / process rule can be pushed as a Toulmin@v1 (M13.L2) or Falsifiability@v1 (M13.L3d) warrant with claim-id tracking, retract / supersede cascade. Inbound: a three-tier channel (cache → HTTP → Cypher fallback, M13.5a-e) surfaces upstream claim invalidations as a `GRAPH-DRIFT` flag in `loom context`, with a scope-qualified warning prompt that lifts F1 to **0.965** at 100 % recall on the locked m13_v1 evaluation set (M13.7d).
- **Drift-warning evaluation harness** — `experiments/bakeoff/v3_driver/` ships a four-tool lifecycle (`m13_eval_curate.py` / `_lock.py` / `_runner.py` / `_compare.py`) plus the locked m13_v1 set (170 stratified scenarios across 21 cells). `m13_run_counterfactual.py` runs prompt-variant ablations against pinned baselines (M13.7e).
- **MCP server** — Phase A (read) and Phase B (write) tools shipped; wraps `LoomStore` as typed MCP tools for Claude Code and other clients. See [`mcp_server/README.md`](mcp_server/README.md).

## Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running on `localhost:11434` (default
  embedding provider; opt out with `--embedding-provider openai|hash`)
  - `nomic-embed-text` — embeddings
  - `qwen3.5:latest` — recommended local executor (see findings above)
- SQLite (stdlib via `sqlite3` — no separate install)
- Optional: `ANTHROPIC_API_KEY` in the environment if you want Opus-driven
  decomposition; `OPENAI_API_KEY` if you want OpenAI embeddings.

### From PyPI (once published)

```bash
pip install loom-cli
ollama pull nomic-embed-text
ollama pull qwen3.5:latest    # for loom_exec
```

This registers two console scripts on PATH: `loom` and `loom_exec`.

### From a clone (development / pre-release)

```bash
git clone https://github.com/jsuppe/loom.git
cd loom
python3 -m venv .venv
. .venv/bin/activate          # or .venv/Scripts/activate on Windows
pip install -e '.[dev]'       # editable install + pytest
ollama pull nomic-embed-text
ollama pull qwen3.5:latest
```

`pip install -e .` exposes `loom` and `loom_exec` on PATH inside the
venv. The legacy `scripts/loom` and `scripts/loom_exec` shims still
work if you'd rather not install (they `sys.path`-bootstrap the
package).

## Quick start

For a guided walk-through with success indicators at each step, see
**[`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md)**. The
condensed path:

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

# Effectiveness telemetry
loom cost          # PreToolUse hook latency / overhead
loom metrics       # coverage, drift, conflicts, activity, staleness
loom health-score  # single 0-100 score for CI gates

# Hygiene
loom stale --older-than 90 --json   # cold + unlinked requirements
loom archive REQ-xxx                # excluded from list/query (recoverable)

# Browse via web UI (opt-in: pip install loom-cli[ui])
loom ui          # serves http://localhost:8090 — reqs / findings / specs / files + search

# Share with the team
loom export                          # write .loom/*.jsonl into the repo
git add .loom && git commit -m "loom: snapshot"
# ...teammate pulls, then:
loom import                          # materialize into their local store + rebuild embeddings
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
| `extract`                | Parse `REQUIREMENT: domain \| text` from stdin (`--rationale`, `--derives-from REQ-xxx`) | — |
| **`related <text>`**     | Find existing requirements semantically related to a query (M11.1)   | yes      |
| **`needs-rationale`**    | List requirements captured without rationale or links (M11.1)        | yes      |
| **`intake [--text]`**    | Manually run the intake hook on a chat message (M11.5)               | yes      |
| **`intake-stats`**       | Aggregate intake-hook activity from `.intake-log.jsonl` (M11.5)      | yes      |
| **`audit-rationale`**    | Preview impact of `LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=1` (M11.4)    | yes      |
| **`indexer-doctor`**     | Health-check the semantic-indexer pipeline (M10.5)                   | yes      |
| **`ui`**                 | Start the local web UI on localhost:8090 (M23). Opt-in extra: `pip install loom-cli[ui]` | — |
| **`export`**             | Write `.loom/*.jsonl` team-shareable snapshot into the repo (M24). Excludes embeddings + audit logs by design | yes |
| **`import`**             | Materialize `.loom/*.jsonl` into the local store (M24). Default errors on conflict; `--force` / `--merge` opt in. Auto-rebuilds embeddings | yes |
| `check <file>`           | Multi-channel drift detection: content / structural / superseded (M10.4) | yes  |
| `context <file>`         | Pre-edit briefing: linked reqs, specs, drift, GRAPH-DRIFT (used by the hook) | yes |
| `link <file>`            | Link code to reqs (`--req`), specs (`--spec`), or symbol (`--symbol --language`); `--lines` for ranges (M16)  | —        |
| **`unlink <file>`**      | Remove an impl link (`--req` for per-req; otherwise whole-impl). Closes the supersession workflow loop (M20.1) | —      |
| `status`                 | Project overview with drift summary                                  | yes      |
| `query <text>`           | Semantic search                                                      | yes      |
| `list`                   | List requirements                                                    | yes      |
| `sync`                   | Regenerate REQUIREMENTS.md + TEST_SPEC.md                            | —        |
| `conflicts --text`       | Detect conflicting/overlapping reqs (LLM-verified)                   | yes      |
| `supersede <id>`         | Mark a requirement as superseded                                     | —        |
| **`archive <id>`**       | Mark a requirement as archived (recoverable; hidden from list/query) | —        |
| **`stale`**              | Rank requirements by `last_referenced` (`--older-than`, `--unlinked`)| yes      |
| `test` / `verify` / `tests` / `test-generate` | Manage test specs                               | `tests`  |
| `trace <target>`         | Bidirectional traceability (req↔files)                               | yes      |
| `chain <req_id>`         | Full traceability chain (req→patterns→specs→impls→tests)             | yes      |
| `coverage`               | Show requirements missing implementations or tests                   | yes      |
| `refine` / `set-status` / `incomplete` | Elaborate and status-manage reqs. `set-status` enforces a strict transition graph for kind=requirement with fast-forward + audit-log events (M15) | —        |
| **`triage [--json --kind --limit]`** | Surface provisional intake captures awaiting promotion (M14.4)   | yes      |
| **`verify-stable [--apply --days]`** | Promote implemented requirements to verified when drift-free for N days (M15.2) | yes |
| `spec` / `specs` / `spec-link` | Specification management                                       | `specs`  |
| `pattern` / `patterns` / `pattern-apply` | Shared design patterns                               | `patterns` |
| `doctor`                 | Health checks (Ollama, store, orphans, drift, coverage)              | yes      |
| **`init`**               | Onboard a target repo: write `.loom-config.json` + health-check      | —        |
| `init-private`           | Create `PRIVATE.md` template                                         | —        |
| **`cost`**               | Summarize PreToolUse hook cost (latency, bytes, overhead)            | yes      |
| **`metrics`**            | Effectiveness rollup: coverage, drift, conflicts, activity, staleness (`--since N`) | yes |
| **`health-score`**       | Single 0-100 score for CI gates (impl + test + freshness + non-drift) | yes      |
| **`task`**               | Atomic work-item CRUD (`add`/`list`/`show`/`claim`/`release`/`complete`/`reject`/`prompt`) | yes |
| **`decompose <SPEC>`**   | Propose atomic-task decomposition (`--apply` persists)               | —        |

The top-level CLI also accepts `--embedding-provider {ollama,openai,hash}`
to switch the embedding backend per call (default: `ollama`; falls back
to env `LOOM_EMBEDDING_PROVIDER`, then `.loom-config.json::embedding_provider`).

Separate entry point for execution:

| Tool         | Purpose |
|--------------|---------|
| `loom_exec`  | Drive Ollama against the Task queue. Flags: `--next`, `--loop`, `--dry-run`, `--model`, `-p`. Default model from `LOOM_EXECUTOR_MODEL`, falling back to `qwen3.5:latest`. (Also runnable as `python -m loom.exec_cli` or via the `scripts/loom_exec` shim.) |

Project is auto-detected from the git repo name; override with `-p/--project` or the `LOOM_PROJECT` env var.

## Per-project configuration (`.loom-config.json`)

`loom init` writes a `.loom-config.json` at the root of the target repo. It pins defaults so you don't have to pass `-p` / `--target-dir` / `--model` on every invocation. Precedence for every setting: **CLI flag > environment variable > `.loom-config.json` > built-in default.**

```json
{
  "project": "myapp",
  "target_dir": ".",
  "decomposer_model": null,
  "executor_model": "qwen3.5:latest",
  "embedding_provider": null,
  "embedding_model": "nomic-embed-text",
  "test_runner": "pytest",
  "test_dir": "tests",
  "ignore": [".git", "__pycache__", ".venv", "venv", "node_modules", ...]
}
```

`embedding_provider` is one of `ollama` (default), `openai`, or `hash`.
`null` → resolve via `LOOM_EMBEDDING_PROVIDER` env, then default to
`ollama`. Per-provider model defaults: `nomic-embed-text` (768d) for
ollama, `text-embedding-3-small` (1536d) for openai, `hash:768` for
the deterministic provider.

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

- **Requirement** — `id`, `domain`, `value`, `rationale`, `status` (pending/in_progress/implemented/verified/superseded/**archived**), `acceptance_criteria`, `elaboration`, `test_spec_id`, `source_msg_id`, `source_session`, `timestamp`, `last_referenced` (stamped by `query`/`check`/`link`/`trace`/`chain`), optional `superseded_at`.
- **Specification** — Detailed HOW for a `parent_req`. Status: draft/approved/implemented/verified/superseded.
- **Pattern** — Shared design standard with an `applies_to` list.
- **Implementation** — Code chunk linked to reqs/specs with a content hash (drift detection).
- **Task** — Atomic work item. Fields: `title`, `files_to_modify`, `test_to_write`, `context_reqs`/`specs`/`patterns`/`sidecars`/`files`, `size_budget_files`, `size_budget_loc`, `depends_on`, `status`, `claimed_by`, `claimed_at`, `completed_at`, `rejected_reason`, `escalated_reason`, `created_by`, `parent_spec`.
- **TestSpec** (JSON-backed, not in the SQLite store) — steps, expected outcome, automated flag, links to reqs/specs.

Six entity tables in `loom.db`: `requirements`, `specifications`, `patterns`, `implementations`, `chat_messages`, `tasks`. Each row carries `id` (PK), `embedding` (BLOB), `metadata` (JSON), `document` (TEXT). Brute-force cosine similarity for nearest-neighbor search — no HNSW indexing.

A seventh small table, `_loom_meta`, pins per-store invariants —
notably `embedding_dim`, recorded on the first vector write so a
provider switch (e.g. `ollama` → `openai`) can't silently corrupt
search. Mismatched writes raise `EmbeddingDimensionMismatch` with
actionable advice.

## Source of truth

```
Loom Store (SQLite at ~/.openclaw/loom/<project>/loom.db)     ← per-developer authoritative
    ↓ loom sync                          ↓ loom export
REQUIREMENTS.md + TEST_SPEC.md         <repo>/.loom/*.jsonl    ← team-shareable canonical text
+ FINDINGS.md + …                            ↓ git push / git pull
(generated — do NOT edit by hand)            ↓ loom import
                                       Another developer's local store
```

To modify requirements: `loom extract` / `loom refine` / `loom supersede` — never edit generated files. To share with the team: `loom export` then commit `.loom/` to the repo. The next developer runs `loom import` to materialize it into their own SQLite store; their own local edits go back through `loom export` → commit → PR.

## Privacy

Create `PRIVATE.md` in your project to exclude sensitive requirements from public docs:

```markdown
# Private Requirements
- REQ-abc123 — Internal security policy
- REQ-def456 — Proprietary algorithm details
```

Generate public docs: `loom sync --public`.

## Data storage

Two locations: a per-developer SQLite store in `$HOME`, and a team-shareable text snapshot in the repo.

```
~/.openclaw/loom/<project>/        # per-developer, source of truth
├── loom.db                  # SQLite — 6 entity tables + _loom_meta
├── .loom-specs.json         # Test specifications
├── .loom-events.jsonl       # User-meaningful event log (M5: feeds `loom metrics` + `loom health-score`)
├── .hook-log.jsonl          # PreToolUse hook activity log (feeds `loom cost`)
├── .intake-log.jsonl        # UserPromptSubmit intake-hook activity log (feeds `loom intake-stats`)
├── .exec-log.jsonl          # loom_exec run log
└── PRIVATE.md               # Private requirement IDs

<repo-root>/.loom/                  # team-shareable, committed to the repo (M24)
├── manifest.json            # schema version + git_head + entity counts
├── requirements.jsonl       # one entity per line, sorted by id, canonical field order, LF newlines
├── specifications.jsonl
├── patterns.jsonl
├── implementations.jsonl
└── test_specs.jsonl
```

`loom export` writes the `.loom/` snapshot; `loom import` materializes it into another developer's `~/.openclaw/...` store and rebuilds embeddings. Embeddings, audit logs (`*.jsonl`), `Implementation.content`, and `last_referenced` are intentionally excluded from the snapshot — they're either regenerable, per-developer telemetry, or recoverable from disk.

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
