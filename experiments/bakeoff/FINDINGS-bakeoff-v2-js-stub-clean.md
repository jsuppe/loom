# Bakeoff V2 — JS clean-stub falsification (phQ3)

**Date:** 2026-05-02
**Question:** Was phQ2's striking JS lift (off=0→60%, on-rule=20→100%)
caused by the JSDoc-style contract assertions in the stub leaking
the rule into the prompt? Specifically: does the lift survive when
the stub is stripped to the kind of output a real `tsserver` LSP
would actually return — file:line references and code snippets
only, no `@returns`, no "does NOT throw", no production-incident
prose?
**Approach:** Author a structural-facts-only `StubJsIndexerClean`
that contains the same call-site evidence (peek-references-style
snippets at 3 reference locations + bare class signatures) but
strips every contract assertion. Re-run the same 4 cells × N=10
on `qwen2.5-coder:32b`.
**N:** 40 trials. 0 retries fired (keep_alive fix held). 0 compile
failures. 0 no-code-extracted. 10.4 min wall.

---

## TL;DR

> **The phQ2 lift was substantially the JSDoc rule leak.** Strip
> the contract assertions and:
> - **off cell collapses 60% → 0%** (confirms the leak: clean
>   structural context alone does NOT encode the rule)
> - **on-rule cell collapses 100% → 0%** (worse than the no-stub
>   baseline of 20% — clean structural context without explanation
>   is an active distractor, not just a non-helper)
> - **rationale cells saturate (100%)** and **placebo cells nearly
>   saturate (90%)** — when *any* explanation (real or filler)
>   accompanies the rule, the structural facts integrate cleanly
>
> Three takeaways:
> 1. A real `tsserver`-based `JsIndexer` would behave like phQ3,
>    not phQ2. The "indexer alone fixes JS at on-rule" framing is
>    wrong.
> 2. The placebo at 90% is itself a Loom-relevant finding: on this
>    scenario, the *presence* of explanation matters more than
>    the *content* — explanation-shaped text functions as
>    rule-reinforcement scaffolding for the structural facts.
> 3. The +40pp delta from phQ baseline (qwen3.5, no stub, +rat=60%)
>    to phQ3 (32b + clean stub, +rat=100%) is a confound between
>    *model tier* and *stub*. Need phQ4 (32b + no stub) to isolate
>    them.

---

## Setup

`experiments/bakeoff/v2_driver/phQ3_crosssession_js_stub_clean_smoke.py`,
4-cell × N=10 sweep against the same `crosssession_js/s1_swallow_error`
scenario as phQ / phQ2.

The clean stub (`S1_JS_STUB_CLEAN_CONTEXT`, 955 chars) keeps:

- File:line for each of 3 references
- 2-4 surrounding lines of code at each reference site (peek-refs
  style — exactly what an editor would render)
- Bare class signatures: `class BackoffError extends Error`,
  `class BackoffLedger { recordExhaustion(url) }`

It strips, relative to phQ2's stub (3097 chars):

- The `IMPORTANT: this call site does NOT have a try/catch ...
  contract violation that production hit on 2024-09-12` prose
- The `Contract for fetchWithRetry` JSDoc-style block:
  - `* @returns {Promise<string | null>}`
  - `* Returns null iff all attempts failed`
  - `* Does NOT throw. Specifically: catches the Error from
    doFetch internally`
- All editorial framing of the wrapper relationship

The model still sees the call-site code:

```javascript
//   src/backoff_loop.js:34
//       const result = await fetchWithRetry(url, this.attempts);
//       if (result === null) {
//           this._ledger.recordExhaustion(url);
//           throw new BackoffError("retry budget exhausted");
//       }
```

…and has to *infer* from the code that callers expect null-on-failure
rather than being told it.

Same `qwen2.5-coder:32b` model as phQ2 for parity. Harness uses the
2026-05-02 `keep_alive=30m` + retry patch; 0 retries fired across
the sweep, confirming the keep_alive fix held the model warm.

---

## Empirical record

| cell | phQ baseline (qwen3.5, no stub) | phQ2 (32b + leaky stub) | **phQ3 (32b + clean stub)** | phQ3 vs phQ2 |
|---|---|---|---|---|
| off | 0% | 60% | **0% (0/20)** | **-60pp** |
| on-rule | 20% | 100% | **0% (0/20)** | **-100pp** |
| on-rule+placebo | 40% | 100% | 90% (18/20) | -10pp |
| on-rule+rat | 60% | 100% | 100% (20/20) | 0pp |

Other measurements:
- 0 compile failures across all 40 trials
- 0 cited-rationale matches across all 40 trials (qwen2.5-coder:32b
  doesn't reproduce rationale phrases on JS — same as phQ2)
- Wall: 10.4 min for 40 trials, ~16s/trial average

A failing on-rule trial:

```
FAIL: returns_null_on_failures (exception propagated)
FAIL: error_does_not_propagate (exception propagated)
SUMMARY: 0 passed, 2 failed
```

A passing rat trial:

```
PASS: returns_null_on_failures
PASS: error_does_not_propagate
SUMMARY: 2 passed, 0 failed
```

Same scenario, same 32b model, same clean stub — the only thing
that differs is whether a rationale or placebo accompanies the rule.

---

## What this rules in / rules out

**Rules in (negatively):** The phQ2 lift was rule leakage.
Specifically, the JSDoc contract assertions in phQ2's stub
(`@returns {Promise<string | null>}`, `Does NOT throw`) were
functioning as rule restatements in code-comment form. Strip
them, and the on-rule cell collapses to 0%. Off-cell goes from
60% to 0%, confirming the JSDoc contract was the implicit rule
source.

**Rules in (positively):** Structural facts + explanation
saturates. Whether the explanation is the real rationale or
length-matched placebo, the model commits to the rule when the
structural context is also present. This is the same +placebo
anomaly we saw in phQ2 — but now it's the dominant signal, not
overshadowed by a leaky stub.

**Rules out:** "A real `tsserver` indexer alone will replicate
phQ2's lift on JS." The on-rule cell at 0% is conclusive — bare
LSP-style structural facts are not sufficient to lift compliance
when the rule must compete with task-prompt framing ("this looks
like a bug — fix it"). The model interprets the structural facts
through whichever framing is loudest in the prompt; without
rationale-shape scaffolding, the task framing wins.

**Worse than rule-out:** Clean structural context with rule but
no rationale produced **0% compliance**, *below* the phQ baseline
of 20% (qwen3.5 with no stub at all). Clean LSP context can be
an *active distractor* on this scenario — adding code snippets
that look bug-like (callers checking for null after a function
call that "swallows errors") may reinforce the task framing's
"this is a bug, fix it" interpretation rather than the rule's
"don't propagate."

---

## Implications for step 4 (real JsIndexer)

**Pre-phQ3 plan:** if Path A (clean stub) confirmed the lift,
proceed to Path B (real `tsserver`-based `JsIndexer`).

**Post-phQ3 plan:** clean stub did NOT confirm the on-rule lift,
but DID maintain saturation in rationale-augmented cells. So a
real `JsIndexer` is justified only for **rationale-augmented
workflows**, not as a standalone fix. That's a different product
shape than the phQ2 framing suggested.

Before committing to ~half a day of subprocess + LSP plumbing,
one cheap experiment is missing:

> **phQ4: qwen2.5-coder:32b WITH the rule but NO stub at all.**
> 4 cells × N=10. Isolates the model-tier effect from the
> stub-presence effect. Currently the only available comparison
> is phQ baseline (qwen3.5, no stub: rat=60%) → phQ3 (32b +
> clean stub: rat=100%). The +40pp could be the bigger model,
> the stub, or both.

If phQ4 lands at, say, 80-100% on +rat, the clean stub adds
little and a real `JsIndexer` would be a marginal improvement
at best. If phQ4 stays near 60% on +rat, the structural context
is the lift mechanism even when explanation is present, and a
real indexer would be load-bearing for rationale-augmented JS.

This is the cheapest experiment that disambiguates the next
engineering decision. ~10 min wall.

---

## Limitations

- **Single scenario.** S1 swallow_error is one specific
  contrarian shape. S2 (rename) and S3 (other contrarian patterns
  if authored) might respond differently.
- **N=10.** Tighter than phQ2 (N=5 with crashes), but the 0/20
  cells in off and on-rule are extreme — at N=20 they could
  be 1/40 or 2/40 (still effectively zero but with non-zero CI).
- **Model-tier confound.** As noted above — the +rat 60→100%
  change is between two different things changed at once. phQ4
  is the missing baseline.
- **Hand-authored "structural-only" stub is a judgment call.**
  Real `tsserver` output might include hover information that
  reads more like phQ2's contract assertions than phQ3's bare
  references. The honest framing is: phQ3 is the *cleanest
  possible* structural stub; real LSP output likely sits between
  phQ2 and phQ3.
- **Placebo at 90% is itself unexplained.** Why does length-
  matched filler text get the model to commit to the rule when
  the rule alone fails? Worth its own falsification — different
  placebo content (e.g. anti-rule prose) would test whether the
  effect is "explanation present" or "explanation supports rule."

---

## Recommended next experiments (priority order)

1. **phQ4: 32b + NO stub** (4 cells × N=10) to isolate model-tier
   from stub effect. ~10 min wall. Cheapest disambiguating
   experiment.
2. **Decide on real `JsIndexer`** based on phQ4 outcome.
3. **Anti-rule placebo variant.** Replace the placebo with text
   that subtly argues *against* the rule, see if compliance
   collapses at 90%/100%. Tests whether the placebo lift is
   "explanation present" or "explanation supports rule."
4. **Higher-N rerun on the 0/20 cells.** Off + on-rule both at
   0/20 are effectively zero, but binomial CI tightening might
   still be useful before the JS regime gets reclassified.

---

## Files of record

- `experiments/bakeoff/v2_driver/phQ3_crosssession_js_stub_clean_smoke.py`
  — clean-stub harness
- `experiments/bakeoff/runs-v2/phQ3_s1_js_*_run{1..10}_summary.json`
  — 40 trial summaries
- `FINDINGS-bakeoff-v2-stub-indexer-multilang.md` — phQ2 (M10.3)
  precedent
- `FINDINGS-bakeoff-v2-cross-language-map.md` — phQ baseline
  (qwen3.5, no stub)
