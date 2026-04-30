# Bakeoff V2 R6m — Chained-Tasks Variant of R6

**Date:** 2026-04-30
**Question:** Does Loom's existing multi-task chain mechanism
(`depends_on` DAG, `loom_exec --loop`) solve the cross-file wiring
gap that R6 surfaced as 0 % across all cells?
**Approach:** Same R6 substrate (`pyschema-extended`, 10 files,
add `RegexField`); decompose the refactor into 3 chained tasks
(T1: strings.py, T2: fields/__init__.py, T3: top __init__.py)
with `depends_on`. Same 3 cells (D1m / D2m / D3m), same 5 metrics.
**N:** 60 trials × 3 tasks each = 180 task executions.
**Errors:** 0 harness errors.

---

## TL;DR

> **The chain mechanism completely closes the wiring gap.** Wiring
> went from R6's 0/80 (0 %) to R6m's 76/80 (95 %) — D1m — and
> 80/80 (100 %) — D2m / D3m. The "architectural ceiling"
> identified in R6 was a single-task-scope artifact, not a Loom
> defect. **The hypothesis is confirmed.**
>
> But the experiment also produced two surprises that **partially
> overturn R6's "delivery is the mechanism" narrative**:
>
> 1. D1m (qwen-only, no spec) hits 95 % across all metrics. R6 D1
>    with the same coarse task title scored 0 %. The difference
>    isn't qwen — it's that each chained task in R6m has a detailed
>    title carrying the implementation specifics that R6's task title
>    was missing.
> 2. D2m and D3m are tied at 100 %. The spec being delivered or not
>    delivered makes zero difference when tasks are precisely
>    decomposed.
>
> **Refined Loom claim:** the value is in *decomposition*, not just
> *delivery*. Once coarse intent is broken into fine-grained tasks
> (which is what `loom decompose` does), qwen executes reliably
> regardless of whether parent spec context is in the prompt.
> The spec only carries weight when tasks are vague.

---

## Setup

**Substrate:** Same `pyschema-extended` library + tests as R6
([`FINDINGS-bakeoff-v2-r6-aligning.md`](FINDINGS-bakeoff-v2-r6-aligning.md)).

**Decomposition:** 3 tasks chained via `depends_on`:

| task | file | gate test | depends |
|---|---|---|---|
| **T1** | `pyschema/fields/strings.py` | `test_gate_t1.py` (RegexField construct + validate) | — |
| **T2** | `pyschema/fields/__init__.py` | `test_gate_t2.py` (re-export works) | T1 |
| **T3** | `pyschema/__init__.py` | `test_gate_t3.py` (top import + in `__all__`) | T2 |

Each task has a detailed multi-sentence title naming the file, the
specific edit, and any structural constraints. The spec rule is the
same as R6's (in D3m). `loom_exec --loop` drains the queue.

### Cells (3, parallel to R6's D1/D2/D3)

| cell | tasks have | what's in the spec |
|---|---|---|
| **D1m** | no `context_specs`, no `context_reqs` (placeholder spec) | not delivered |
| **D2m** | empty `context_specs` (real spec stored, undelivered) | stored, undelivered |
| **D3m** | `context_specs=[spec_id]` (real spec delivered to each task) | delivered to each task |

### Five metrics (same as R6)

1. Acceptance — RegexField behaves correctly (5 tests)
2. Regression — existing 38 tests still pass
3. Idiom — 4 ast-based checks (file, base, dataclass, super-call)
4. Wiring — 4 cross-file checks (re-export, top barrel import, `__all__`, live `from pyschema import RegexField`)
5. Import — does the package import cleanly (subset of wiring)

Plus a new metric for R6m: **tasks_complete** — how many of T1/T2/T3 reached `outcome: complete` per trial.

---

## Empirical record (60 trials, N=20 per cell)

| metric | D1m | D2m | D3m |
|---|---|---|---|
| **tasks_complete** | 57/60 (95 %) | 60/60 (100 %) | 60/60 (100 %) |
| **Acceptance** | 95/96 (99 %) | 100/100 (100 %) | 100/100 (100 %) |
| **Regression** | 760/760 (100 %) | 760/760 (100 %) | 760/760 (100 %) |
| **Idiom** | 76/80 (95 %) | 80/80 (100 %) | 80/80 (100 %) |
| **Wiring** | 76/80 (95 %) | 80/80 (100 %) | 80/80 (100 %) |
| **Import works** | 19/20 (95 %) | 20/20 (100 %) | 20/20 (100 %) |

The 5 % gap on D1m is one trial where T1 failed its gate test (qwen's
RegexField didn't pass the construct/validate checks), so T2 and T3
never ran. The chain stopped at the first broken link, as designed.

### Comparison to R6 (single-task variant)

| metric | R6 D1 | R6 D3 | R6m D1m | R6m D3m | delta R6→R6m |
|---|---|---|---|---|---|
| Acceptance | 0 % | 100 % | 99 % | 100 % | **D1: 0 → 99 %** |
| Idiom | 0 % | 100 % | 95 % | 100 % | **D1: 0 → 95 %** |
| Wiring | 0 % | **0 %** | 95 % | **100 %** | **D3: 0 → 100 %** ✓ chain solves it |
| Import | 0 % | 0 % | 95 % | 100 % | (same as wiring) |

The wiring jump from 0 % (R6 D3) to 100 % (R6m D3m) is the
hypothesis confirmation. The chain mechanism resolves the "Loom
production gap" the R6 finding identified.

---

## Pre-registered prediction check

| prediction | result | called it? |
|---|---|---|
| R6m D3m wiring ≥ 80 % | 100 % | ✓ (slight overshoot) |
| R6m D1m would look like R6 D1 (low) | actually 95 % across the board | ✗ surprised |
| R6m D2m would lag D3m | tied at 100 % | ✗ surprised |

The wiring prediction held cleanly. The two D1m / D2m surprises are
the more interesting results.

---

## Why D1m hit 95 % when R6 D1 hit 0 %

R6 D1 task title (single coarse task):
> *"Add a RegexField type to pyschema-extended that takes a regex
> pattern: str and validates string inputs against the pattern.
> RegexField should integrate with the existing Field hierarchy
> and be importable as `from pyschema import RegexField`."*

R6m D1m task titles (three precise tasks):
> *T1: "Step 1 of 3: Add the RegexField class to
> pyschema/fields/strings.py. Inherits StrField; takes
> `pattern: str` (default ''); overrides validate() to call
> super().validate() then re.match(self.pattern, result). Use
> @dataclass decorator. Place after the existing UUIDField class."*
>
> *T2: "Step 2 of 3: Re-export RegexField from
> pyschema/fields/__init__.py. Add `RegexField` to the import
> line `from .strings import EmailField, URLField, UUIDField`
> (make it `EmailField, RegexField, URLField, UUIDField`) and
> add `'RegexField'` to the `__all__` list (alphabetically)."*
>
> *T3: ... (similar precision for top-level barrel)*

The R6m task titles are essentially a step-by-step recipe. They
contain the file paths, base class names, decorator specifications,
and exact import-line edits. **When the task title carries this
information, the spec is redundant.** That's why D1m matches D2m /
D3m — there's no headroom for the spec to add value.

In R6, the coarse task title left these decisions open. The spec
filled them in (D3 hit 100 % on acceptance + idiom). Without the
spec (D1, D2), qwen had no structural anchor and produced nothing
that passed the gate.

---

## What this refines about Loom's value claim

The R6 narrative was: *"delivery is the mechanism — D2 vs D3 = 0 % vs
100 % isolates that storing rules without surfacing them adds no value.
The structured rule needs to reach the executor's prompt."*

R6m refines this: *"the spec context is one of several mechanisms that
can carry structural commitments to the executor. Detailed task titles
are another. Once tasks are precisely decomposed, the spec adds
marginal value because the task title is already a micro-spec."*

The actual production-relevant claim is sharper:

> **Loom's value is in helping a human or agent decompose coarse
> intent into precise atomic tasks.** `loom decompose` is the
> primary value-add. Once tasks are well-decomposed, the executor
> succeeds reliably whether or not the parent spec is in the prompt.
> The spec mostly matters when decomposition is loose.

Two paths to high pass rates on the production case:
- **Loose task + structured spec** (R6 D3) → 100 % acceptance, 0 % wiring
- **Fine-grained decomposition + minimal spec** (R6m D1m) → 95 % across all 5 metrics
- **Fine-grained decomposition + structured spec** (R6m D3m) → 100 % across all 5 metrics

The combination is best, but the decomposition alone gets you most
of the way there — and crucially, the chain mechanism is what
unlocks multi-file refactors regardless of which path you take.

---

## What this means for the broader smoke series

This is the **fifth** experiment that has refined what "Loom helps"
means:

1. R1 single-file add field (contrarian framing) → +95 pp on D2 vs D3 → "delivery matters"
2. R2 single-file rename (easy task) → 100 % across cells → "Loom adds nothing when task is easy"
3. phK 3 cross-session contrarian rules (Python) → rule alone saturates → "rationale field is decorative"
4. R6 multi-file aligning add field (single task) → +100 pp on D2 vs D3, but **wiring stuck at 0 %** → "architectural ceiling"
5. **R6m multi-file aligning add field (chained tasks)** → wiring solved (95–100 %), but **D2m = D3m = 100 %** → "decomposition is the load-bearing mechanism, not delivery"

The Loom story has progressively sharpened. Each experiment cut a
piece of the original "Loom helps small models" claim and refined
the surviving piece. The current honest claim:

> **Loom's structured decomposition (`loom decompose`) breaks coarse
> intent into precise chained tasks; that decomposition alone is
> sufficient to drive qwen3.5 to ≥95 % completion on multi-file
> aligning Python refactors. Spec context delivered through
> `task_build_prompt` adds the marginal 5 pp (and prevents the rare
> task-title-ambiguity failure). Loom's per-task delivery is correct
> but underpowered for multi-file changes — the chain mechanism
> covers that.**

---

## Limitations

- **Manual decomposition.** The R6m task titles were authored by
  hand to maximize precision. We didn't test `loom decompose`'s
  *automated* decomposition; it might or might not produce titles
  this precise. **The most-important follow-on:** run R6 through
  `loom decompose --apply` and see if the auto-decomposed tasks
  match D1m's pass rate.
- **Single language (Python).** Other languages might decompose
  differently. The cross-language map already showed Python is in
  the saturated regime.
- **Single refactor type (add new class wired through barrels).**
  Other multi-file refactors might not decompose this cleanly.
- **D1m's 95 % is from N=20.** Binomial 95 % CI for 19/20 is
  [75 %, 99.9 %]. The point estimate is high but the lower bound
  isn't far below D3m's 100 %.

### Recommended follow-ons (priority order)

1. **Auto-decompose R6 with `loom decompose`.** Test whether the
   actual decomposer produces task titles precise enough to match
   D1m's 95 %. If it does, the production claim is intact. If
   auto-decomposed titles are coarser, that's a `loom decompose`
   gap to fix.
2. **R6m on a real codebase (replay study).** Pick a known
   open-source library refactor, drive it through Loom's full
   chain. Compare the result to the merged PR.
3. **R6m cross-language ports.** TS / Rust / Java multi-file
   refactors with the chain mechanism. Test whether decomposition
   amortizes the language-specific friction the cross-language map
   surfaced.

---

## Files of record

- `experiments/bakeoff/v2_driver/phU_pyschema_extended_r6m_smoke.py`
  — 3-cell × 3-task harness with 5-metric grading + per-task
  completion counter
- `experiments/bakeoff/runs-v2/phU_pyschema_r6m_d{1m,2m,3m}_run{1..20}_summary.json`
  — 60 trial summaries
- `experiments/bakeoff/runs-v2/phU_smoke_progress.log`
  — wall-clock progression
- Reused: `experiments/bakeoff/benchmarks/pyschema-extended/ground_truth/`
  — same substrate as R6
