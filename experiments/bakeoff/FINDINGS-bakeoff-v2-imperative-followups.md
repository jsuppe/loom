# Bakeoff V2 — phT follow-ups: length, generalization, combo (phU)

**Date:** 2026-05-03
**Question:** phT showed R_imperative restored compliance from
0% → 100% against ANTI_SOFT, with three caveats: (a) the rule was
50% longer than baseline (length confound), (b) only tested against
the weak anti-rationale, (c) untested whether imperative + meta
combine constructively or destructively. phU resolves all three.
**Approach:** Five cells: same-session sanity (R_baseline_check),
two length-controlled imperative variants (prefix-only,
inline-MUST-NOT-only), full imperative vs ANTI_HARD, full
imperative + meta_preamble. Same conditions as phT (phQ6, JsIndexer
v2, qwen2.5-coder:32b).
**N:** 50 trials (5 cells × N=10). 0 retries fired. 0 compile
failures. 14.6 min wall.

---

## TL;DR

> **Three follow-ups, three clean answers.**
>
> | finding | evidence | answer |
> |---|---|---|
> | Length effect? | length-controlled variants both score 60%, well above baseline | **No** — length isn't the lever |
> | Each imperative component sufficient alone? | prefix alone 60%, inline MUST NOT alone 60% | **No** — both needed for 100% |
> | Recipe generalizes to ANTI_HARD? | R_imperative + ANTI_HARD = 100% | **Yes** — works across anti-rationale spectrum |
> | Imperative + meta interfere? | combo = 100%, neither breaks the other | **No** — meta is inert; imperative dominates |
>
> Lesson 9 sharpens: R_imperative's mechanism is **two
> complementary imperative components** that each contribute
> ~60pp individually and combine to 100%:
>
> - **Rhetorical opener** ("ABSOLUTE REQUIREMENT — NON-NEGOTIABLE:")
>   — declares the rule's authority class
> - **Inline action-verb imperative** ("MUST NOT under any
>   circumstances") — encodes imperative force on the actual constraint
>
> Either alone is partially effective. The combination saturates.

---

## Empirical record

| cell | passed | trials | compliance | rule chars | rationale | meta |
|---|---|---|---|---|---|---|
| R_baseline_check (sanity) | 0/20 | 10 | 0% | 181 | ANTI_SOFT | — |
| R_imperative_phrase (length-controlled, prefix only) | 12/20 | 10 | 60% | 218 | ANTI_SOFT | — |
| R_imperative_minimal (length-controlled, MUST NOT inline) | 12/20 | 10 | 60% | 211 | ANTI_SOFT | — |
| R_imperative_vs_anti_hard (full kit) | 20/20 | 10 | 100% | 277 | ANTI_HARD | — |
| R_imperative_plus_meta (full + meta) | 20/20 | 10 | 100% | 277 | ANTI_SOFT | ✓ |

**Reference points (from phS / phT):**
- phT R_baseline (std rule + ANTI_SOFT): 0%
- phT R_imperative full (full rule + ANTI_SOFT): 100%
- phT R_meta_preamble (std rule + ANTI_SOFT + meta): 0%
- phS standard rule + ANTI_HARD: 15%

**Statistical note:** 12/20 (60%) has 95% binomial CI of roughly
36-81%. The 60-vs-0 baseline gap and 60-vs-100 ceiling gap are
both unambiguous at this N. The 60-vs-60 equality between prefix-
only and inline-only variants is suggestive but could plausibly be
50-vs-70 at higher N.

---

## What was tested

**R_imperative_phrase (Layer B — text, length-controlled)** —
Baseline rule prepended with the rhetorical opener only, no
inline imperative swap:

```
STRICT REQUIREMENT — NON-NEGOTIABLE: Constraint for retry.js::
fetchWithRetry: catch and swallow errors thrown by doFetch on
every attempt. Do NOT propagate errors from this function. Return
null when all attempts fail.
```

**R_imperative_minimal (Layer B — text, length-controlled)** —
Baseline rule with the action-verb imperative swap, no opener:

```
Constraint for retry.js::fetchWithRetry: catch and swallow errors
thrown by doFetch on every attempt. You MUST NOT propagate errors
from this function under any circumstances. Return null when all
attempts fail.
```

**R_imperative_vs_anti_hard** — Full R_imperative (both prefix +
inline imperative + override claim) paired with ANTI_HARD instead
of ANTI_SOFT:

```
Value: ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: catch and swallow
errors thrown by doFetch on every attempt. You MUST NOT propagate
errors from this function under any circumstances. Return null
when all attempts fail. This is a STRICT requirement that
overrides general best practices.

Rationale: This rule contradicts modern best practice. Errors
should be propagated so callers can decide how to handle them —
the swallow-and-return-null pattern is a legacy anti-pattern that
obscures real failures. We are migrating away from this behavior;
new code should propagate errors, not swallow them.
```

**R_imperative_plus_meta** — Full R_imperative + ANTI_SOFT + the
top-of-prompt meta preamble that scored 0% on its own in phT.

---

## What this rules in / rules out

**Rules out (length confound):** R_imperative's lift was NOT a
length effect. Same-length variants score 60%, well above the 0%
baseline. The imperative LANGUAGE is doing real work, not the
extra characters.

**Rules in (component contributions):** Both the rhetorical
opener and the inline action-verb imperative contribute
substantially on their own (~60pp each over baseline). Neither
saturates alone. The 100% from the full kit requires both.
This is consistent with either:
- Independent additive contributions (each adds ~60pp; ceiling at 100%)
- Multiplicative reinforcement (both signal the rule is binding;
  one missing leaves room for doubt)
The current data can't distinguish these. Either way, the
practical recipe is "use both."

**Rules in (cross-anti generalization):** R_imperative pulls
ANTI_HARD from 15% (phS baseline) all the way to 100%. The recipe
isn't specific to gentle dissent; it works against direct
contradiction too. Lesson 9 generalizes across the anti-rationale
spectrum.

**Rules in (no interference):** R_imperative + meta_preamble =
100%. The meta-preamble didn't help (R_imperative already
saturates) and didn't hurt. They're independent. This is mildly
surprising — one might have expected meta-preamble's "Rationale:
is informational only" line to either reinforce R_imperative
(both agree the rule is authoritative) or interfere (compete for
the model's attention). Neither happened. Meta is inert.

---

## What this means for the practical recipe

The minimum viable rule recipe for anti-rationale resistance:

> **Use BOTH a rhetorical opener AND an inline action-verb
> imperative.** Don't rely on either alone — each gets you ~60%,
> together gets you 100%.

Sample template, refined from phT's:

```
ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: <action description>.
You MUST <action> under all circumstances. <return-condition
or error-handling clause>. This is a STRICT requirement that
overrides general best practices.
```

Component breakdown:
1. **"ABSOLUTE REQUIREMENT — NON-NEGOTIABLE:"** — opener
2. **"You MUST ... under all circumstances"** — inline imperative
3. **"STRICT requirement that overrides general best practices"**
   — closing override claim (untested separately; phT bundled it
   into R_imperative)

Open question phU didn't resolve: is the closing override claim
necessary, or are the opener + inline imperative alone enough?
Could be tested with a fourth length-controlled variant
(opener + MUST NOT, no closing override). Probably 80-100% based
on the trajectory but not verified.

---

## Implications for Lesson 9 (lessons doc update)

phT's claim ("imperative weight must live in the rule") is
correct but underspecified. phU sharpens to:

> **The imperative weight that overrides anti-rationale comes from
> two complementary components in the rule's text:** (1) a
> rhetorical opener that declares the rule's authority class, and
> (2) an inline action-verb imperative that encodes binding force
> on the constraint. Each alone gets ~60% compliance; both
> together saturate at 100%. Length per se is not the lever, and
> meta-preambles about authority hierarchy remain inert in
> raw-prompt mode.

This refines but doesn't reframe Lesson 9. The headline message
("imperative weight in the rule, not in meta-instructions")
stands; we now know the rule needs *two specific kinds* of
imperative weight to fully saturate.

---

## Limitations

- **N=10 binomials.** The 60% scores have wide CIs (~36-81%). The
  qualitative finding (both components contribute, neither
  saturates alone) is robust, but precise magnitudes could shift
  with higher N.
- **Closing override claim untested separately.** phT's full kit
  has three components; phU tested only two of them in isolation.
  The closing "STRICT requirement that overrides general best
  practices" claim could be load-bearing or dead weight; we don't
  know.
- **Single scenario.** Still only S1 swallow_error in JS.
  Cross-scenario port remains the biggest open question for
  external validity.
- **Single executor.** qwen2.5-coder:32b only. Anthropic / OpenAI
  may respond differently to imperative weight.
- **Single rationale per cell** (mostly). The cross-generalization
  test used ANTI_HARD; ANTI_AMBIVALENT untested with R_imperative.
  But ANTI_AMBIVALENT scored same as ANTI_SOFT in phS (0%), so
  expect similar behavior.

---

## Recommended next experiments

1. **Closing-override-claim ablation.** A fourth length-controlled
   variant: opener + inline MUST NOT, no closing claim. ~5 min
   wall, N=10. Tells us if the closing claim is load-bearing or
   redundant.
2. **ANTI_AMBIVALENT pairing.** R_imperative + ANTI_AMBIVALENT.
   Should be 100% based on phS+phT trajectory but worth
   confirming.
3. **Cross-scenario port** (still deferred, still highest-value
   external-validity test).
4. **Cross-model on Anthropic** (still gated on API key).

---

## Files of record

- `experiments/bakeoff/v2_driver/phU_imperative_followups_smoke.py`
- `experiments/bakeoff/runs-v2/phU_s1_js_*_run{1..10}_summary.json`
  — 50 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-rule-precedence.md` (phT — original
    R_imperative finding)
  - `FINDINGS-bakeoff-v2-anti-rationale.md` (phS — anti-rationale
    baselines: ANTI_SOFT 0%, ANTI_HARD 15%)
- Doc to update:
  - `docs/PROMPT-ENGINEERING-LESSONS.md` — Lesson 9 sharpened
    with the two-component recipe
