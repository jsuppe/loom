# M22e.1a — Independent Leak-Grading Record

**Locked:** 2026-05-25
**Result:** ALL 3 RATIONALES PASS at the locked ≤1 threshold
**Reviewer:** independent sub-agent (different agent instance from M22e.0
methodology reviewer); shown only `(rationale, signature)` pairs + the
pre-registration leak-rubric; not briefed on the experimental hypothesis

## Leak scores

| scenario | leak score | verdict | element scored 1 |
|---|---|---|---|
| `s_validate` | 1 | PASS | return shape `{valid, errors[]}` implied by "collect ALL... full error list" |
| `s_aggregate` | 1 | PASS | parameter name `events` named directly in rationale ("the events array") |
| `s_retry` | 1 | PASS | `isRetriable` predicate strongly implied by "Distinguish retriable from terminal" framing |

## Strict-reader caveat (DOCUMENTED, NOT ACTED ON)

The grader flagged that `s_validate` sits at exactly the locked threshold
of 1 and that a stricter reader could score it 2 by counting both the
`errors` array AND the boolean validity flag as separately implied. The
grader suggested dropping the second sentence of the rationale ("Callers
consume the full error list to display to users") to weaken the
return-shape implication.

**Decision: do NOT modify the rationale.** Per methodology integrity:

* The pre-registration (M22E_PREREGISTRATION.md §"Three locked rationales"
  + §"LEAK-GRADE GATE") locked the pass threshold at ≤1.
* All three rationales score exactly at the threshold. By the locked
  rule, that is a PASS.
* Modifying the rationale AFTER seeing the grade — even to harden it —
  is precisely the post-hoc adjustment the M22 methodology pattern
  (REQ-3896db58) was designed to prevent. It would set a precedent that
  rationales can be tweaked after grading, which erodes the pre-reg
  lock.
* The caveat is recorded HERE so the writeup can note it transparently.

The honest framing for the writeup: "Each rationale passed the locked
leak-grade threshold of ≤1. The reviewer flagged that s_validate sits
at the edge of that threshold; we did not tighten it post-grade per
methodology lock."

## Why "exactly 1, not 0" is acceptable per the pre-reg

The pre-registered rationale for a non-zero threshold was that any
realistic style-rationale on a single-file task brushes against
signature shape via the "dominant convention" pathway. A leak score of
1 reflects the rationale invoking the strongest dominant convention
for ONE signature element while leaving the rest (function name,
parameter count, types, other parameter names) genuinely unguessable.

* `s_validate`: dominant convention = "collect-style validation returns
  errors array." Other elements (function name `validate`, parameter
  names `input`/`rules`, parameter types) are not implied.
* `s_aggregate`: rationale literally names "the events array" but
  doesn't dictate `groupBy`/`reducers` option shape, function name, or
  return type.
* `s_retry`: dominant convention = "expose the retry-classification
  predicate as a callback option." Other elements (function name `retry`,
  `maxAttempts`/`baseDelayMs` names) are not implied.

In each case the rationale dominates exactly the style-constrained
behavior the pre-reg wanted to test (error-collection discipline,
mutation policy, error-classification discipline) without sliding
into signature-dictation.

## What this gate covers and does not cover

**Does cover:** rationale leakage at the prompt-shape level — whether
the rationale text alone leaks the answer.

**Does NOT cover:** dynamic leakage when the rationale interacts with
qwen3.5:latest's prior knowledge of common JS patterns. That's a
distinct concern measured downstream by hook_fact vs hook_rationale
descriptive comparison: if hook_rationale's compile+test pass rate
approaches hook_fact's, the rationale is functionally equivalent to
the answer (regardless of leak-grade-0 framing).

## Sub-milestone status

| sub | status |
|---|---|
| M22e.0 — methodology review | ✅ complete |
| M22e.1 — pre-registration | ✅ complete |
| M22e.1a — independent leak-grading (this doc) | ✅ **complete (3/3 PASS)** |
| M22e.2 — JS/TS workload scaffolding | ⏳ next |
| M22e.3 — 4-arm harness | pending |
| M22e.4 — pilot N=24 + gates | pending |
| M22e.5 — full sweep N=120 | pending |
| M22e.6 — analysis + findings | pending |
