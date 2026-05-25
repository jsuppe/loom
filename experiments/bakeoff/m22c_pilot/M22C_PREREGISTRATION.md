# M22c Pre-registration — Single-Benchmark Dart Characterization Study

**Locked:** 2026-05-25
**Status:** Locked BEFORE harness build (per REQ-3896db58 step 2)
**Methodology-review verdict:** "would not run as designed" — all blockers addressed in this pre-reg
**Reframing acknowledged:** single-benchmark (dart-inventory), NOT a Dart-broad claim

## Why this pre-reg exists

Per REQ-3896db58 (the M22 methodology pattern earned its keep 5/5),
this document locks the M22c design BEFORE any harness build, so the
falsifier verdict is committed-to without hindsight bias.

The methodology-review sub-agent (M22c.0) flagged three structural
blockers in the proposed M22c design plus several secondary concerns.
This pre-reg incorporates every actionable fix.

## Blocker resolutions

### Blocker 1 — dart-orders has no reference source files

**Verified.** `experiments/bakeoff/benchmarks/dart-orders/ground_truth/reference/`
contains only `.dart_tool/` build artifacts + `pubspec.lock`. No `lib/`,
no `test/`, no `manifest.json`. The benchmark source is gone.

**Resolution:** **single-benchmark scope (dart-inventory only).** Findings
will NOT generalize to dart-orders or to Dart broadly. The writeup will
explicitly frame this as a "single-benchmark single-language
characterization study," per reviewer recommendation.

### Blocker 2 — "Hide the matching contract" has no clean Dart analog

Dart's `customer_service.dart` doesn't have an `.hpp`-equivalent
abstract class. Its contract is distributed across:
* `lib/types/customers.dart` (the `Customer` value class — has `id`, `name`,
  `email` required-named-parameters explicit in source)
* `lib/types/customers.dart` doc-comment ("`id`, `name`, and `email` are
  required")
* `lib/shop.dart` (barrel — `export 'services/customer_service.dart'`
  leaks target name)
* `lib/services/order_service.dart` (consumer — references the
  service's methods via call sites)
* `test/shop_test.dart` (oracle)

**Resolution — operational "hide contract" rule:**

For each target file being regenerated, the trial workspace EXCLUDES:
1. The target file itself.
2. The matching `export` line in `shop.dart` (strip the one line; keep the rest).
3. Doc-comment lines in sibling type files that paraphrase the contract
   (per-scenario hand-stripped during scenario authoring).
4. `test/shop_test.dart` (the oracle) — excluded from ALL arms identically.

The trial workspace KEEPS:
* The other service files (`order_service.dart` etc.). Consumers stay
  visible. This is the reviewer's "position A": we test hook-rationale
  over-call-site-inference, not hook-rationale-vs-vacuum.
* Type files (`customers.dart` etc.) with leaky doc-comments stripped.
* `lib/persistence.dart` + `lib/errors.dart`.
* `pubspec.yaml`.

This is acknowledged as a HIGHER FLOOR than a pure typelink-vacuum
study. The primary metric isn't absolute pass rate — it's the
delta between arms.

### Blocker 3 — Proposed hook-rationale text leaks the fact

"id-first parameters for cross-service joining" + visible
`customers.dart` lets the model reconstruct the `register()` signature
trivially.

**Resolution — style-not-signature rationale design.** Each scenario's
rationale must constrain a STYLE choice (where rationale narrows the
space without dictating signature) rather than a SIGNATURE choice
(where rationale IS the signature).

Per-scenario rationales (pre-locked, pre-graded for leak risk):

| target | style-rationale | what it constrains | leak risk (0-3) |
|---|---|---|---|
| `customer_service.dart` | "Services use required named kwargs over positional because callers are mostly generated code where field order may evolve." | named vs positional | **0** (style only) |
| `inventory_service.dart` | "Duplicate-registration must throw `ConflictError`, never return null or silent-overwrite — downstream services rely on the throw to detect resync needs." | error style (throw vs null) | **0** (style only) |
| `order_service.dart` | "Order creation must validate ALL line items before any persistence write — never partial-commit. Use a pre-check pass + then atomic write." | transaction pattern (atomic vs incremental) | **0** (style only) |

**Pre-grading rule:** any rationale with leak-score ≥ 2 is excluded
from F-hook-rationale primary analysis. Currently all 3 scenarios are
leak-score 0. If future scenarios need to be added, hand-grade first.

The hook-fact arm uses the literal signature contract for comparison
(upper-bound), as designed.

## Locked design

### Workload

* **Benchmark:** dart-inventory (single benchmark)
* **Target files:** 3 service files
  - `lib/services/customer_service.dart`
  - `lib/services/inventory_service.dart`
  - `lib/services/order_service.dart`
* **Per-scenario workspace:** reference solution minus the hide-rules above
* **Test command:** `dart test test/shop_test.dart`

### Four arms

1. **`no_context`** — bare task + workspace (with hide-rules). Task: "Implement `<target>` for the multi-service shop. Other files are present; reference the project's conventions from the codebase."
2. **`hook-rationale`** — bare task + `<system-reminder>` carrying the locked style-rationale (above, leak-score 0). Tests loom's actual value prop.
3. **`hook-fact`** — bare task + `<system-reminder>` carrying the literal signature contract. Tests upper-bound (answer-in-prompt).
4. **`placebo`** — bare task + length-matched irrelevant project text drawn from OTHER scenarios' rationales.

### Grading

**Compile/test 4-bin outcome (the primary metric per reviewer):**
* `compile_fail` — `dart analyze` or test run reports type errors
* `link_fail` — analyzer ok but test reports undefined symbol/method
* `test_fail` — runs but 0/28 sub-tests pass
* `test_pass` — runs and ≥27/28 sub-tests pass (allow 1 flake)

Plus a continuous sub-test pass rate (passed / 28) for granular signal.

**LLM-judged 4-bin response classification** via gemma4:31b (per
REQ-d91fcd71 + the M22a-regrade harness). Re-calibrated on Dart subset
(see Judge Calibration below).

### Sample size

* **Pilot (M22c.4):** 3 services × 4 arms × 2 trials = **24 trials**. Goes through every pilot gate (see below).
* **Full sweep (M22c.5):** 3 services × 4 arms × 5 trials = **60 trials**.

**N=60 is at the power floor for McNemar on this effect size.** Per
reviewer: pool across services for primary McNemar; per-service is
underpowered (5 paired sets each). Report per-service descriptively only.

### Primary test (LOCKED — F-hook-rationale)

**Metric:** compile+link pass rate (i.e. `compile_fail` and `link_fail`
both excluded; `test_fail` and `test_pass` count as engaged-with-typelink).

**Comparison:** hook-rationale vs placebo, paired McNemar exact on
discordant pairs, pooled across 3 services × 5 trials = 15 paired sets.

**Falsifier thresholds:**
* **CONFIRMED:** hook-rationale > placebo by ≥ 10pp on compile+link
  pass rate AND McNemar **p ≤ 0.05**.
* **DIRECTIONAL (secondary verdict):** hook-rationale > placebo by
  ≥ 5pp AND p ≤ 0.15. Reported as "directional signal, needs more N."
* **REFUTED:** hook-rationale within 5pp of placebo.
* **OPPOSITE:** placebo > hook-rationale by ≥ 5pp (would indicate
  reverse effect; would be reported as null with surprise note).

### Secondary tests (descriptive only — no inferential threshold)

* Per-service breakdown of compile/test 4-bin
* hook-fact vs hook-rationale (characterizes how much the
  "fact-in-prompt" trivial-help is worth)
* LLM-judged response 4-bin (drift_cited_pause / procedural_pause /
  proceeded_with_reasoning / proceeded_blindly)
* Sub-test pass rate distribution per arm
* Wilson 95% CIs on every cell

## Exclusion rules (LOCKED)

Drop any trial whose response body is **<50 characters** (per
M22a-pilot F3 lesson — empty timeouts game the binary grader).
Recompute the compile+link baseline on the same exclusion set so
arms are apples-to-apples.

## Pilot go/no-go gates (LOCKED — per reviewer)

Before running the full sweep, the N=24 pilot MUST pass ALL of:

1. **Empty-response rate < 5%** (1/24 max). If higher, fix timeout
   or token budget. F3-shape failure mode.
2. **At least one discordant outcome per arm-pair.** If all paired
   arms produce identical compile/test outcomes, scenarios don't
   discriminate. Pivot.
3. **Within-cell variance check.** Run 5 trials of ONE (scenario × arm)
   cell. Must produce ≥ 2 distinct response strings. If all 5
   bit-identical, drop trials/scenario back to 1 (no inferential gain).
4. **Judge round-trip ≥ 95%.** Run gemma4:31b twice on the pilot
   response set. Self-agreement must be ≥ 95%. Lower → calibration on
   Dart is broken.
5. **Hand-spot-check ≥ 8/10 agreement.** Hand-classify 10 random pilot
   responses; compare with gemma. If hand-judge agreement < 80%,
   re-calibrate before sweep.
6. **Floor non-degenerate.** If no_context produces 0% compile-pass
   (floor too low) OR 100% (floor too high), redesign the
   hide-contract rule before sweep.

**Hard stop:** if (1), (2), or (4) fails, postmortem — capture as
finding, do NOT run the full sweep.

## Judge calibration (LOCKED)

Re-calibrate gemma4:31b on Dart-shaped responses before primary
analysis. Procedure:

1. Hand-classify 20 Dart pilot responses using the M22a-regrade
   rubric, with one addition: a **`code_only_no_meta`** bin for trials
   where the model dumps Dart with no meta-commentary (likely common
   on "regenerate this file" tasks).
2. Run gemma4:31b on the same 20.
3. Compute Cohen's kappa (hand vs gemma).
4. **Pre-registered floor:** kappa ≥ 0.4. Below this → re-prompt the
   judge OR add Dart-specific bin notes OR switch judge model.

## What gets reported

Win or lose, the writeup will include:
* All cell counts with Wilson 95% CIs
* Per-arm compile/test 4-bin distribution
* hook-rationale vs placebo paired McNemar (primary)
* hook-fact vs hook-rationale descriptive
* LLM-judged response 4-bin per arm
* Inter-judge kappa from Dart calibration
* Excluded-trial counts + reasons

**NOT acceptable:** cherry-picking favorable services, dropping arms
because they look bad, retroactively adjusting falsifier thresholds,
swapping the primary test to the response-4-bin if compile/test goes
against us.

## Null-result pre-commitment

If hook-rationale ≤ placebo + 5pp on the primary compile+link pass
rate, **the verdict is REFUTED** and the writeup leads with that.
We do NOT retreat to "but the engagement 4-bin shows X..." as the
headline. M22a-regrade already did the engagement-pivot once;
M22c will not do it again.

## Process safeguards

This document was locked BEFORE any harness work. Committed in the
same change as the methodology-review findings. Any deviation from
the locked rules will be flagged in the writeup as "deviation from
pre-registration" with rationale.

## Sub-milestone status

| sub | status |
|---|---|
| M22c.0 — methodology review | ✅ complete |
| M22c.1 — pre-registration (this doc) | ✅ complete |
| M22c.2 — Dart workload scaffolding | deferred (next session) |
| M22c.3 — 4-arm harness | deferred (next session) |
| M22c.4 — pilot N=24 + gates | deferred |
| M22c.5 — full sweep N=60 | deferred |
| M22c.6 — analysis + findings | deferred |
