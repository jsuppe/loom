# M22e Pre-registration — Single-File JS/TS Confound-Elimination Study

**Locked:** 2026-05-25
**Status:** Locked BEFORE harness build (per REQ-3896db58 step 2)
**Methodology-review verdict:** "warning, salvageable with 6 specific changes" — all incorporated here
**Pivot type:** WORKLOAD-arm pivot from M22c, isolating workload as the only changed variable

## Why this pre-reg exists

M22c failed pre-reg gates 2 + 6 (REQ-9f24f46e). The postmortem identified
a specific, measurable confound (REQ-7e2d6518): **100% of M22c trials
hallucinated file paths from training-data 'standard layout' priors**,
flooring all four arms regardless of context — including hook_fact with
literal method signatures in the prompt. The model never looked at the
real `lib/` structure; it generated imports from priors.

M22e is the WORKLOAD-arm pivot. We swap the multi-file Dart workload
for a single-file JS/TS workload where:

* **File layout is explicit in the prompt** (`import { … } from "./X"`
  declared up front) so the layout-hallucination confound from REQ-7e2d6518
  cannot operate.
* Model arm stays = `qwen3.5:latest` (the M22c executor) to isolate
  workload as the changed variable.
* All grading, gates, falsifier thresholds, and integrity rules from
  M22c carry through unchanged where the workload allows.

## Framing — confound elimination, NOT priors matching

This is the most important framing point in the document. M22e is NOT
"we picked a workload where the model's priors happen to match the
layout." That would be a goal-post move and we would not run it.

M22e IS "we identified a *measured* confound (REQ-7e2d6518) that floored
all four arms uniformly, and we constructed a prompt arrangement where
that specific confound cannot operate, holding every other variable
constant." This is scope narrowing for the question:

> "Can hook-rationale beat placebo *when import layout is not the
> bottleneck on a 7B local model*?"

That is a strictly NARROWER question than the M22c original. The writeup
will explicitly say: **findings from M22e generalize only to "single-file
tasks where layout is given in the prompt" — they do NOT generalize back
to multi-file Dart, to other languages, or to other model classes.**

## Locked workload — Option B (single-file JS/TS)

Per reviewer recommendation. Justification:

* **Option A (Python single-function) rejected:** ceiling-bound risk for
  qwen3.5:latest; gate-6-ceiling failure likely.
* **Option C (simple Dart standalone) rejected:** same model + same
  language as M22c is unlikely to lift the floor; capability ceiling
  evidence from M22c (e.g. `m22c_s_order_hook_rationale_t1.txt`
  runaway-comment loop) suggests Dart-specific weakness.
* **Option B accepted:** qwen3.5:latest has strong JS/TS priors but
  they don't dominate to 100% on non-trivial logic; sits in the
  predicted 30-70% sweet spot for compile+test pass rate.

### Workload spec

* **Project shape:** Node.js with native ES modules (`"type": "module"`
  in package.json). Single source file under test. One test file.
* **Test runner:** built-in `node --test`.
* **No external deps** beyond Node stdlib (no test framework deps to
  contaminate model priors; `node --test` is built in 22+).
* **Per scenario:** the model is given the file path it must write,
  the `import` statements it must use (so layout is fixed in prompt),
  and a task description. Model writes one function (or small set of
  related functions) into that file.

### Three locked scenarios

| scenario_id | target_file | task | nature |
|---|---|---|---|
| `s_validate` | `src/validate.js` | implement `validate(input)` that checks an object against a list of declarative rules and returns a `ValidationResult` | input validation w/ error aggregation |
| `s_aggregate` | `src/aggregate.js` | implement `aggregate(events, opts)` that groups events by key, runs reducers, returns summary | data transformation |
| `s_retry` | `src/retry.js` | implement `retry(fn, opts)` async wrapper that retries a failing async function with configurable backoff | async control flow |

Each scenario has an oracle test file at `test/scenario_test.js` with
~20-30 sub-tests covering golden path, edge cases, error handling.

Reference solutions live at `experiments/bakeoff/benchmarks/js-singlefile/`
(to be authored M22e.2). Each reference passes all sub-tests.

## Three locked rationales (style, leak-score 0)

Per the reviewer's leak-shape guidance, valid single-file rationale
shapes are: error-handling discipline, iteration/transformation pattern,
mutation policy. Each rationale below constrains a STYLE choice that
narrows the design space without dictating the signature.

| scenario | style-rationale | what it constrains | leak risk (0-3) |
|---|---|---|---|
| `s_validate` | "Collect ALL validation errors before returning; never throw or short-circuit on the first failure. Callers consume the full error list to display to users." | error-collection style (collect vs short-circuit) | **0** (style only) |
| `s_aggregate` | "Treat inputs as immutable; do not mutate the events array or any event object. Build the result by accumulating new objects in a reducer pass." | mutation policy (pure vs in-place) | **0** (style only) |
| `s_retry` | "Distinguish 'truly retriable' errors (network, timeout, 5xx) from terminal errors (validation, 4xx). Terminal errors must short-circuit and re-throw immediately; only retriable errors get retried with backoff." | error-classification discipline | **0** (style only) |

**Hand-grading:** each rationale has been authored to constrain a style
that does not dictate the function signature. None mentions parameter
names, return types, error class names, or method names of helper
functions.

### LEAK-GRADE GATE — independent reviewer pass

Per reviewer recommendation, an **independent reviewer sub-agent will
blind-grade these three rationales** for signature leakage BEFORE the
harness work begins (M22e.1a). The reviewer will be shown each rationale
+ the corresponding `fact_signature` and asked: "given only this
rationale (no other context), how many of these signature elements
could a competent JS developer reproduce verbatim?"

Pass threshold: **≤1 signature element guessable per rationale.**

If any rationale fails: rewrite. If rewrite cannot pass, drop the
scenario (and the study runs with 2 scenarios, not 3).

## Four arms (unchanged from M22c)

1. **`no_context`** — bare task + the explicit import block (which is
   identical across all arms). Tests baseline: model writes the function
   given only the layout and the task.
2. **`hook_rationale`** — bare task + `<system-reminder>` carrying the
   locked style-rationale. Tests loom's actual value prop.
3. **`hook_fact`** — bare task + `<system-reminder>` carrying the literal
   signature contract (function name, parameter names, return type).
   Upper-bound (answer-in-prompt).
4. **`placebo`** — bare task + length-matched irrelevant text drawn from
   OTHER scenarios' rationales.

**The import block is identical across all four arms.** This is the
operational embodiment of the confound-elimination framing — layout is
constant, the only variable is the rationale/fact envelope.

## Grading (carry-forward from M22c, unchanged)

**Compile/test 4-bin outcome:**
* `compile_fail` — `node --check` rejects the file OR the test file
  fails to load with a SyntaxError / ReferenceError on import
* `link_fail` — file loads but test reports `is not a function` /
  `is not defined` at runtime
* `test_fail` — runs but < (N-1) sub-tests pass (allow 1 flake)
* `test_pass` — ≥ (N-1) sub-tests pass

Plus a continuous sub-test pass rate (passed / N) for granular signal.

**LLM-judged 4-bin response classification** via gemma4:31b (per
REQ-d91fcd71). Calibration set on JS/TS responses (see Judge Calibration).

## Pre-registered floor and ceiling predictions

Per reviewer recommendation, this study pre-registers the expected
no_context floor BEFORE the pilot runs:

* **Predicted no_context compile+test pass rate: 40-65%** on `qwen3.5:latest`.
* If actual lands below 25%: workload too hard (same as M22c, fall
  back to refuted-via-floor path).
* If actual lands above 75%: ceiling-bound, no rationale headroom
  (re-design hide-rule or strip more context).
* If actual lands within [25%, 75%]: gate passes, sweep is in scope.

This prediction is captured here, locked, and the writeup will report
both prediction and actual.

## Sample size

* **Pilot (M22e.3):** 3 scenarios × 4 arms × 2 trials = **24 trials**.
* **Full sweep (M22e.4):** 3 scenarios × 4 arms × 10 trials = **120 trials**.

Larger sweep N than M22c (120 vs 60) because single-file trials run
faster and per-cell power for paired McNemar benefits from 10 trials/cell.

## Primary test (LOCKED — F-hook-rationale, identical to M22c except for workload)

**Metric:** compile+link pass rate (i.e. `compile_fail` and `link_fail`
both excluded; `test_fail` and `test_pass` count as engaged).

**Comparison:** hook_rationale vs placebo, paired McNemar exact on
discordant pairs, pooled across 3 scenarios × 10 trials = 30 paired sets.

**Falsifier thresholds (CARRIED FORWARD VERBATIM from M22c):**
* **CONFIRMED:** hook_rationale > placebo by ≥ 10pp AND McNemar **p ≤ 0.05**.
* **DIRECTIONAL (secondary verdict):** ≥ 5pp AND p ≤ 0.15. Reported
  as "directional signal, needs more N."
* **REFUTED:** within 5pp of placebo.
* **OPPOSITE:** placebo > hook_rationale by ≥ 5pp (reverse effect; null
  with surprise note).

## Secondary tests (descriptive only — no inferential threshold)

Carried forward verbatim from M22c. Per-scenario breakdown of
compile/test 4-bin; hook_fact vs hook_rationale; LLM-judged response
4-bin; sub-test pass rate distribution; Wilson 95% CIs.

## Exclusion rules (CARRIED FORWARD VERBATIM from M22c)

Drop any trial whose response body is **<50 characters**. Recompute
the compile+link baseline on the same exclusion set.

## Pilot go/no-go gates (M22c gates carried forward + adapted)

Before running the full sweep, the N=24 pilot MUST pass ALL of:

1. **Empty-response rate < 5%** (1/24 max). Same as M22c.
2. **At least one discordant outcome per arm-pair.** Same as M22c.
3. **Within-cell variance check.** Same as M22c.
4. **Judge round-trip ≥ 95%.** Same as M22c (re-calibrate gemma on JS/TS).
5. **Hand-spot-check ≥ 8/10 agreement.** Same as M22c.
6. **Floor + ceiling band:** no_context compile+test pass rate lands
   in [25%, 75%]. Below 25% → workload too hard → REFUTED-VIA-FLOOR
   path (see §Pivot-killer commitments). Above 75% → ceiling-bound
   → halt sweep, redesign single hide-rule for stronger context-strip.
7. **Hook_fact discriminates:** hook_fact compile+test pass rate
   must exceed no_context by ≥10pp on the pilot. If not, the workload
   doesn't discriminate "answer-in-prompt" — pivot.

**Hard stop:** if (1), (2), (4), or pivot-killer Q1 (gate 6 floor-failure
sub-case) fails, postmortem — capture as finding, do NOT run sweep.

## Judge calibration

Re-calibrate gemma4:31b on **JS/TS-shaped responses** before primary
analysis (the M22a/M22c calibration was Dart-shaped). Procedure
identical to M22c.4: 20 hand-classified pilot responses + gemma run,
compute Cohen's kappa. Pre-registered floor: **kappa ≥ 0.4.**

## What gets reported

Identical to M22c verbatim. Win or lose: cell counts with Wilson CIs,
per-arm 4-bin distribution, paired McNemar primary, hook_fact descriptive,
LLM-judged response 4-bin, inter-judge kappa, excluded-trial counts +
reasons, **prediction vs actual on no_context floor.**

**NOT acceptable** (verbatim from M22c §"NOT acceptable"):
cherry-picking favorable scenarios, dropping arms because they look
bad, retroactively adjusting falsifier thresholds, swapping the primary
test to LLM-judged 4-bin if compile/test goes against us, running a
second workload as a tiebreaker if M22e fails.

## Null-result pre-commitment (CARRIED FORWARD VERBATIM from M22c)

If hook_rationale ≤ placebo + 5pp on the primary compile+link pass
rate, **the verdict is REFUTED** and the writeup leads with that.
We do NOT retreat to "but the engagement 4-bin shows X..." as the
headline.

## Pivot-killer commitments

The M22e.0 reviewer surfaced two pivot-killer questions. These have
pre-registered fall-back rules:

**Q1 — Floor band failure.** If the pilot N=24 produces no_context
compile+test pass rate outside [25%, 75%] AND the band-edge predicted
by the redesign rule (gate 6 above) cannot be hit by a minor hide-rule
tweak, the verdict is:

> **REFUTED-VIA-FLOOR.** The compile/test grading methodology cannot
> measure hook-rationale signal at this model's capability tier.
> M22a-regrade's engagement 4-bin signal stands as the existing positive
> evidence; M22e does not add new compile/test evidence either way.

**Q2 — Leak-score-0 rationales fail independent grading.** If any of the
three locked rationales fails the M22e.1a independent leak-grading pass
AND cannot be rewritten to pass with the same scope, drop the scenario.
If fewer than 2 scenarios survive, the verdict is:

> **REFUTED-VIA-LEAKAGE.** Cannot construct a clean rationale-vs-placebo
> comparison on this workload. M22a-regrade's engagement 4-bin signal
> stands; M22e does not add new compile/test evidence.

We commit upfront to taking these paths if the conditions trigger.

## What MUST come through unchanged from M22c (locked rules)

* **Null-result pre-commitment** (above, verbatim)
* **Anti-Texas-sharpshooter** (above, verbatim)
* **Falsifier thresholds** (above, verbatim)
* **Exclusion rule** (above, verbatim)
* **Primary metric definition** (paired McNemar on compile+link pass)
* **Pre-reg locked BEFORE harness work** (this document)
* **Leak-score-0 requirement on rationales** (with independent
  reviewer pass per M22e.1a)
* **Pilot gates 1, 2, 3, 4, 5** (verbatim; gate 6 adapted for band)

## What LEGITIMATELY changes from M22c

* **Workload:** multi-file Dart → single-file JS/TS
* **Hide-rule:** complex multi-file hide-rules → trivially the target
  file (single-file workload). Layout is explicit in prompt.
* **Judge calibration:** Dart-shaped → JS/TS-shaped (new 20-sample set)
* **Sweep N:** 60 → 120 (faster trials enable better paired-McNemar power)
* **Pilot gate 6:** "floor non-degenerate" → "floor in [25%, 75%] band"
* **Pilot gate 7 (new):** "hook_fact discriminates" (≥10pp over no_context)
* **Predicted no_context band:** new — pre-registered upfront

## Sub-milestone status

| sub | status |
|---|---|
| M22e.0 — methodology review | ✅ complete |
| M22e.1 — pre-registration (this doc) | ✅ complete |
| M22e.1a — independent leak-grading of 3 rationales | ⏳ next |
| M22e.2 — JS/TS workload scaffolding (3 scenarios + reference solutions + oracle tests) | pending |
| M22e.3 — 4-arm harness | pending |
| M22e.4 — pilot N=24 + gates | pending |
| M22e.5 — full sweep N=120 | pending |
| M22e.6 — analysis + findings | pending |

## Files (planned)

* `experiments/bakeoff/m22e_pilot/scenarios.json` — locked scenarios (M22e.2)
* `experiments/bakeoff/m22e_pilot/m22e_pilot.py` — harness (M22e.3)
* `experiments/bakeoff/benchmarks/js-singlefile/` — reference workspace (M22e.2)
* `experiments/bakeoff/runs-m22e-pilot/` — trial summaries + raw outputs
* `experiments/bakeoff/m22e_pilot/M22E_LEAK_GRADING.md` — independent reviewer pass (M22e.1a)
