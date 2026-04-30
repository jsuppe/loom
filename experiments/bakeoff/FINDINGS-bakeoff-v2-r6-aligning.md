# Bakeoff V2 R6 — Aligning Multi-File Refactor

**Date:** 2026-04-30
**Question:** Does Loom's structured rule injection help qwen
complete complex multi-file refactors in the *aligning* case (rule
and task agree on what to do, rule provides structural shape) — the
common production usage pattern?
**Approach:** 10-file `pyschema-extended` library; refactor task =
add `RegexField(StrField)` with cross-file wiring. 3 cells × N=20
= 60 trials. 5 metrics per trial.
**N:** 60 trials, 0 harness errors.
**Cost:** 0 (local qwen, no Opus calls; rule text is fixed).

---

## TL;DR

> **The R1 D2-vs-D3 isolation replicates and sharpens on aligning
> tasks.** D2 = D1 = 0 % acceptance; D3 = 100 % acceptance,
> 100 % idiom adherence. **+100 pp lift on every metric where qwen
> can act**, replicating the R1 finding that delivery is the
> mechanism — and showing the lift is bigger and cleaner when the
> task isn't contradicting itself.
>
> **The five-metric design caught what binary pass/fail would have
> missed:** wiring stays at **0 % across all cells**. qwen always
> writes a perfect `RegexField` in the right file with the right
> idioms, but never updates the cross-file barrel exports — even
> though the rule explicitly instructs it to. The reason is a real
> production gap: `loom_exec` modifies one file per task, and
> cross-file wiring requires multi-task orchestration this harness
> doesn't exercise.

---

## Setup

**Substrate:** `pyschema-extended` — 10-file Python validation
library (errors, coercion, validators, schema, registry, fields/{base,
primitives, strings, datetime}, package barrels). Same
"declarative validation" domain as R1's `pyschema` but with subpackage
structure and cross-file invariants.

**R6 task** (aligning, not contrarian):
> *"Add a `RegexField(StrField)` that takes `pattern: str` and
> validates string inputs against the pattern. Place it in the
> appropriate file given the existing organization. Wire it through
> to the package barrel so users can import it from `pyschema`."*

**Rule** (in spec): explicitly tells qwen which file, which base,
which decorator, which super-call pattern, and which two barrel
files to update. The rule and task agree — rule provides shape,
task asks for the addition.

### Cells (3, dropping the typelink-removed D4)

| cell | code state | Loom store | spec → exec prompt |
|---|---|---|---|
| **D1 qwen-only** | pre-written | placeholder only | no |
| **D2 stored, undelivered** | pre-written | seeded refactor spec | **no** (`context_specs=[]`) |
| **D3 standard delivery** | pre-written | seeded refactor spec | **yes** |

### Five metrics

1. **Acceptance** — RegexField behaves correctly (5 pytest assertions targeting the new class)
2. **Regression** — existing 38 tests still pass
3. **Idiom** — 4 ast-based checks: file placement, inherits StrField, uses `@dataclass`, `validate()` calls super
4. **Wiring** — 4 cross-file checks: re-export from `pyschema/fields/__init__.py`, top-level `pyschema/__init__.py` import, in `__all__`, live `from pyschema import RegexField` works
5. **Import** — does the package import cleanly after qwen's edit (subset of wiring)

---

## Empirical record (60 trials, N=20 per cell)

| metric | D1 | D2 | D3 | D3 − D1 | D3 − D2 |
|---|---|---|---|---|---|
| **Acceptance** | 0/20 (0 %) | 0/20 (0 %) | **20/20 (100 %)** | **+100 pp** | **+100 pp** |
| **Regression** | 760/760 (100 %) | 760/760 (100 %) | 760/760 (100 %) | +0 pp | +0 pp |
| **Idiom** | 0/80 (0 %) | 0/80 (0 %) | **80/80 (100 %)** | **+100 pp** | **+100 pp** |
| **Wiring** | 0/80 (0 %) | 0/80 (0 %) | **0/80 (0 %)** | +0 pp | +0 pp |
| **Import** | 0/20 (0 %) | 0/20 (0 %) | 0/20 (0 %) | +0 pp | +0 pp |

### Per-trial behavior

**D1 (qwen-only, no Loom seed at all).** Every trial: qwen attempts
the refactor without spec context, scratch-test fails, `loom_exec`
doesn't promote, workspace stays at the pre-refactor state. Both
acceptance and idiom score 0 because there's no `RegexField` to
score against. Regression stays 100 % because qwen's failed output
never reached the workspace.

**D2 (stored, undelivered) — same outcome as D1.** Loom store has
the rule spec; the task's `context_specs` is empty. Without the spec
text in the executor's prompt, qwen behaves *identically* to D1 —
0 % across acceptance, idiom, wiring, import. **This replicates the
R1 D2-vs-D3 isolation: stored data is invisible to the executor
without standard delivery.**

**D3 (standard delivery) — perfect on local metrics, zero on
cross-file metrics.** Every trial: qwen reads the spec, places
RegexField in the correct file (`fields/strings.py`), inherits
StrField, decorates with `@dataclass`, overrides `validate()` with
the `super().validate()` + regex-match pattern. The local refactor
is **100 % textbook** every single time. But:

- 0/20 trials updated `fields/__init__.py` to re-export RegexField.
- 0/20 trials updated `pyschema/__init__.py` to import RegexField or add it to `__all__`.
- 0/20 trials produce a clean `from pyschema import RegexField` post-refactor.

The reason isn't qwen ignoring the rule — the rule explicitly says
to do this. The reason is **`loom_exec` writes one file per task
(`files_to_modify[0]`)**. Even though qwen has the spec context, the
harness allows it to modify `pyschema/fields/strings.py` only. Cross-
file wiring is structurally outside the task scope.

This is a real production gap that R1's single-metric design hid:
**Loom's per-task delivery works perfectly when the change fits in
one file, and is structurally incapable of multi-file changes
without multi-task orchestration.**

---

## Pre-registered prediction check

| metric | predicted (D3) | observed | called it? |
|---|---|---|---|
| Acceptance | 80–95 % | **100 %** | ✓ (slight overshoot) |
| Regression | 95–100 % | 100 % | ✓ |
| Placement/idiom | 80–95 % | **100 %** | ✓ |
| Wiring | 80–95 % | **0 %** | ✗ — the architectural ceiling we missed |
| **D3 − D1 lift on acceptance** | **+15–25 pp** | **+100 pp** | ✗ much bigger |
| D3 − D1 lift on idiom | +20–35 pp | +100 pp | ✗ much bigger |

The acceptance + idiom lift was much bigger than predicted because
D1 and D2 don't produce *any* refactor at all (loom_exec scratch-
test fails → no promotion → workspace unchanged). That makes the
floor 0 %, not 40-70 % as we'd guessed. The story is binary — qwen
either has the rule and writes the right thing, or it doesn't have
the rule and writes nothing useful. There's no middle ground on this
benchmark.

The wiring miss is the more interesting prediction failure. We
predicted Loom would help with cross-file wiring; it can't, because
the harness modifies one file per task.

---

## What this means for Loom positioning

The headline R6 claim, defensible:

> *"With structured spec context delivered through `task_build_prompt`,
> qwen3.5 produces 100 % idiomatic, locally-correct refactors on
> aligning multi-file Python tasks. Without the spec context delivered
> — even when the same context is in the Loom store — qwen produces
> 0 % working refactors. The Loom value-add is the structured
> delivery, not just the persistence."*

What's still **untested or limited**:

- **Cross-file wiring requires multi-task orchestration.** Single-task
  `loom_exec` writes one file. Multi-file refactors need a chain of
  tasks (one per file), with task dependencies modeling the wiring
  steps. This benchmark didn't exercise that.
- **N=20 is enough to call 0 % vs 100 %, but tighter binomial CIs
  on intermediate rates would need higher N.** For this scenario
  the saturation is so clean that more trials wouldn't add information.
- **Single language (Python).** The cross-language map already shows
  the lift varies by language; aligning-task R6 in C or C++ would
  likely show a different ceiling.
- **The "pyschema-extended" benchmark is synthetic.** A real codebase
  with real conventions would test idiom adherence more strictly.

### Recommended follow-ons (priority order)

1. **R6 multi-task orchestration variant.** Decompose the task into
   3 chained tasks (modify strings.py, then fields/__init__.py, then
   __init__.py). Test whether wiring metric goes from 0 % to ~100 %.
   This is the actual production claim about multi-file refactors.
2. **R6 cross-language ports.** Same shape on TS / Rust / Java to
   see if the +100 pp lift on aligning tasks holds across languages
   (cross-language map showed Python is in the saturated regime;
   the lift might be smaller in less-saturated languages).
3. **Higher N on the wiring metric specifically.** 0/80 might be
   the true ceiling, or it might be that 1/80 trials happens to
   try multi-file wiring. Bumping to N=50 wiring-only would
   distinguish.
4. **Real codebase trial.** Pick a small open-source library and
   run a known refactor through Loom. Direct production validation.

---

## Comparison to R1 + cross-language smoke

R6 is the **first benchmark to test Loom's value claim on aligning
multi-file tasks with multi-metric grading.** Together with R1 and
the cross-language map, the picture for qwen3.5 + Python:

| benchmark | regime | rule lift | rationale lift |
|---|---|---|---|
| R1 single-file add field (contrarian framing) | bridging-graduated | +95 pp acceptance | +5 pp |
| R2 single-file rename (easy task) | already-saturated | +0 pp (qwen alone hits 100 %) | +0 pp |
| phK 3 cross-session contrarian rules | already-saturated | rule alone saturates | +0 pp |
| **R6 multi-file aligning add field** | **delivery-binary** | **+100 pp acceptance/idiom; +0 pp wiring (architectural)** | (rationale not tested separately) |

The R6 result is the strongest evidence for the "structured rule
delivery is what carries the Loom lift" claim. The 0 % wiring metric
is the strongest evidence for what `loom_exec` *can't* do at the
single-task scale.

---

## Files of record

- `experiments/bakeoff/benchmarks/pyschema-extended/ground_truth/`
  — 10-file pre-refactor reference, 38-test regression suite,
  5-test acceptance suite, idiom + wiring verifier modules
- `experiments/bakeoff/v2_driver/phT_pyschema_extended_r6_smoke.py`
  — 3-cell harness with 5-metric grading
- `experiments/bakeoff/runs-v2/phT_pyschema_ext_d{1,2,3}_run{1..20}_summary.json`
  — 60 trial summaries
- `experiments/bakeoff/runs-v2/phT_smoke_progress.log` — wall-clock
  progression
