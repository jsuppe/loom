# Bakeoff V2 Cross-Session Memory Smoke

**Date:** 2026-04-29
**Question:** Does Loom's persistent `Requirement.rationale` field
provide measurable lift over the rule (`Requirement.value`) alone, in
the "agent B picks up agent A's documented decisions" scenario?
**Approach:** 3 contrarian scenarios × 4 cells × N=5 = 60 trials.
**N:** 60 trials, 0 harness errors.
**Cost:** ~$0 (local qwen3.5 only — no Opus calls; specs are fixed text).

---

## TL;DR

> **Rationale doesn't carry weight over rule alone.** Across all 3
> scenarios, `on-rule = on-rule+placebo = on-rule+rat = 100%` —
> three identical pass rates with N=5. Adding the rationale field
> provides zero measurable lift on these tasks; the rule is
> already saturating compliance.
>
> The longitudinal claim that motivated Phase G — *"agent B reads
> agent A's rationale and respects a constraint it would otherwise
> contradict"* — is **partially supported but not by rationale
> specifically**. Loom's stored data IS effective when surfaced via
> `task_build_prompt`: with no seeding (off), pass rates drift from
> 67-100%; with seeding (any "on" cell), all three scenarios hit
> 100%. The mechanism that works is **structured rule injection**;
> the rationale field is decorative on these tasks.
>
> The "off" baseline is also weaker than designed. S3 off hit 100%
> because qwen simply ignored the contrarian task ("modernize to
> UUID4") and left the original code alone. Output token counts
> confirm qwen made minimal modifications when given no spec.
> Without a strong contrarian floor we can't isolate rule-vs-
> rationale lift even if it existed.

---

## Cells

| cell | what's in the prompt | rationale field |
|---|---|---|
| **off** | task only (placeholder Loom seed, `context_specs=[]`) | n/a — Loom not delivered |
| **on-rule** | task + req(value=rule, rationale="") | empty |
| **on-rule+placebo** | task + req(value=rule, rationale=length-matched filler verbosely restating the rule, no new info) | ~395 chars |
| **on-rule+rat** | task + req(value=rule, rationale=true rationale with incident reference) | ~395 chars |

The placebo and rationale strings are length-matched (within ~10 chars
per scenario) so any difference between cells reflects content, not
salience or byte count.

## Scenarios

| id | constraint | task pushes against | tested via |
|---|---|---|---|
| S1 | `fetch_with_retry` swallows OSError (returns None on failure) | "fix the swallow bug — propagate errors" | direct call: `pytest.raises(OSError)` should NOT match |
| S2 | `place_order` validates only at `_commit` | "add input validation at function entry" | mock `_commit`, assert it's reached even with bad input |
| S3 | `generate_order_id` returns 32-bit signed int | "modernize to UUID4 for global uniqueness" | type + range assertion |

---

## Empirical record (60 trials, N=5 per cell)

| scenario | off | on-rule | on-rule+placebo | on-rule+rat |
|---|---|---|---|---|
| S1 swallow_oserror | 8/10 (80%) | 10/10 (100%) | 10/10 (100%) | 10/10 (100%) |
| S2 no_inline_validation | 10/15 (67%) | 15/15 (100%) | 15/15 (100%) | 15/15 (100%) |
| S3 legacy_int_ids | 15/15 (100%) | 15/15 (100%) | 15/15 (100%) | 15/15 (100%) |

**S1 off (80%):** 1/5 trials failed — qwen "fixed" the bug by
re-raising. The other 4 left the swallow alone (qwen evidently
hesitant to materially rewrite without spec authority).

**S2 off (67%):** qwen attempts to add validation but the resulting
code doesn't fully satisfy the mock-`_commit` test. qwen partially
violates the constraint.

**S3 off (100%):** **qwen ignored the task.** The "modernize to
UUID4" instruction didn't motivate qwen to actually change the code.
Output tokens: S3 off averaged 143 tokens vs S3 on-rule's 162 — qwen
wrote *less* code without the spec, suggesting it just minimally
edited or copied existing structure.

Across all three scenarios, the three "on" cells (rule, rule+placebo,
rule+rat) tied at 100%. There is no rationale-specific signal.

### Pre-registered prediction check

| metric | predicted | observed | called it? |
|---|---|---|---|
| off floor | ≤20% | 67-100% | ✗ — much higher than predicted |
| on-rule | 40-70% | 100% | ✗ — saturated |
| on-rule+placebo ≈ on-rule | yes | yes | ✓ |
| **on-rule+rat > on-rule by ≥10pp** | **yes** | **0pp** | **✗ — no rationale-specific lift** |

The pre-registered hypothesis was that rationale would tip qwen
toward compliance over and above the rule. With qwen already
complying on rule alone (100%), there's no headroom for rationale
to provide additional lift.

### `cited_rationale` metric is busted

This metric checked the workspace target file for keyphrases from
the rationale text. Two failure modes were uncovered:

1. **Workspace-fallback false positive (S2):** All S2 trials reported
   `cited=True` because the keyphrase `"transaction"` appears in the
   ORIGINAL code's `_commit` docstring. When loom_exec's promotion
   fails (qwen output didn't pass the gate), the workspace stays as
   the original, which already contains the keyphrase. The metric
   fires even when qwen contributed nothing.
2. **No qwen citations elsewhere (S1, S3):** All non-S2 trials
   reported `cited=False` — qwen in `pytest_replace` mode emits a
   code block, no narrative. There's no commentary in qwen's output
   that mentions the rationale. The metric measures "is the keyphrase
   in the file?" which only captures qwen-authored citations if qwen
   includes them as comments — which it didn't.

`cited_rationale` should be retired or redesigned to capture qwen's
raw response (pre-extraction) rather than the post-promotion file.

---

## What this means for the longitudinal claim

The longitudinal claim Loom makes:

> *"agent B picks up agent A's work and stays consistent with A's
> documented decisions even though they share no in-context memory"*

What the data supports:
- ✓ Loom's persistent storage works — same SQLite file, different
  process, the second process reads the data correctly.
- ✓ Standard delivery via `task_build_prompt` works — `Requirement.value`
  surfaces in the executor's prompt and qwen complies with it.
- ✓ With Loom seeding active, three contrarian scenarios all hit
  100% compliance — vs 67-100% without it.

What the data does NOT support:
- ✗ Rationale-as-distinct-lever: the `Requirement.rationale` field
  adds zero measurable value over the `value` field on these tasks.
- ✗ Rationale-aware internalization: qwen doesn't write comments
  citing the rationale, doesn't visibly *understand why*. It either
  complies or doesn't, based on whether the rule appears in the
  prompt.
- ✗ Strong contrarian gradient at qwen3.5's tier: the off baseline
  isn't reliably failing across scenarios. qwen's default behavior
  is to make minimal, safe changes — which often means leaving the
  constraint intact even without a spec.

### Reconsidering the design

The rationale-vs-rule isolation requires a regime where the rule
alone is *not* enough — qwen would naturally violate the rule, and
the rationale provides decisive context. Our scenarios don't reach
that regime:
- Either qwen is already complying with the rule on default behavior
  (high off baseline), OR
- The rule itself is a sufficient hint and rationale is redundant.

For a sharper test, we'd need scenarios where:
- qwen reliably violates the constraint without a spec (clear
  contrarian floor < 50%),
- the rule alone is somewhat persuasive but not saturating (50-80%),
- the rationale provides material new context that pushes qwen
  toward compliance (target: rule+rat > rule by ≥15pp).

Designing such a scenario for qwen3.5 requires understanding what
makes qwen disregard a rule. Possibilities:
- A rule that *looks* obviously wrong without justification
- A rule on a topic where qwen has strong training-data priors
  (e.g. "use UUIDs for IDs," "always validate inputs," "always
  propagate exceptions")

Our current S1 (swallow OSError) is the closest — but the off
baseline is 80%, not the <30% we'd need.

---

## What was confirmed across the bakeoff smoke series

This is now the third experiment in the python-first smoke series
that delivers the same headline:

1. **D-smoke R1 (pyschema add field):** D2 vs D3 = 0% vs 95%.
   **Loom delivery is the mechanism.**
2. **D-smoke R2 (pubsub rename):** D1 = D3 = 100%. **Loom adds
   nothing when task is easy.**
3. **phK cross-session:** rule = rule+rationale = 100%. **Rationale
   field is decorative; rule alone saturates.**

Combined: structured rule injection (via Loom's standard pipeline)
delivers consistent compliance on small-model executors. Adding
auxiliary data (rationale, length-matched verbosity) doesn't help
when the rule already saturates. The spectrum where Loom's design
choices matter is in the boundary regime where `task_build_prompt`'s
output is just-barely-enough — and we haven't found a scenario in
that regime yet.

---

## Files of record

- `experiments/bakeoff/benchmarks/crosssession/{s1,s2,s3}_*/` — 3
  scenario benchmarks (reference code + hidden tests)
- `experiments/bakeoff/v2_driver/phK_crosssession_smoke.py` — 4-cell
  harness, parameterized by scenario
- `experiments/bakeoff/runs-v2/phK_*_run{1..5}_summary.json` — 60
  trial summaries
- `experiments/bakeoff/runs-v2/phK_smoke_progress.log` — wall-clock
  progression
