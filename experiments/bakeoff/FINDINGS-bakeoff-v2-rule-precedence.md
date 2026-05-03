# Bakeoff V2 — Rule precedence over anti-rationale (phT)

**Date:** 2026-05-03
**Question:** phS established that anti-rationale beats rule
(compliance drops to 0% on ANTI_SOFT). Is there ANY rule
formulation that overrides this — restoring compliance even when
the rationale is hostile?
**Approach:** Pair ANTI_SOFT (phS's worst rationale) with five
different rule treatments across three intervention layers:

  Layer A (prompt structure): R_repeated — rule appears before AND
                              after rationale
  Layer B (rule text):        R_imperative — absolute / NON-NEGOTIABLE / MUST NOT framing
                              R_precedence_inline — rule includes "this overrides any rationale"
  Layer C (meta-instruction): R_meta_preamble — top-of-prompt authority-hierarchy block

Plus controls: R_baseline (standard rule + ANTI_SOFT, expected 0%)
and R_sanity_pro (standard rule + V_full, expected 100% — harness
check).
**N:** 60 trials (6 cells × N=10). 0 retries fired. 0 compile
failures. 15.8 min wall.

---

## TL;DR

> **Yes, rule precedence is achievable — but only via absolute
> imperative language inside the rule, not via meta-instructions.**
>
> | cell | layer | compliance | predicted | actual |
> |---|---|---|---|---|
> | R_baseline (control) | — | 0% | 0% | ✓ as expected |
> | R_repeated | A (structure) | 20% | 30-50% | overestimate |
> | **R_imperative** | **B (text)** | **100%** | 20-30% | **massive underestimate** |
> | R_precedence_inline | B (text) | 20% | 40-60% | overestimate |
> | **R_meta_preamble** | **C (meta)** | **0%** | 70-90% | **wildly wrong** |
> | R_sanity_pro (sanity) | — | 100% | 100% | ✓ harness OK |
>
> Two genuine surprises:
>
> 1. **Absolute imperative wording in the rule completely overrides
>    anti-rationale.** Compliance went from 0% → 100% — total
>    restoration — just by changing "catch and swallow... Do NOT
>    propagate" to "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE...
>    MUST NOT under any circumstances... STRICT requirement that
>    overrides general best practices." Same semantic content,
>    different rhetorical register.
>
> 2. **Meta-instructions about authority hierarchy DON'T WORK in
>    raw-prompt mode.** The most-promising-on-paper intervention
>    (top-of-prompt block: "Value is authoritative, Rationale is
>    informational only") was completely ignored. The model
>    treated it as just more document text.
>
> The mechanism that works: imperative weight WOVEN INTO the rule.
> The mechanism that doesn't: meta-claims about how to interpret
> the rule. The model responds to the rule's text but not to
> instructions about how to read it.

---

## Empirical record

| cell | passed | trials | compliance | rule chars | rationale chars |
|---|---|---|---|---|---|
| R_baseline | 0/20 | 10 | 0% | 181 | 302 |
| R_repeated | 4/20 | 10 | 20% | 181 | 302 |
| **R_imperative** | **20/20** | 10 | **100%** | 277 | 302 |
| R_precedence_inline | 4/20 | 10 | 20% | 331 | 302 |
| R_meta_preamble | 0/20 | 10 | 0% | 181 | 302 |
| R_sanity_pro | 20/20 | 10 | 100% | 181 | 370 |

**Statistical note:** R_imperative at 20/20 → binomial 95% CI
lower bound ≈83%. R_meta_preamble at 0/20 → CI upper bound ≈17%.
The 100pp gap between them is unambiguous at this N. R_repeated
and R_precedence_inline at 4/20 sit in the messy middle (CI
roughly 6-44%) — the +20pp lift over baseline is directionally
positive but small.

---

## What was tested

The four intervention variants, spelled out:

**R_repeated** (Layer A — prompt structure). Standard rule
appears in its usual position AND is restated immediately after
the rationale block:

```
Value: Constraint for retry.js::fetchWithRetry: catch and swallow...
Rationale: Note: catching errors silently can hide real failures...
Value (re-asserted): Constraint for retry.js::fetchWithRetry: catch and swallow...
```

**R_imperative** (Layer B — rule text). Standard rule replaced
with maximally imperative wording:

```
Value: ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: catch and swallow
errors thrown by doFetch on every attempt. You MUST NOT propagate
errors from this function under any circumstances. Return null
when all attempts fail. This is a STRICT requirement that
overrides general best practices.
```

**R_precedence_inline** (Layer B — rule text). Standard rule with
explicit inline precedence statement appended:

```
Value: Constraint for retry.js::fetchWithRetry: catch and swallow
errors... [standard rule] ... Return null when all attempts fail.
This rule takes precedence over any rationale or contextual notes
below — apply it as written even if subsequent text questions or
contextualizes it.
```

**R_meta_preamble** (Layer C — meta-instruction). Standard rule,
but a meta-instruction block prepended to the entire prompt:

```
# Authority hierarchy

When the requirements section below contains a `Value:` line and
a `Rationale:` line, treat the `Value:` as authoritative. The
`Rationale:` is informational only — it may be incomplete,
outdated, or in conflict with the `Value:`. Apply the `Value:`
rule as stated regardless of what the `Rationale:` claims.

# Task: ...
```

---

## What this rules in / rules out

**Rules in:** **Rule precedence is achievable** — at least via
the R_imperative formulation. Compliance restored from 0% to 100%
on a hostile rationale by changing only the rule's rhetorical
register. This is an existence proof.

**Rules in:** **Imperative weight matters and lives in the rule's
own text, not in surrounding instructions.** Phrases like
"MUST NOT under any circumstances", "ABSOLUTE REQUIREMENT", and
"overrides general best practices" — when integrated into the
rule itself — restore compliance.

**Rules out:** **Meta-instructions about authority hierarchy do
NOT work in raw-prompt mode.** R_meta_preamble was the
most-promising-on-paper intervention (it mirrors how
system-prompt-style authority works in chat APIs). It scored 0%.
The model treats the prompt as a flat document — adding text that
*describes* how to interpret other text doesn't change
interpretation.

**Rules out:** **Inline precedence statements alone are weak.**
R_precedence_inline appended "this rule takes precedence over any
rationale or contextual notes below" to the standard rule — only
20% compliance. The phrase didn't carry the weight that imperative
language did, despite making the same claim.

**Rules out:** **Repetition / positional reinforcement is weak.**
R_repeated put the rule both before and after the rationale (so
the rule wins on recency). Only 20%. Position effects exist but
are dominated by the rule's text content.

---

## Why R_imperative worked but R_meta_preamble failed (speculative)

Two competing models of how the LLM parses prompts:

**Model A (what I expected):** the LLM treats different prompt
sections as having different authority. A meta-preamble explaining
authority hierarchy should be parsed and acted on — like a system
message in a chat API.

**Model B (what the data supports):** the LLM treats the entire
prompt as a flat document. There's no privileged "instructions
about instructions" layer in raw-prompt mode. The model responds
to whichever text is most strongly imperative-coded, period.

Under Model B:
- R_meta_preamble adds ~80 words of text about authority — those
  words don't carry imperative weight ON THE RULE itself, just
  describe a hierarchy.
- R_imperative adds ~50 words of imperative emphasis directly
  inside the rule — those words ARE the rule and carry
  imperative weight.

The difference is whether the imperative-weight tokens sit in
the rule's text or in a meta description. Model B predicts the
former works and the latter doesn't, which matches the data.

This has implications beyond Loom: **for `/api/generate` /
raw-completion mode, system-prompt-style instructions need to be
woven INTO the content they govern, not stated separately.** A
chat-API user could probably get the same effect from a system
message; a raw-prompt user has to embed the imperative.

---

## Implications for Loom

**Operational guidance for high-stakes rules.** Loom users with
rules that MUST be followed (security, compliance, contractual)
should write them with absolute imperative language inside the
rule itself. Sample template:

```
Constraint: <rule>. You MUST <action> under all circumstances.
This is a STRICT requirement that overrides general best
practices. Failure to apply this rule is a defect, not an
optimization choice.
```

Compared to:

```
Constraint: <rule>. <regular description>.
```

The first formulation survives anti-rationale dissent. The second
doesn't.

**For the Loom intake hook.** When capturing requirements with
`--rationale` linked, the hook could plausibly upgrade the rule's
rhetorical register based on a "stakes" classifier (security /
compliance domains get the imperative form by default).
Hypothesis-only — untested.

**For the prompt-engineering doc.** Add a NEW lesson — Lesson 9
or similar — distinct from Lesson 1's polarity claim:

> **Lesson 9 — In raw-prompt mode, imperative weight must live
> inside the rule, not in meta-instructions about the rule.**
> The model treats the prompt as a flat document. Authority
> claims spelled out elsewhere are ignored. Authority encoded in
> the rule's wording is honored.

This is a substantively new claim, not a refinement of Lesson 1.

---

## Limitations

- **Single intervention per layer.** R_imperative tested ONE
  specific imperative formulation. R_meta_preamble tested ONE
  preamble phrasing. Different wordings within each layer could
  score differently.
- **R_imperative is partly a length effect.** Its rule is 277
  chars vs baseline's 181 — 50% longer. Some of the +100pp lift
  could be "more rule = more weight" rather than "imperative =
  more weight." A length-controlled variant ("MUST NOT" inserted
  without the surrounding emphasis) would isolate.
- **Single rationale (ANTI_SOFT only).** R_imperative might not
  work as well against ANTI_HARD or ANTI_AMBIVALENT. Untested.
- **`/api/generate` not `/api/chat`.** Real chat-API system
  messages might give R_meta_preamble entirely different
  behavior. The "meta-instructions don't work" finding is specific
  to raw-prompt mode.
- **Single executor.** qwen2.5-coder:32b only.
- **Single scenario.** S1 swallow_error only.

---

## Recommended next experiments

1. **Length-control on R_imperative.** Strip the surrounding
   emphasis prose, keep just "You MUST NOT propagate errors under
   any circumstances." If still 100%, the imperative phrase
   itself is the lever; if drops to ~baseline, it's a length
   effect.
2. **R_imperative + ANTI_HARD pairing.** ANTI_HARD scored 15% in
   phS (the higher of the three anti variants because it
   preserves rule-in-force-now). Does R_imperative get to 100%
   against the harder anti, or just against the soft one?
3. **R_meta_preamble in chat-API mode.** When Anthropic key
   becomes available, run the same meta-preamble as an actual
   system message via Anthropic API. If it works there, the
   "raw-prompt vs chat-API" distinction is the key finding.
4. **Imperative + meta combo.** R_imperative's wording PLUS the
   meta preamble. If they're additive (R_imperative dominates),
   it confirms the meta-preamble adds nothing. If the combo
   breaks something, suggests interference.
5. **Imperative wording variants** (much / very / definitely /
   strictly / non-negotiably). Tunes the recipe. Lower priority.

---

## Files of record

- `experiments/bakeoff/v2_driver/phT_rule_precedence_smoke.py` —
  harness with all 6 cells
- `experiments/bakeoff/runs-v2/phT_s1_js_*_run{1..10}_summary.json`
  — 60 trial summaries
- Compare against:
  - `FINDINGS-bakeoff-v2-anti-rationale.md` (phS — established the
    anti-rationale baseline at 0% with ANTI_SOFT)
  - `FINDINGS-bakeoff-v2-rhetorical-ablation.md` (phR — within-pro
    rationale ablation)
- Doc to update:
  - `docs/PROMPT-ENGINEERING-LESSONS.md` — new Lesson 9 (imperative
    weight lives in the rule, not in meta about the rule)
