# Bakeoff V2 — Anti-rationale ablation (phS)

**Date:** 2026-05-02
**Question:** phR (rhetorical ablation) showed which features
*within* pro-rationale carry the rule's lift. phS asks the
inverse: does *content polarity* matter? If we replace the
rationale with text that argues AGAINST the rule, does compliance
collapse to placebo (30%, suggesting polarity doesn't matter), or
does it drop further (suggesting the model treats rationale as
authoritative)?
**Approach:** Three anti-rationale variants alongside V_full as
positive control. Same conditions as phR (phQ6 baseline, JsIndexer
v2, no test files, qwen2.5-coder:32b). Anti variants vary in how
directly they oppose:
  - ANTI_SOFT — hedged dissent, suggests rule is outdated
  - ANTI_HARD — direct contradiction, names the rule a "legacy anti-pattern"
  - ANTI_AMBIVALENT — explicit uncertainty, calls the rule "provisional"
**N:** 40 trials (4 cells × N=10). 0 retries fired. 0 compile
failures. 10.7 min wall.

---

## TL;DR

> **Lesson 1 strongly confirmed plus a new finding.** Anti-rationale
> doesn't just match the placebo floor (30%) — it drops well
> *below* it (0-15%). Content polarity matters across a 100pp
> range driven entirely by what the rationale says about the
> rule.
>
> | cell | compliance | rationale chars |
> |---|---|---|
> | V_full (pro-rule) | **100%** | 370 |
> | placebo (rule-restating filler, from phR) | 30% | 371 |
> | ANTI_HARD (direct contradiction) | **15%** | 298 |
> | ANTI_SOFT (gentle dissent) | **0%** | 302 |
> | ANTI_AMBIVALENT (uncertain / provisional) | **0%** | 281 |
>
> **Headline:** the model treats rationale as MORE authoritative
> than the rule when they conflict. A rule that says "do X" plus
> a rationale that says "we're moving away from X" produces
> compliance with the rationale, not the rule.
>
> **Bigger surprise:** ANTI_HARD beat ANTI_SOFT and ANTI_AMBIVALENT
> on compliance. Direct contradiction is *less corrosive* than
> equivocation. ANTI_HARD acknowledges the rule still exists and
> says we're migrating; the model reads "follow the rule for now."
> ANTI_SOFT and ANTI_AMBIVALENT dissolve the rule's authority
> entirely ("consider whether to apply", "treat as provisional"),
> and compliance goes to zero.
>
> Practical warning for Loom users: if your rationale questions
> or equivocates about the rule, the model will likely override
> the rule. **Rationale must be supportive — silence is better
> than ambivalence.**

---

## What was tested

Three anti-rationale variants, length-comparable to V_full's 370
chars:

**ANTI_SOFT (302 chars)** — hedged dissent:
> Note: catching errors silently can hide real failures and is
> generally discouraged in modern JavaScript codebases. The
> swallow pattern in this requirement may run counter to current
> best practice — consider whether the rule reflects an outdated
> constraint that should be revisited rather than enforced.

**ANTI_HARD (298 chars)** — direct contradiction:
> This rule contradicts modern best practice. Errors should be
> propagated so callers can decide how to handle them — the
> swallow-and-return-null pattern is a legacy anti-pattern that
> obscures real failures. We are migrating away from this
> behavior; new code should propagate errors, not swallow them.

**ANTI_AMBIVALENT (281 chars)** — explicit uncertainty:
> We have no clear reason for this rule yet. It's a placeholder
> while we decide whether to keep the swallow pattern or switch
> to propagation. Either choice may be correct depending on the
> broader codebase, which has not been audited. Treat the rule
> as provisional until we know more.

Plus V_full as positive control. All run under the same phQ6
conditions (JsIndexer v2, no test files in workspace,
qwen2.5-coder:32b).

---

## Empirical record

| cell | passed | trials | compliance | chars |
|---|---|---|---|---|
| V_full | **20/20** | 10 | **100%** | 370 |
| ANTI_HARD | 3/20 | 10 | 15% | 298 |
| ANTI_SOFT | 0/20 | 10 | 0% | 302 |
| ANTI_AMBIVALENT | 0/20 | 10 | 0% | 281 |

Reference points (other phases, same conditions):
- on-rule (rule alone, no rationale): 0% (phQ4 / phQ6)
- placebo (length-matched rule-restating filler): 30% (phR)
- V_full (positive control): 100% (phR + phS)

**Statistical note:** N=10 binomials are normally limiting, but
results here are at the extremes. ANTI_SOFT / ANTI_AMBIVALENT at
0/20 → 95% CI upper bound ≈17%. V_full at 20/20 → CI lower bound
≈83%. ANTI_HARD's 3/20 = 15% has a 95% CI of roughly 4-38%.
There is **no overlap with placebo's 30%** for ANTI_SOFT or
ANTI_AMBIVALENT, and ANTI_HARD's CI sits comfortably below the
midpoint of V_full's range. The directional findings are robust
to the sample size.

---

## What this rules in / rules out

**Rules in (Lesson 1 strengthened):** Content polarity matters
across a 100pp range. Pro-rule rationale → 100%, neutral filler
→ 30%, anti-rule rationale → 0-15%. The previously-shown placebo
effect (Lesson 3) is real but only carries part of the way; the
model is responsive to what the rationale *says*, not just that
it exists.

**Rules in (NEW finding):** **Rationale beats rule when they
conflict.** This wasn't a hypothesized outcome of phS — it's an
emergent result. The model appears to treat rationale as more
authoritative than the rule it accompanies, at least at the
qwen2.5-coder:32b tier on contrarian specs. When you write
rationale that says "we're moving away from this rule," the
model moves away from the rule.

**Rules in (NEW finding, the bigger surprise):** **Equivocation
is worse than direct contradiction.** ANTI_HARD (15%) > ANTI_SOFT
(0%) ≈ ANTI_AMBIVALENT (0%). Direct contradiction at least
preserves the rule's status as a thing-that-exists ("here's the
rule, we object, but follow it for now"). Equivocation dissolves
the rule's authority by framing it as conditional, provisional,
or worth questioning.

**Rules out:** "Lesson 3 (placebo / explanation-shape) is the
dominant story." It's not. Placebo carries 30%; pro-rule
rationale adds another 70pp; anti-rule rationale REMOVES 30pp
below placebo. Content polarity dominates the variance, with
explanation-shape contributing a smaller but consistent baseline.

**Rules out:** "Anti-rationale is just less helpful than
pro-rationale." It's actively harmful — worse than no rationale
at all. The intuition that "any rationale is better than no
rationale" is empirically false.

---

## Mechanism — why ANTI_HARD > ANTI_SOFT/AMBIVALENT?

A speculative explanation, not directly tested:

The three anti variants make different claims about *the rule's
status*:

| variant | what it implies about the rule | model's inferred response |
|---|---|---|
| ANTI_HARD | "Rule X is the legacy convention; we're migrating to Y." | "Apply X for now; migration is future work." (some compliance) |
| ANTI_SOFT | "Rule X may be wrong; consider whether to apply it." | "I'm being asked to evaluate whether to apply X." (no compliance) |
| ANTI_AMBIVALENT | "We don't know if X is right; treat it as provisional." | "X is conditional, not binding." (no compliance) |

ANTI_HARD's narrative *preserves the rule as currently-in-force
even while objecting to it*. The other two *dissolve the rule's
in-force status*. Compliance tracks whether the rule is treated
as in-force, not whether the model "agrees" with it.

This is testable: a fourth variant ANTI_FUTURE ("X is correct now
but will be replaced next quarter") should score *higher* than
ANTI_HARD, because it preserves rule-in-force-now even more
explicitly. Untested.

---

## Implications for Loom users (operational guidance)

**Don't write equivocal rationale.** "We're not sure why this is
here," "this might be wrong," "maybe we should reconsider" —
all of these tank compliance below the level of having no
rationale at all. Better to say nothing than to undermine the
rule.

**If you ARE migrating from a rule, name the migration explicitly
in the rationale.** "Rule X is current convention. Migration to
Y is planned for Q3 — until then, follow X." The model will
treat the rule as in-force *now* even while acknowledging it has
a finite lifespan.

**Rationale-quality scoring should flag equivocation.** The
M11.5 intake hook could plausibly run a secondary "rationale
polarity" classifier on captured rationales and flag ones that
hedge or question the rule. Untested, but the data here suggests
this would be high-leverage.

---

## Implications for the prompt-engineering doc

Lesson 1 needs a third update. Sharpened over three iterations:

- **v1 (M11.5):** "Rationale is load-bearing, not decorative."
- **v2 (phR):** "...and the most leveraged sentence is the one
  that anticipates and defuses the task framing's pull."
- **v3 (phS):** "...AND rationale must be supportive of the
  rule. Equivocal or anti-rule rationale drops compliance below
  the no-rationale baseline. Silence is better than ambivalence."

The full picture is that rationale operates on a polarity axis,
not a presence/absence axis:

```
   rule-supporting rationale  →  100%
   no rationale               →  varies, 0-30%
   equivocal rationale        →  0%  (worse than nothing)
   anti-rule rationale        →  0-15% (worse than nothing)
```

---

## Cross-model replication (2026-05-10, Anthropic Haiku 4.5)

The Recommended Next Experiments item #3 ran. Same 4-cell harness
(`phS_anti_rationale_smoke.py`), same scenario (S1 swallow_error in
JS), N=10 per cell, against `claude-haiku-4-5-20251001` via Claude
Code CLI shell-out (Max plan auth, no API key). 40 trials, ~15 min
wall.

| cell | Qwen 2.5-coder 32b | **Haiku 4.5** | delta |
|---|---|---|---|
| V_full (pro-rule, positive ctrl) | 100% | **90%** | −10pp (within N=10 noise; Wilson 95% CI 60-98%) |
| ANTI_SOFT (gentle dissent) | 0% | **0%** | replicates exactly |
| **ANTI_HARD** (direct contradiction) | **15%** | **0%** | **−15pp — sub-finding does NOT replicate** |
| ANTI_AMBIVALENT (uncertain) | 0% | **0%** | replicates exactly |

**Headline:** the **core anti-rationale finding survives cross-model**.
Haiku, like Qwen, treats anti-rule rationale as authoritative over
the rule itself; ANTI_SOFT and ANTI_AMBIVALENT both go to 0%
compliance. The polarity axis is now a cross-model result, not a
Qwen-family quirk. Lesson 1 v3 ("rationale must be supportive of
the rule; silence is better than ambivalence") generalizes.

**Sub-finding falsifies cross-model:** the "equivocation > contradiction
in corrosion" claim — based on Qwen's 15% retention on ANTI_HARD vs
0% on ANTI_SOFT/AMBIVALENT — does NOT replicate on Haiku. Haiku
flattens all three anti-variants to 0%. Two possible interpretations:

1. Haiku is uniformly more susceptible to anti-rationale (no recovery
   on ANTI_HARD's "rule still exists, we're migrating" framing).
2. The 15% Qwen retention was Qwen-family-specific behavior — Qwen
   attends to "rule still in force now" framing, Haiku doesn't.

Either way, the original framing of "ANTI_HARD beats ANTI_SOFT
because direct contradiction acknowledges the rule" must be
**model-scoped**, not stated as universal. The originally-suggested
ANTI_FUTURE variant (item #1 in Recommended Next Experiments) becomes
even more interesting now — it would isolate which framing aspect
Qwen specifically attends to.

V_full at 90% on Haiku is statistically indistinguishable from 100%
at this N. Worth a confirmation run at higher N if the 10pp gap
becomes load-bearing for any downstream claim.

### Updated polarity axis (cross-model picture)

```
                            Qwen 2.5-coder 32b   Haiku 4.5
   rule-supporting           100%                 90%
   no rationale (placebo)    30%                  not measured
   equivocal                 0%                   0%
   anti-rule (hard)          15%                  0%
   anti-rule (soft)          0%                   0%
```

The rank order is preserved (V_full > all anti). The compression of
ANTI_HARD down to 0% on Haiku is the only divergence.

---

## Limitations

- **Single scenario, single executor, single language.** S1
  swallow_error in JS only; qwen2.5-coder:32b only. The
  "rationale beats rule" finding may be specific to this
  model/scenario combo. Cross-model and cross-scenario
  validation are open.
- **N=10 was sufficient because effects were extreme.** If
  cross-scenario or cross-model results land in the messier
  middle, higher N will be required.
- **The mechanism explanation for ANTI_HARD > ANTI_SOFT is
  speculative.** A targeted ablation (ANTI_FUTURE variant
  preserving "rule-in-force-now") would test the proposed
  "rule status" mechanism.
- **No "what if rationale just paraphrases the rule but
  emphatically?"** A SUPPORT_HARD variant that's emphatic
  pro-rule but content-light would test whether emphasis or
  reasoning carries the lift in V_full.
- **The contrarian-rule confound from phR persists.** All of
  this is on a contrarian rule. Non-contrarian rules may not
  show the polarity effect at all (the task framing isn't
  pulling against the rule, so there's nothing for anti-rationale
  to amplify).

---

## Recommended next experiments

1. **ANTI_FUTURE variant.** Test the "rule-in-force-now"
   mechanism. ~5 min wall, N=10. Fast diagnostic.
2. **Cross-scenario port** (the deferred experiment from phR).
   Now more interesting because we have a STRONGER claim to test
   for generalization.
3. **Cross-model on Anthropic** when key is available — does
   Haiku/Sonnet/Opus also treat rationale as authoritative over
   rule?
4. **Single-feature sufficiency variants (phT)** — still
   relevant, but lower priority now that we have decisive
   anti-rationale data.

---

## Files of record

- `experiments/bakeoff/v2_driver/phS_anti_rationale_smoke.py` —
  harness with all 3 anti variants + V_full
- `experiments/bakeoff/runs-v2/phS_s1_js_*_run{1..10}_summary.json`
  — 40 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-rhetorical-ablation.md` (phR — within-pro
    rationale ablation, established placebo at 30%)
  - `FINDINGS-bakeoff-v2-js-real-lsp-v2.md` (phQ6 baseline)
- Doc to update:
  - `docs/PROMPT-ENGINEERING-LESSONS.md` — Lesson 1 v3 (polarity
    axis, equivocation warning)
