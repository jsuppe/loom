# Bakeoff V1 — Protocol

**Pre-registered:** 2026-04-24, before the harness is built.
**Purpose:** Measure whether making Loom available to an engineer-agent
measurably improves the outcome of a collaborative build session against
a fixed ground truth.

This document exists to commit to the experimental design *before* we
see any data. Anything we change after pilot runs must be documented as
an amendment with date.

---

## Hypothesis (primary)

> When two agents (product owner A, engineer B) collaborate through
> turn-based conversation to implement a pre-defined project, giving
> Agent B access to Loom tools (capture, spec, decompose, check, link,
> exec) improves the build outcome over a baseline with only file I/O
> and a test runner.

"Improves the build outcome" is operationalized via the primary metrics
below. The alternative hypothesis is specifically that **one or more of
the primary metrics shows a statistically meaningful positive shift**
in the Loom condition relative to the baseline condition.

## Null hypothesis

> Making Loom tools available to Agent B produces no measurable
> improvement on any primary metric, within the sample size and effect-
> size detectability of this experiment.

A null result is a valid outcome. It signals the thesis needs reshaping,
not a problem to bury.

---

## Experimental design

### Setup

| Role | Knows | Never reveals | Accepts | Tools |
|---|---|---|---|---|
| **A (Product Owner)** | Full ground-truth spec + test suite | The test file content, the full spec at once | B's code diffs + test results | Conversational only (no code) |
| **B (Engineer)** | Only what A has said in conversation + current repo state | — | A's directives | baseline: read_file, write_file, run_tests · loom: add loom_extract, loom_spec, loom_decompose, loom_check, loom_link, loom_exec |

### Models

Same model for A and B in every run:
- **qwen3.5:latest** via Ollama (local, ~$0/run).

Chosen for V1 because (a) it's the model we've validated for `loom_exec`
elsewhere, and (b) zero API cost removes budget as a confound in the
pilot iterations. The V1 experiment directly tests the thesis of
interest: *does structured memory measurably help a small-local-model
agent-to-agent collaboration?*

V2+ (explicitly deferred): same protocol against larger cloud models
(Claude Sonnet 4.6, Opus 4.7) to test whether any observed effect
generalizes upward in capability.

### Ground-truth project

One project for V1: **TaskQueue library** (details in
`ground_truth/README.md`). Target scope: ~200 LoC of library code +
~15 pytest test cases across 6 declared requirements. Chosen because:
- Pure Python — no stack-specific confounds.
- Small enough that runs finish in < 30 iterations.
- Enough cross-method coupling to allow regressions (e.g. changing
  priority semantics can break filter behavior).
- Deterministic test suite — no flaky tests.

### Turn mechanic

1. A speaks first with an opening directive.
2. B reads, may call tools, eventually produces a code update and a
   reply to A.
3. Driver applies B's write_file calls to the workspace.
4. Driver runs the full test suite.
5. Results (passed/total plus per-test pass/fail delta since previous
   iteration) are given to A.
6. A produces the next turn's directive (may be a clarification, a
   correction, or a new feature).
7. Repeat until a stop condition fires.

### Stop conditions (first to hit wins)

- `all_tests_pass`: every ground-truth test passes.
- `max_iterations = 25`: guardrail against infinite loops.
- `token_budget_per_run = 500_000 total` (A+B combined).
- `no_progress`: 3 consecutive iterations with no passing-test delta.

All four are checked after every iteration.

---

## Metrics

### Primary (what we're testing)

| Metric | Definition |
|---|---|
| **final_pass_rate** | Fraction of ground-truth tests passing at stop time. `[0, 1]`. |
| **iterations_to_80pct** | Number of A↔B turn pairs before `pass_rate ≥ 0.8`. `None` if never reached. |
| **total_tokens** | Sum of `input + output` tokens across all A and B API calls. |
| **regression_count** | Number of `(previously_passing → failing)` test transitions across the run. |

### Secondary (diagnostic)

| Metric | Definition |
|---|---|
| `iterations_total` | Turn count when run stopped. |
| `a_tokens` / `b_tokens` | Split by agent. |
| `messages_total` | Total turns (typically `2 × iterations_total`). |
| `stop_reason` | One of the stop conditions above. |
| `loom_tool_calls` | Treatment only — count of each Loom tool invoked. |
| `mean_code_diff_size` | Average LoC changed per iteration. |

Secondary metrics are for diagnosis. We do not run significance tests
on them — we report them.

---

## Statistical method

- **Per primary metric**: two-sided Mann-Whitney U test between the
  two conditions. Non-parametric; doesn't assume normality.
- **Effect size**: Cliff's delta (non-parametric effect size for
  ordinal data).
- **Reported**: median per condition, IQR, U statistic, p-value,
  Cliff's delta with interpretation (negligible / small / medium / large).
- **Multiple comparisons**: Holm-Bonferroni correction across the four
  primary metrics.
- **Alpha**: 0.10 (not 0.05 — we have small N and are looking for signal,
  not precision; generous alpha avoids under-powering false negatives).

We do not compute CI's; with N=5 per condition that's too wide to be
meaningful. Direction + effect size is what we report.

## Sample size

- **V1 real run**: N = 5 per condition (10 total runs).
- **Pilot**: N = 1 per condition (2 total runs), discarded.

Rationale: N=5 is weak statistical power and only detects large effects
(Cliff's delta > ~0.8). If we see no signal at N=5, we expand to N=10
before declaring the null. If we see strong signal at N=5, that's the
floor and we accept it.

Budget:
- Ollama qwen3.5 is local. Budget = wall-clock time and the laptop's
  thermal headroom, not $.
- Typical run: ~15 iterations × ~3K tokens each × 2 agents ≈ 90K tokens
- qwen3.5 on this machine: ~2s per ~200-token generation, so roughly
  5 minutes/run, ~1 hour for N=10.

---

## Controls against common experimental bugs

### Fair baseline
Both engineer agents have identical tool surfaces minus Loom. No
artificial constraints on the baseline (e.g., no banning of iteration,
no forced one-shot). If Loom wins, it wins because the Loom-specific
tools helped, not because the baseline was sandbagged.

### Info leakage via Loom
Rule for Agent A: **never capture a req or spec into Loom until that
req or spec has been revealed to B in the current conversation.** This
is a PO-prompt constraint. We'll audit the Loom store after each
treatment run to verify no reqs/specs exist that weren't in the
conversation transcript.

### Test-suite contamination
The ground-truth test suite is NEVER shown to Agent B. Agent A sees
test results (passed/total + per-test delta), not test source. This
mirrors how a real PO relays results without dictating implementation.

### Same initial state
Each run starts from a fresh workspace — scaffolded package skeleton,
no implementation. Identical starting point between conditions.

### Independence across runs
No state carries between runs. Each run creates a fresh tempdir, a
fresh Loom store (treatment only), a fresh conversation history.

---

## Pre-committed analysis plan

After the N=5 real run:

1. Compute each primary metric per run.
2. Apply Mann-Whitney + Cliff's delta per primary metric.
3. Apply Holm-Bonferroni correction.
4. Report medians, IQRs, U, p, delta, corrected-p per metric.
5. Report secondary metrics per condition as medians + IQR.
6. Write `FINDINGS-bakeoff.md` with:
   - Verbatim primary-metric numbers.
   - Interpretation of the effect for each metric (even if null).
   - What the data tells us about the thesis.
   - What the data does NOT tell us (caveats).
   - Next-step recommendations, whether positive, null, or
     unexpectedly negative.

No p-hacking: we do not run additional tests, add more runs, or change
metric definitions after seeing the data. If we think we need more N,
we commit to doubling N (not "add just a couple more until it's
significant").

---

## Publication commitment

Whatever the result:
- Findings go in `FINDINGS-bakeoff.md`, committed to main.
- If the result is null or negative, the repo's README and ROADMAP get
  updated to reflect the reduced confidence in the thesis.
- No "we ran it and didn't write it up." No "it showed signal but we
  reshaped the experiment." Committed honestly before we ran.

## Known limitations of V1

- **N=5 is small.** Detects only strong effects.
- **One project.** Generalization to other domains untested.
- **One model pair.** Effects may differ for stronger models — V1 uses
  qwen3.5:latest for both agents. V2 should run the same harness
  against Sonnet/Opus to test whether any observed effect holds up,
  diminishes, or reverses at higher capability.
- **Python only.** Multi-runtime was the whole point of recent work,
  but V1 pure-Python keeps fewer moving parts.
- **Single product-owner profile.** A different A prompt shape (terser,
  more verbose, more/less forgiving) could shift outcomes.
- **No human comparison.** We don't compare either condition to a
  human engineer.
- **Tool interface via structured text, not native tool-use API.**
  Ollama's tool-use support varies by model; we use a prompt-based
  protocol (model emits `TOOL:` lines the driver parses). This matches
  how `loom_exec` and `loom decompose` already work, so it's a
  well-trodden path, but it biases toward models that follow
  structured-output instructions well.

Each of these is a direction for V2+ if V1 produces signal worth
investigating. None invalidates V1's result for its stated scope.

---

## Amendments

(None yet. Any change to this protocol after the pilot runs must be
dated and described here.)
