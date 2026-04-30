# Bakeoff V2 — Python vs C++ comparison (cross-session S1)

**Date:** 2026-04-29
**Question:** Does Loom's "structured rule injection saturates compliance"
finding from the Python smoke series hold when qwen is operating in a
less-friendly language (C++)?
**Approach:** Direct port of Python S1 (swallow_oserror) to C++
(swallow_runtime_error). Same 4-cell harness, same N=5, same qwen3.5
model. C++ harness bypasses loom_exec (no C++ runner exists) and calls
Ollama directly with prompts that mirror task_build_prompt's format.
**N:** 20 trials. 3 hung at 32k+ output tokens (treated as failures).
**Cost:** $0 (local qwen only).

---

## TL;DR

> **Same model. Same scenario logic. Different language. Loom's
> mechanism collapses.**
>
> Python S1 (cross-session smoke): rule alone produces 100%
> compliance — `on-rule = on-rule+placebo = on-rule+rat = 100%`.
> C++ S1 (this experiment): rule alone produces **0%** compliance.
> qwen disregards the contrarian rule and compromises with the
> task ("catch on intermediate attempts, throw on the last") in
> every trial that wasn't artifactual.
>
> The Loom value claim — "structured rule injection works for small
> models" — is **language-fitness-dependent**. When qwen is fluent
> in the target language, the rule serves as authoritative context.
> When qwen is shaky in the language (C++ requires careful syntax,
> manual memory model, exception lifecycle reasoning), the rule
> becomes one signal among many that qwen weights against task
> instinct and general code-fixing priors.
>
> This reframes the whole bakeoff smoke series. The Python results
> are real, but the generalization claim — "Loom helps qwen comply
> with stored decisions" — should be qualified to "...when the
> language is one qwen handles fluently."

---

## Side-by-side

| cell | Python (phK S1) | C++ (phL S1) | delta |
|---|---|---|---|
| off | 8/10 (80%) | 0/10 (0%) | -80pp |
| on-rule | 10/10 (100%) | 0/10 (0%, 1 trial hung) | -100pp |
| on-rule+placebo | 10/10 (100%) | 10/10 (100%, **artifact** — qwen copies original) | 0pp |
| on-rule+rat | 10/10 (100%) | 4/10 (40%, 2 trials hung) | -60pp |

The placebo cell tying at 100% is *not* a real Loom-effect
observation — see below.

## Per-trial behavior (C++)

### off cell (n=5)

All 5 failed (4 with compiling code that propagates, 1 with non-
compiling code that uses default-constructed `std::runtime_error`).
qwen attempted to "fix the bug" exactly as the task asked, producing
some variation of:

```cpp
catch (const std::runtime_error& e) {
    last_error = e;
}
// ...
if (failed) throw last_error;
```

This is healthy contrarian behavior — qwen is ignoring the existing
swallow and trying to propagate. Output tokens 1.2k-9.9k.

### on-rule cell (n=5: 4 produced summaries, 1 hung)

All 4 summary-producing trials failed at 0/2. qwen produced a
"compromise" — typically:

```cpp
catch (const std::runtime_error& e) {
    if (attempt == attempts - 1) {
        throw e;            // propagate on last
    }
    continue;               // swallow on intermediate
}
```

This violates the rule (`do NOT propagate`) but partially honors the
task ("propagate so callers see"). qwen is weighting task instinct
over the rule. The 5th trial hung at 32k tokens — qwen wandered into
prose without producing a clean fenced code block.

### on-rule+placebo cell (n=5)

All 5 hit 2/2. **But** the produced files are near-verbatim copies
of the pre-state retry.hpp. qwen left the original code alone in
every trial. The placebo's content (verbose restatement of the rule
with no new info) appears to have given qwen so little material to
act on that it defaulted to "copy the file."

This is **not Loom working correctly** — it's qwen giving up on the
task. We measure pass=2/2 because the original code already
satisfies the constraint, not because the rule changed qwen's
behavior. The metric is fooled by inaction.

### on-rule+rat cell (n=5: 3 produced summaries, 2 hung)

| run | result | behavior |
|---|---|---|
| 1 | hung | 32k tokens, no fenced code block |
| 2 | 0/2 | qwen propagated despite rule + rationale |
| 3 | 2/2 | qwen complied with rule |
| 4 | hung | 32k tokens |
| 5 | 2/2 | qwen complied + cited "wrapper", "BackoffError", "incident" in code comments |

Counting hung as failures: 2/5 trials = 40% pass. Among the 3
trials that ran cleanly, 2/3 = 67% — but that's noisy at this N.

The rationale doesn't reliably tip qwen toward compliance in C++.
It also seems to amplify hang risk — 2/5 trials produced 32k+
tokens of prose/code, suggesting qwen got lost in elaboration when
given more material to weigh.

## Why does this happen?

Plausible mechanism: qwen's C++ training data has stronger "always
propagate exceptions, errors are bugs, swallow-and-ignore is bad
code" priors than qwen's Python training data. The contrarian
constraint (must swallow) fights these priors directly. Adding the
rule to the prompt is one signal; qwen's general C++ priors are
another. In Python the rule wins; in C++ the priors do.

A subtler reading: qwen's *capacity* for following structured
context is also language-dependent. In Python qwen is fluent enough
that ~200 tokens of clean code is trivially produced; the prompt's
rule+task contradiction is resolved cleanly. In C++ qwen is
expending capacity on syntax, memory model, exception types, and
template considerations — the rule is just one more thing to weigh.
Output token volumes confirm this: Python S1 averaged 220 tokens
per trial; C++ S1 averaged 5,000-8,000.

## What this means for the broader Loom claims

Three smoke experiments in Python all showed structured rule
injection working:

1. D-smoke R1 (pyschema add field): D2 vs D3 = 0% → 95%
2. D-smoke R2 (pubsub rename): D1 = D3 = 100%
3. phK cross-session: rule = rule+rationale = 100%

**One smoke experiment in C++ shows the mechanism collapsing:**

4. **phL C++ S1: rule = 0% (despite Python S1 at 100%)**

The honest interpretation:
- ✓ Loom's mechanism (structured rule injection via
  `task_build_prompt`) works **for languages qwen handles fluently**.
- ✗ The mechanism does NOT generalize across languages with the
  same model. Saying "Loom helps small models" overgeneralizes.
- ✓ Python is a uniquely friendly substrate for qwen3.5 + Loom.
  The smoke series happened to land in qwen's strongest language.

For positioning Loom honestly: it's a tool that **amplifies what
the executor model can already mostly do**. It moves a mostly-
fluent executor from "imperfect compliance under task pressure"
to "consistent compliance." It does not move a marginally-fluent
executor to compliance.

## Limitations and follow-on

- **N=5 per cell.** The "100% placebo" finding is suspicious enough
  that higher N might wash it out (or might confirm that qwen
  systematically gives up on placebo content).
- **One scenario (S1).** S2 and S3 might show different patterns
  in C++. The "qwen ignores rule" finding could be S1-specific.
- **One language pair.** TS, Go, Rust, or another language might
  show patterns between Python and C++. The Loom story would be
  cleaner with a language gradient.
- **One model tier.** qwen2.5-coder:32b might handle C++ better and
  show Python-like compliance. Larger models likely show smaller
  language gaps.
- **3/20 trials hung at 32k tokens.** This is a real failure mode
  for qwen in a language it's shaky on — output runs away. Tighter
  generation limits would change pass rates.

### Recommended next experiments (priority order)

1. **Re-run C++ S1 with `qwen2.5-coder:32b`.** Same scenario, same
   harness, larger code-tuned model. If the Python pattern emerges
   (rule = 100%), the gap is qwen3.5-tier-specific. If it stays
   broken (rule < 50%), it's a deeper language/architecture story.
2. **C++ S2 and S3 ports.** Test whether the "rule collapses in
   C++" pattern is S1-specific or general.
3. **TypeScript / Go S1 ports.** Build a language gradient. TS is
   probably between Python and C++ for qwen; Go is closer to C++
   in tooling but easier in syntax.
4. **Output-token cap experiments.** Constrain qwen to 500 tokens
   max. Does that reduce hangs and force the choice to surface?

---

## Files of record

- `experiments/bakeoff/benchmarks/crosssession_cpp/s1_swallow_runtime_error/`
  — C++ S1 reference + hidden test
- `experiments/bakeoff/v2_driver/phL_crosssession_cpp_smoke.py`
  — 4-cell C++ harness (direct Ollama call, no loom_exec)
- `experiments/bakeoff/runs-v2/phL_s1_cpp_*_run{1..5}_summary.json`
  — 17 trial summaries (3 trials hung; harness now writes a
  no_code_extracted summary in that case after the bug fix in this
  commit)
- `experiments/bakeoff/runs-v2/phL_smoke_progress.log`
  — wall-clock progression
- Pre-existing: `phK_s1_*_run*_summary.json` — Python S1 results
  for direct comparison
