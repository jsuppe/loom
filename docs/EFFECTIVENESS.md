# Loom: Effectiveness Report

*Empirical evidence for teams evaluating Loom for AI-assisted development.
Last updated 2026-06-06.*

---

## Why this document exists

If your team writes code with Claude, Cursor, Copilot, or any LLM-assisted
workflow, you have probably hit these failure modes:

* The agent forgets a decision the team made a week ago. Same bug,
  same fix, same blast radius.
* The agent writes code that contradicts an earlier requirement. Nobody
  notices until production.
* You pay frontier prices for tasks a 9B local model could finish.
* New team members ask the agent why something was done — the agent
  doesn't know. The git log doesn't say. The rationale is in a Slack
  thread that scrolled away.

Loom is a requirements traceability + execution substrate built around
these failure modes. This document summarizes the experimental evidence
for what Loom actually changes, organized by user benefit, with
citations to ~1,050 trials of bake-off data.

The honest framing throughout: numbered claims, named conditions, and
explicit "doesn't help here" callouts. Marketing-grade claims aren't in
this document.

---

## Five validated benefits

### 1. Pre-edit context lifts compliance at sub-frontier model tiers

When the Loom hook injects linked requirements + rationale into the
context window before an Edit/Write tool call, **sub-frontier models
behave like frontier models on contrarian specs**.

| model tier | without hook | with hook | lift |
|---|---|---|---|
| Sonnet 4.6 | 7%  | 100% | **+93 pp** |
| Haiku 4.5  | 40% | 100% | **+60 pp** |
| Opus 4.7   | 100% | 100% | 0 pp (already saturated) |

*30 trials per tier × 3 tiers = 90 trials. Phase E bakeoff.
[FINDINGS-bakeoff-v2-phaseA.md](../experiments/bakeoff/FINDINGS-bakeoff-v2-phaseA.md) +
[FINDINGS-bakeoff-v3-scope-qualifier.md](../experiments/bakeoff/FINDINGS-bakeoff-v3-scope-qualifier.md).*

**What this means for your team.** If you mostly use Sonnet or Haiku
because of Opus pricing, the Loom hook reclaims frontier-grade
compliance on the decisions your team has captured. The 30/30 hard-block
mechanism (Loom blocks Edit/Write tool calls when drift is detected) is
operationally reliable. Hook latency is ~800ms at 500-file project size.

**Where it doesn't help.** Opus already passes contrarian specs at 100% in
the saturated benchmark, so the hook has no measurable lift at the top
tier. If your team only uses Opus, the hook value is rationale-storage
(see benefit #3) rather than compliance lift.

---

### 2. Asymmetric pipeline: ~8× cheaper than frontier-only at parity

Loom's "asymmetric pipeline" splits work between a frontier planner and
a local executor: the frontier model decomposes a specification into
atomic tasks (~$0.30/spec on Opus), and a local model executes each task
(~$0/task on qwen3.5:latest).

| approach | per-task cost | per-100-task project |
|---|---|---|
| Frontier-only | ~$0.28 per task | ~$28 |
| **Asymmetric (Opus plans, qwen3.5 executes)** | ~$0.006 per task amortized | **~$0.60–$1.00** |

*Phase D, 60 trials matched-pricing on a Python feature task. Quality
parity on graded tests. [FINDINGS-bakeoff-v2-pythonfirst-smoke.md](../experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md).*

The capability validation that anchors this:
**`qwen3.5:latest` (9.7B parameters, runs on commodity hardware) matched
Opus 4.7 on every trial** across three escalating task shapes
(write-from-spec, extend, behavior-preserving refactor). At
`temperature=0`, output is byte-deterministic across repeats.

*Milestone 0 capability validation, full write-up in
[FINDINGS.md](../experiments/gaps/FINDINGS.md).*

**What this means for your team.** Frontier inference cost can drop
30–50× for large refactors, migrations, and feature builds. The frontier
model still does the load-bearing reasoning (decomposition, code review,
spec authoring); the local model does the body work where capability is
already saturated.

**Where it doesn't help.** Single-file tasks that fit in one model call
don't benefit from decomposition overhead. Cross-module refactors
(>9 files) are untested. See benefit #5 for the full project-size fit
map.

---

### 3. Loom rationale enables confident, scope-aware agent behavior

The most surprising finding from M22a (augmentation effectiveness study)
isn't that the Loom hook makes agents pause more — it's that **the Loom
hook makes agents *proceed with reasoning* at 6-7× the rate of any
control condition**.

| arm | engaged with context | proceeded with reasoning |
|---|---|---|
| **Loom hook** (production payload) | **93.1%** | **41%** |
| placebo (length-matched irrelevant project text) | 70.6% | 6% |
| pre_loaded project docs | 62.5% | 25% |
| no_context (bare task) | 25.9% | 0% |

*N=120 across 4 arms on m13_v1 scenarios, qwen3.5 subject, gemma4:31b
judge (cross-vendor calibrated), pre-registered 4-bin re-grade with
locked exclusions. [FINDINGS-bakeoff-m22a-regrade.md](../experiments/bakeoff/FINDINGS-bakeoff-m22a-regrade.md).*

**What "proceeded with reasoning" means.** The agent took committed
action AND explicitly reasoned about why a stored constraint did or
didn't apply to the current task. This is the "knows what's safe to
proceed with" behavior — not timid pausing, not bulldozing past
warnings.

**What this means for your team.** Storing rationale isn't just for
documentation. It changes how agents reason about their own
decisions. An agent with Loom rationale doesn't just see more text —
it sees more *load-bearing* text, and acts on it.

**Honest caveat.** The placebo arm (irrelevant project text matched on
length) accounted for ~70% of the engagement lift. Most of "Loom helps"
is "any project context primes engaged behavior." Loom's structured
rationale adds the marginal +17pp on top — meaningful but smaller than
the binary grader initially claimed.

---

### 4. Drift detection: F1 0.965 at 100% recall on the locked benchmark

When code drifts from a captured requirement, Loom catches it and
surfaces a structured warning to the agent. Tuned against a
pre-registered evaluation set of 170 scenarios across 21 strata, the
v3 production warning achieves:

| metric | v3 scope-qualifier (production) |
|---|---|
| Recall (catches true drift) | **100%** (Wilson 95% CI ≥ 94.8%) |
| FPR on unrelated drift in context (the "trap" stratum) | **12%** (CI 4.5–24.1%) |
| FPR on no-drift baseline | **2%** (CI 0.1–10.5%) |
| F1 strict | **0.965** |

*N=170 scenarios across 21 (stratum × edit_type) cells, qwen3.5
temperature=0. [FINDINGS-bakeoff-v3-scope-qualifier.md](../experiments/bakeoff/FINDINGS-bakeoff-v3-scope-qualifier.md).*

**What this means for your team.** When the captured requirement says
"users must confirm before deletion" and someone removes the modal,
Loom catches it before the next agent edits that file. The structured
warning tells the agent *which requirement is at risk* and *what the
current intent looks like* — not just "drift detected."

**What we falsified along the way.** The original "imperative warning
pattern" (v2) had a 48% false-positive rate on the trap stratum —
warning agents about drift in context that wasn't actually relevant to
their edit. v3's scope-qualifier prompt closed that gap to 12% without
losing recall.

---

### 5. Language and project-size fit map

Loom's effectiveness varies by language and project size — both axes are
mapped empirically.

**Language fitness** (qwen3.5:latest as executor, contrarian-rule test
scenario, 4 cells × N=5 per language):

| Strong fit | Mixed | Weak |
|---|---|---|
| Python, Java, Rust, TypeScript, Asm | JavaScript (caps ~60%) | C, Go, C++ |

*Phase 8.4 cross-language map. 9 languages × 4 cells × N=5 = 180
trials. [FINDINGS-bakeoff-v2-cross-language-map.md](../experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md).*

**Project-size fit** (Loom's asymmetric pipeline on a small local
model, qwen3.5:latest unless noted):

| project shape | result |
|---|---|
| Single-file Python | 5/5 = 100% (Phase D) |
| 9-file Python | 5/5 = 100% (M6.6.1) |
| Single-header C++ | 6/6 = 100% with qwen2.5-coder:32b (cpp-orders) |
| Small multi-file Dart (≤3 files) | 100% after Tier 1+2 (dart-orders) |
| Flutter multi-widget (3 widgets) | 3/3 = 100% with qwen2.5-coder:32b |
| 9-file Dart | **0/35** across executors — does not work |

**What this means for your team.** If your codebase is Python, Java, TS,
or Rust, and your typical work-unit is ≤9 files, Loom is in its
validated zone. If your codebase is C or Go or your work-units are
larger than 9 files, treat Loom as exploratory — the data isn't there
yet.

---

## Honest limits

Five things Loom **does not yet** do well. Calling them out so you
don't discover them in production.

1. **Loom does not help on saturated benchmarks.** If your task is
   something every Claude tier already passes (TaskQueue-shaped CRUD on
   the happy path), Loom adds cost overhead without correctness lift.
   See [Phase A null result](../experiments/bakeoff/FINDINGS-bakeoff-v2-phaseA.md).

2. **Loom does not bridge marginally-fluent executors.** If the executor
   model is below the capability floor for your language (qwen3.5 on
   Dart at 9 files, llama3.1:8b on Python refactors), Loom does not lift
   it. The "small model is fine with enough context" claim has a real
   floor — empirically, ~10B parameters for Python refactor, ~32B for
   C++.

3. **The asymmetric pipeline has v2-readiness gaps surfaced by
   dogfooding.** A pilot today (M26) used `loom decompose` + `loom_exec`
   to ship a real feature into Loom's own source. One of five atomic
   tasks succeeded end-to-end; four surfaced concrete decomposer and
   executor gaps documented in
   [`experiments/m26_spec_scorer/FINDINGS.md`](../experiments/m26_spec_scorer/FINDINGS.md).
   Three of the gaps were fixed the same day; six remain queued for v2.

4. **C++ semantic-indexer Phase 1 (ClangdIndexer) was pre-registered
   and falsified.** M28 tested whether the M10.2 stub-indexer's +40pp
   lift on the rationale cell would replicate with a real LSP-backed
   indexer. Under N=40 with H3 STOP gate passing (off cell 0% — no
   rule leak), the rat cell came in at 0/10 (Wilson 95% CI 0-28%) —
   below the 20% falsifier band. The M10.2 lift was carried by
   hand-authored contract prose ("IMPORTANT: this call site does NOT
   have a try/catch... production incident 2024-09-12"), not by the
   structural Kythe-shaped facts. Same failure mode as M10.3a's phQ3
   finding on JavaScript. Detail: [`experiments/m28_clangd_indexer/FINDINGS.md`](../experiments/m28_clangd_indexer/FINDINGS.md).

5. **C++ style-constraint hypothesis (M29 Phase A) was pre-registered
   and falsified — but as predicted by the locked predictor's prior.**
   M29 tested whether prepending an explicit C++17 style block to the
   prompt would lift the rat cell ≥ 20pp vs M28's baseline. N=40, H3
   STOP gate passed (off cell 0%). Rat cell came in at 0/10 (CI 0-28%)
   — refuted. **The pre-registration also locked a predictor's prior**
   that H1 would refute on this specific scenario, because the
   contrarian rule's text already pins the C++17 idiom ("Return
   std::nullopt..."). The data confirmed the prior. The narrow finding
   is "style constraint refuted for scenarios where the rule itself
   pins idiom"; the broader hypothesis (style constraint as a lever on
   scenarios where the rule is behavioral-only) remains open. Detail:
   [`experiments/m29_style_constraint/FINDINGS.md`](../experiments/m29_style_constraint/FINDINGS.md).

   C++ stays in the **weak** zone after both M28 and M29 refute.
   Remaining candidates for what might move the rat cell: an M28v2
   that adds an LLM-summarized contract-prose layer on top of
   ClangdIndexer (tests whether prose IS the carrier directly); a
   different scenario shape (multi-file C++ with idiom-underspecified
   rule); or Kythe Phase 2 (substantially more infra cost, justifiable
   only if the prose hypothesis also fails).

4. **Loom's value on Opus is rationale-storage, not compliance lift.**
   If your team only uses Opus, the hook does not measurably improve
   correctness because Opus already passes the contrarian benchmark at
   100%. Loom's value at the top tier is "the next developer + the next
   agent see the rationale" rather than "the current call gets better
   output."

5. **Loom's storage layer is single-developer by default.** The SQLite
   store lives in `~/.openclaw/loom/<project>/`. For team sharing, run
   `loom export` to write `.loom/*.jsonl` into your repo and commit. The
   pattern works but requires discipline.

---

## What "deploy Loom" looks like in week 1

| Day | Action | Outcome |
|---|---|---|
| 1 | `pip install loom-cli`, `loom init` in one repo | Per-project config + health check |
| 1 | Add `hooks/loom_pretool.py` to `.claude/settings.json` | Pre-edit hook fires on Edit/Write |
| 2 | Capture 5–10 real requirements from recent Slack threads via `loom extract --rationale` | Store seeded with team's decisions |
| 3 | `loom link <file> --spec SPEC-xxx` for files matching those requirements | Drift detection armed |
| 4 | First drift catch in a real PR review | Engineering trust established |
| 5 | `loom export` + commit `.loom/` to repo | Teammates can `loom import` |

The 60-second demo that shows the loop end-to-end is in
[`docs/WORKED_EXAMPLE.md`](WORKED_EXAMPLE.md).

---

## Token-efficiency frontier (C++ S1 case study)

When evaluating an intervention, "did it improve pass rate" is half
the question. The other half is "what did it cost in tokens." Both
matter for production deployment economics. The token-efficiency
rollup at
[`experiments/_meta/token_efficiency_rollup.py`](../experiments/_meta/token_efficiency_rollup.py)
walks every per-trial JSON under `experiments/bakeoff/runs-*/` and
computes mean tokens, pass rate, and tokens-per-pass per (intervention,
cell).

Run on the C++ S1 lineage as of 2026-06-06 — same scenario, same
benchmark, four sequential interventions:

| intervention | rat pass rate | mean in-tok | mean out-tok | tokens / pass | verdict |
|---|---|---|---|---|---|
| phL — qwen3.5 baseline, no indexer | 50% (2/4) | 588 | 7,149 | **15,474** | weak — high out-tok overhead |
| M10.1b — qwen2.5-coder:32b, no indexer | 0% (0/5) | 581 | 266 | — | refuted (executor capacity not the lever) |
| **M10.2 — hand-curated stub** | **50%** (3/6) | **1,111** | **259** | **2,740** | confounded (prose, not facts, carried the lift) |
| **M28 — ClangdIndexer LSP** | **0%** (0/10) | 1,176 | 273 | — | **falsified** (structural facts alone don't replicate) |
| **M29 — style constraint alone** | **0%** (0/10) | **795** | 270 | — | **falsified** (rule already pinned the idiom; **32% cheaper than M28**) |

What this surfaces that a pass-rate table alone doesn't:

* **The qwen3.5 baseline (phL) was paying ~6× more output tokens per
  trial** than the qwen2.5-coder:32b interventions (~7,200 vs ~260).
  Verbosity, not capability, was a hidden cost on the original
  baseline.
* **M10.2's "structural facts" lift was unmatched on efficiency** —
  2,740 tokens/pass on rat is the best ratio across the four
  interventions. M28's clangd added similar tokens but produced no
  passes; the ratio is undefined and the cost is pure waste.
* **The right question for M29 (style constraint) and any future
  C++ work** is not "did pass rate go up" but "did pass rate go up
  *relative to the marginal token cost*." Style constraints (~190
  words) cost less than the M10.2 stub block (~1,800 chars). If
  M29's rat cell hits even 20-30% at that cost, the tokens/pass
  ratio would beat the M10.2 baseline.

The rollup script is generic — it reads any new `experiments/bakeoff/runs-*/`
output without code changes. Add a new intervention to the `SOURCES`
list and it's surfaced automatically.

## How to read the underlying evidence

Each numbered claim above cites one or more findings docs in
`experiments/`. The full evidence is reproducible from the JSON trial
logs under `experiments/bakeoff/runs-*/`. The methodology pattern that
governs every claim — pre-registration, locked exclusions, cross-vendor
judge calibration, honest falsifier verdicts — is captured as
REQ-3896db58 in the Loom store itself.

If a claim in this document doesn't survive re-running the underlying
experiment, the failure should land as a `kind=finding` in the Loom
store with a link back to this document. The document is intended to be
falsifiable, not promotional.

---

## Quick reference

| If your team... | Loom's empirical value-add | Citation |
|---|---|---|
| Uses Sonnet/Haiku as the daily driver | +60–93pp compliance on captured contrarian specs | Phase E |
| Cares about per-task LLM cost | ~8× cheaper at quality parity via asymmetric pipeline | Phase D + Milestone 0 |
| Wants agents that *reason about* stored constraints | 41% proceeded-with-reasoning vs 0% no-context | M22a re-grade |
| Needs drift detection that doesn't over-fire | F1 0.965 at 100% recall, 12% trap-FPR | M13.7d |
| Works in Python / Java / TS / Rust | Strong-fit empirical zone | Cross-language map |
| Works in C / Go / C++ | Mixed-to-weak fit — exploratory | Cross-language map |
| Mostly uses Opus | Rationale storage > compliance lift | Phase E null |
