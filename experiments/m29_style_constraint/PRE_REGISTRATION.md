# M29 — Style Constraint for C++: Pre-registration

**Drafted:** 2026-06-06 (while M28.4 runs)
**Status:** **DRAFT — locks after M28.4 verdict lands**
**Methodology pattern:** REQ-3896db58
**Builds on:** M10.2 (stub indexer baseline), M28 (ClangdIndexer Phase 1
running concurrently), M22c finding REQ-7e2d6518 (model file-path
hallucination from training-data priors)

> **Hypothesis under test (single sentence):**
> Explicitly constraining C++ style (language version, memory model,
> error handling, include style) in the prompt lifts the
> rationale-cell pass rate on the locked S1 C++ benchmark by ≥ 20pp
> compared to the no-style-constraint baseline, *independently* of
> semantic-context interventions.

---

## Why this experiment

C++ is unique among the tested languages on style-variance surface
area. Compared to Rust/Go/modern Python (each with one canonical
style), C++ presents the model with at least five independent style
axes — all of which the model has seen mixed in 40 years of training
data:

| dimension | C++ choice space |
|---|---|
| Language version | C++98 / 03 / 11 / 14 / 17 / 20 / 23 |
| Memory management | raw / smart ptr / RAII / refcount |
| Error handling | exceptions / error codes / `std::expected` |
| Generic style | templates / virtual / concepts |
| Standard library | `iostreams` / `<format>` / `printf` / fmt |

M22c (REQ-7e2d6518) established that the executor's training-data
priors override on-disk reality for *file paths* in Dart. The
hypothesis under M29 is that the same mechanism applies to C++ *style
choice*: the executor picks from training-data priors instead of
reading the codebase's idiom, and the resulting mismatch shows up as
compile failures and silently wrong behavior.

This is a *distinct* mechanism from M28's semantic-context
hypothesis. M28 tests "does the executor know enough about
cross-file consequences." M29 tests "does the executor pick the right
style family for this codebase." Both can be true; both can be false;
they could compound or be orthogonal.

## Pre-registered hypotheses

**H1 (primary):** Style constraint alone lifts the rat cell by ≥ 20pp
versus M28's no-style-constraint baseline.

Concretely: let `M28_rat` be the rat-cell pass rate from M28.4. M29
predicts `M29_rat_style_only ≥ M28_rat + 20pp`.

* **Confirms** if `M29_rat_style_only - M28_rat ≥ 20pp` with the
  pre-registered Wilson 95% lower CI on the difference
  positive-or-zero.
* **Refutes** if `M29_rat_style_only - M28_rat ≤ 0pp`. Style
  constraint is not the load-bearing lever for the S1 scenario.
* **Inconclusive** if `0 < M29_rat_style_only - M28_rat < 20pp`. Some
  signal but below the practical-significance threshold; expand N
  before deciding.

**H2 (secondary, conditional on M28 H1 confirming):** Style + semantic
combined ≥ max(style alone, semantic alone) + 10pp. Tests for additive
or multiplicative interaction. Skipped if M28's H1 is refuted (no
semantic baseline to combine with).

**H3 (tertiary, STOP gate):** The style-constraint block does NOT leak
rule-equivalent content. Off cell pass rate ≤ 20%.

This is the analog of M10.3a's phQ3 STOP gate. The risk is concrete:
the style-constraint block mentions `std::optional` as the preferred
"no value" return type, which partially anticipates the contrarian
rule's "return std::nullopt on all-failure." If the off cell jumps
above 20%, the constraint is leaking rule semantics — kill the
experiment and re-author the constraint without idiom-level guidance
on return types.

This STOP gate is required because pre-registering it forces us to
treat an off-cell lift as a failure, not a feature, before we see the
data. Without it, post-hoc rationalization could spin "off cell went
to 60%" as "the model now writes better C++ in general."

## Locked harness (locks after M28.4 verdict)

The M29 harness is the M28 harness with one swap: a `## Style
constraints` block prepended to the prompt right above the
`## Requirements` block.

| Component | Locked value |
|---|---|
| Driver | `experiments/m29_style_constraint/m29_style_smoke.py` (clone of m28_clangd_smoke.py with the style-constraint swap) |
| Scenario | `experiments/bakeoff/benchmarks/crosssession_cpp/s1_swallow_runtime_error/` (same as M28, M10.2, M10.1b) |
| Executor model | `qwen2.5-coder:32b` (same as M28, M10.2, M10.1b) |
| Temperature / seed | Same as M28 (matches phL2 verbatim — see REQ-ec63fa50 for the drift note) |
| N per cell | **10** (same as M28; doubled from M10.2's N=5) |
| Cells (Phase A — style alone) | off, on-rule, on-rule+placebo, on-rule+rat — **WITHOUT ClangdIndexer** |
| Cells (Phase B — combined; conditional) | same 4 cells **WITH ClangdIndexer** (only if M28 H1 confirms) |
| Total trials | 40 (Phase A) + 40 (Phase B if triggered) |

## Locked style-constraint text

The exact text prepended to the prompt, locked verbatim BEFORE M29
runs (any post-hoc edit invalidates the experiment):

```
## Style constraints

Target language: C++17. You may use std::optional, structured
bindings, std::string_view, and constexpr-if. Do NOT use C++20 or
later features (concepts, coroutines, ranges, modules,
std::expected, requires-clauses).

Memory model: RAII only. No raw `new` or `delete`. No `malloc` or
`free`. Use `std::unique_ptr` / `std::shared_ptr` where ownership
transfers; pass by const reference where lifetime is bounded by
the caller.

Error handling: prefer exceptions for exceptional paths
(`throw std::runtime_error(...)`, catch by const reference). Use
return-value-shaped sentinels (numeric error codes, magic values)
only when the existing file already does so.

Standard library: prefer `std::` over Boost, fmt, abseil, or
third-party equivalents. Use `<iostream>` for stdout/stderr.

Include style: angle brackets for stdlib (`#include <vector>`),
double quotes for project headers (`#include "retry.hpp"`).
```

**Critical confound acknowledged in the H3 STOP gate above:** the
phrases "Use std::optional" and "Use return-value-shaped sentinels"
are adjacent to the contrarian rule's content. If they leak rule
semantics, the off cell will jump above 20% and the experiment
self-falsifies.

The constraint text is moderate-explicit. It is NOT a multi-page
Google C++ Style Guide section — that would test "does the executor
follow long style guides" rather than "does an explicit style
constraint affect outcomes." The locked text is ~190 words of
constraint, comparable in length to the RATIONALE text from the rat
cell (~400 chars) so the prompt-token-count delta is bounded.

## Locked falsifier

H1 is falsified — and M29 Phase A is wrapped — if `M29_rat_style_only
- M28_rat ≤ 0pp`. Style constraint added no signal; pursuing it
further is not justified.

H3 is the STOP gate: if off cell pass rate ≥ 40% at any cell of N=10,
stop and audit the constraint text before evaluating H1. This is
binding even if H1 looks like a confirm — an off-cell rule leak makes
the H1 result uninterpretable.

If M28 H1 is refuted (so the semantic context is not the lever),
M29's H2 is automatically dropped — there's no semantic baseline to
combine with. M29 Phase A still runs in that case as an independent
hypothesis.

## Independent design review

**Status:** completed by the user during the M28.4 wait window,
2026-06-06.

**Approved:**
* The 20pp H1 threshold (lower than M28's effective 40pp because M29
  tests a smaller incremental intervention).
* The H3 STOP gate language and the 20%/40% thresholds.
* The decision to lock M29 AFTER M28.4's verdict lands, so M29
  Phase A's "baseline" is the just-measured M28 result (not the
  older M10.1b number).
* The constraint text being moderate-explicit (190 words) rather
  than minimal ("Target C++17") or heavy (full style guide).

**Reviewer concerns flagged but not blocking:**
* If M28's H1 confirms, the M29 Phase A trials may compete for the
  same lift M28 already captured — making H1 harder to clear. This
  is a known tradeoff; we accept it because the alternative (run M29
  before M28 to maximize signal) would compromise the apples-to-
  apples comparison to M10.2.
* Sub-agent design review is deferred to M29 Phase B (the combined
  cell) if it triggers. Phase A's minimum-confound shape (one swap
  on an already-reviewed M28 harness) doesn't warrant the review
  cost.

## Methodology compliance checklist (REQ-3896db58)

| Step | Status |
|---|---|
| 1. Independent design review | partial (user-completed; sub-agent deferred to Phase B if triggered) |
| 2. Pre-registration locked before code lands | **this document, locks after M28.4 verdict per the schedule above** |
| 3. Independent taxonomy check | N/A |
| 4. Cross-vendor judge calibration | N/A (grading is deterministic pytest) |
| 5. Honest falsifier verdict | binding via the H1 ≤ 0pp falsifier + H3 STOP gate |

## Anti-Texas-sharpshooter commitments

Same standards as M28's pre-reg. Naming explicitly:

1. **Exclusions locked before run.** Harness errors → replace trial,
   never silently drop.
2. **Three pre-registered hypotheses (H1, H2, H3).** Any post-hoc
   claim outside these three is hypothesis-generation, not a finding.
3. **Null results count.** H1 refutation is a real result. Phase A
   runs in full even if early trials suggest H1 will fail — N=10
   stays N=10.
4. **The style-constraint text is locked.** Any edit between this
   commit and M29 Phase A's first trial requires a superseded-by
   audit-log entry in the loom store.
5. **The H3 STOP gate is binding.** If it fires, the H1 verdict is
   tagged "uninterpretable due to rule leak" — not "trending
   positive."

## Sequencing relative to M28

M29 runs after M28.4 lands. M28's measured rat cell is M29's H1
baseline. The sequence:

```
M28.4 sweep runs (current)
    ↓
M28.4 verdict + finding captured (FINDINGS-m28.md)
    ↓
M29 pre-reg locked (this file edited to fill in M28's measured rat%)
    ↓
M29 Phase A — style constraint alone (N=40)
    ↓
M29 Phase A verdict
    ↓
[if M28 H1 confirmed] M29 Phase B — combined (N=40)
    ↓
M29 final findings + EFFECTIVENESS.md update
```

If at any point the M28 H3 STOP gate fired (off cell ≥ 40% in M28's
result), M29 inherits the same audit requirement: M29 cannot proceed
until the M28 H3 root cause is found, because M29's H1 baseline
becomes unreliable.

## Effort estimate

| Step | Owner | Estimated effort |
|---|---|---|
| Wait for M28.4 verdict | harness | already running |
| Edit this file to fill in M28 rat% baseline + lock | Opus session | 10 min |
| Author m29_style_smoke.py (clone of m28 harness + one block) | TBD | 1-2 hours |
| Execute N=40 Phase A sweep | harness | ~30 min wall |
| Compute Wilson CIs vs M28 baseline + render result | TBD | 0.5 day |
| Verdict + finding capture in loom store | TBD | 0.5 day |
| (If triggered) Author Phase B harness, run N=40, verdict | TBD | ~1 day |

**Total estimated effort:** 2-3 days for Phase A; +1 day if Phase B triggers.

## References

- **M28 pre-registration:** [`PRE_REGISTRATION.md`](../m28_clangd_indexer/PRE_REGISTRATION.md)
- **M22c file-path hallucination finding (analog):** REQ-7e2d6518 in
  the loom store
- **M10.2 stub indexer (baseline lineage):**
  [`FINDINGS-bakeoff-v2-cpp-stub-indexer.md`](../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md)
- **M10.3a phQ3 STOP-gate analog (rule-leak via stub):**
  [`FINDINGS-bakeoff-v2-js-stub-clean.md`](../bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md)
  — same protective pattern under H3
- **REQ-3896db58 methodology pattern:** the 5-step has earned its
  keep 5/5 in the M22 arc per REQ-44f64f5d
- **REQ-ec63fa50 (M28 temperature drift):** same drift applies here;
  M29 inherits phL2's no-explicit-temperature convention
