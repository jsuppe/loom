# Prompt-Engineering Lessons from Loom Experiments

**Last updated:** 2026-05-02
**Provenance:** Synthesis of empirical findings from M8 (Python-first
smoke + cross-language map), M10 (semantic indexer integration), and
M11 (rationale linkage + intake hook). All numbers below are linked
to a specific experiment.

This document is the umbrella synthesis of what the Loom bake-off
work has actually taught us about prompt engineering. The work
shipped as "build a requirements-traceability tool," but the
load-bearing findings are general lessons about how to construct
prompts that get LLMs to follow rules — especially rules that
contradict their training priors.

---

## The meta-takeaway

> **Delivery is the mechanism.** Storage doesn't lift compliance,
> prompt assembly does.

The unbroken arc from M8.1 (where stored-but-undelivered specs
produced 0% compliance and stored-AND-delivered specs produced
95%) to M11.5 (an intake hook that captures rationale at the
source so it can be delivered later) is one consistent claim:
**the load-bearing engineering is putting the right text in the
right prompt at the right moment.** The model is the engine;
the prompt is the steering. Almost every result we've measured
says: invest in better steering before more horsepower.

---

## Lesson 1 — Rationale is load-bearing, polarity-sensitive, and the framing-defuser is its core

**Source:** M8.1 D-smoke
([`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md));
M10.3 phQ3-phQ7 series; phR rhetorical ablation
([`FINDINGS-bakeoff-v2-rhetorical-ablation.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-rhetorical-ablation.md));
phS anti-rationale ablation
([`FINDINGS-bakeoff-v2-anti-rationale.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-anti-rationale.md)).

The first signal came from M8.1: same data in the store, but D2
(stored, undelivered) scored **0% compliance** and D3 (stored AND
injected via `task_build_prompt`) scored **95%** — a +95pp swing
on whether the rationale text actually made it into the prompt.

Every M10.3 phQ experiment after reproduced it at finer grain on
contrarian-rule scenarios:

| context shape | compliance |
|---|---|
| Bare rule, no rationale | **0%** |
| Rule + rationale (real or placebo) | **90-100%** |

This isn't "rationale helps a bit." Without it, the rule is
effectively invisible to the model on contrarian specs. With it,
compliance saturates.

**Sharpened by phR (rhetorical ablation, M11+).** Decomposing the
RATIONALE constant into 6 atomic features and ablating each:

| feature stripped | compliance | drop |
|---|---|---|
| (full rationale) | 100% | baseline |
| Mechanism explanation | 100% | 0pp |
| Cost quantification | 100% | 0pp |
| Codebase locator | 95% | −5pp |
| Incident date | 90% | −10pp |
| Dependence assertion | 90% | −10pp |
| **The reframe ("actually working as intended")** | **80%** | **−20pp** |

The reframe — the sentence that **anticipates and defuses the task
framing's "fix the bug" pull** — carries 2× the impact of any
other feature. Mechanism, cost, and locator can be stripped with
no measurable loss.

**The prompt-engineering takeaway:** stop treating rationale as
documentation overhead. It's the prompt's most leveraged token.
And the most leveraged sentence within rationale is the one that
**anticipates how someone would misread the rule and corrects them
in advance.**

For Loom users capturing rationale, this becomes a practical
guideline: ask "if a future agent reads this rule, what would
they mistakenly conclude they should do?" Then write the sentence
that defuses that misreading. That sentence is worth more than
five sentences of mechanism, cost, or history.

**Sharpened again by phS (anti-rationale, M11+).** Rationale
operates on a polarity axis, not a presence/absence axis:

| rationale shape | compliance |
|---|---|
| **Pro-rule** (the original V_full) | **100%** |
| Length-matched filler that paraphrases the rule (placebo) | 30% |
| No rationale at all (rule alone) | 0-20% |
| **Anti-rule** (direct contradiction) | **15%** |
| **Equivocal** (rule "may be wrong", "treat as provisional") | **0%** |

Two new findings from this:

1. **The model treats rationale as more authoritative than the
   rule when they conflict.** Anti-rule rationale doesn't just
   match the no-rationale baseline — it drops *below* placebo.
   The rule says "do X," the rationale says "we're moving away
   from X," and the model moves away from X.

2. **Equivocation is worse than direct contradiction.** A
   rationale that says "rule X is the legacy convention; we're
   migrating to Y" preserves rule-in-force-now and gets some
   compliance (15%). A rationale that says "treat the rule as
   provisional" or "consider whether it still applies" dissolves
   the rule's authority entirely (0%).

**Practical safety warning for Loom users.** If you write rationale
that questions or equivocates about the rule, the model will
likely override the rule. **Silence is better than ambivalence.**
If you don't have a clear pro-rule reason yet, leave rationale
empty (status will fall to `rationale_needed`, which is debt but
not active sabotage) rather than write a "this might be wrong" hedge.

---

## Lesson 2 — Bigger model ≠ better, especially on contrarian rules

**Source:** M11.5 P0 / phQ4
([`FINDINGS-bakeoff-v2-js-no-stub-32b.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-no-stub-32b.md)).

Counter-intuitive result: `qwen2.5-coder:32b` LOST to `qwen3.5:latest`
by **20-30pp** on bare-rule cells. Code-specialist priors actively
fight specs that ask the model to do something its training data
calls "wrong" — swallow errors, accept null returns, skip
validation.

The bigger and more code-specialized the model, the stronger the
priors that fight you. A small general-purpose model with weaker
priors is more deferential to a stated rule.

| executor | bare-rule compliance | rationale-augmented |
|---|---|---|
| qwen3.5:latest | 20% | 60% |
| qwen2.5-coder:32b | **0%** | **80%** |

The crossover: the bigger model wins on the rationale path (better
integration of context) but loses on the bare-rule path
(stronger conflicting priors).

**The prompt-engineering takeaway:** **spec-shape-aware model
selection.**
- Conventional spec → code-specialist.
- Contrarian spec → general-purpose with weaker priors.
- Either way → ALSO supply rationale; it bridges most of the gap.

---

## Lesson 3 — Explanation-shape > explanation content

**Source:** M10.3 phQ3 placebo cell
([`FINDINGS-bakeoff-v2-js-stub-clean.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md)).

The phQ3 placebo cell — rule + length-matched filler text that
just paraphrased the rule, no real reasoning — hit **90%
compliance**. The placebo wasn't even good prose. And it still
worked.

| cell | compliance |
|---|---|
| off (no rule) | 0% |
| on-rule (rule alone) | 0% |
| on-rule + placebo (filler text) | **90%** |
| on-rule + rationale (real reason) | 100% |

Whatever explanation-shape text accompanies the rule, the model
commits more. The PRESENCE of explanation matters more than its
quality. A one-line "we hit a production incident" probably
outperforms a perfectly-argued essay because both are
explanation-shaped, but the essay buries the rule under more
text.

**The prompt-engineering takeaway:** stop crafting perfect
rationale. Capture *anything* explanation-shaped at decision time
and persist it. Loom's `loom extract --rationale "..."` should
err toward "save it now, refine later" rather than "wait until
I have time to write this well."

**Cautionary note:** the placebo-vs-rationale gap was small (90%
vs 100%) on this scenario. Don't take this as license to skip
real rationale capture — there are scenarios where the content
will matter (cross-session memory, future audits). But for
*compliance in the next agent action*, the shape dominates.

---

## Lesson 4 — Deterministic guardrails > prompt iteration

**Source:** M11.5 P0 classifier pilot
([`FINDINGS-intake-classifier-pilot.md`](../experiments/pilot/FINDINGS-intake-classifier-pilot.md)).

The intake classifier hit 95.2% precision on 40 hand-labeled
chat utterances, with one false positive: "Make this faster if
possible." — a hedged optimization request, not a real rule.

The fix was *not* "iterate the prompt to teach the classifier
about hedges." It was a downstream regex guardrail (`if
possible`, `try to`, `would be nice`, `maybe`, `perhaps`,
`consider`, `ideally`, `someday`, `nice to have` → force the
propose branch instead of auto-link).

That's one of five guardrails on the intake hook. Together
they're more reliable than any single prompt-engineering pass:

| guardrail | what it catches |
|---|---|
| Precision threshold (≥90%) | The classifier's own miss rate |
| Domain whitelist | Off-enum domain inventions (Lesson 5) |
| Softener detection | Hedge-language false positives |
| Daily budget cap | Runaway capture from a noisy session |
| Reversibility surface | The cases the other guardrails miss |

**The prompt-engineering takeaway:** don't make the LLM perfect.
Make a layered system where deterministic code catches the LLM's
predictable mistakes. The model produces a candidate; the system
decides whether to trust it.

---

## Lesson 5 — Output schema constrains but doesn't enforce

**Source:** M11.5 P0 classifier pilot, domain-accuracy analysis.

The classifier prompt explicitly enumerated: `domain MUST be one
of "behavior" | "ui" | "data" | "architecture" | "terminology"`.
The model invented `security` as a domain **2 of 20 times** on
true positives. The enum constraint was advisory, not enforced.

The fix wasn't a stricter prompt. It was downstream tolerance:
out-of-enum domains route to the propose branch (where the user
picks/corrects), instead of crashing or auto-capturing under a
fabricated domain.

**The prompt-engineering takeaway:** when you constrain output
via enum, *also* build downstream tolerance for off-enum values.
The prompt is a hint, not a contract. Treat any structured-output
field as "best-effort with an unknown bucket."

---

## Lesson 6 — Test references are uniquely high-signal context

**Source:** M11.5 phQ7
([`FINDINGS-bakeoff-v2-js-test-refs.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-test-refs.md)).

phQ7's +40pp lift on the placebo cell came from **one line of
`setup_workspace` change**: copy the test file alongside source so
the LSP indexes it. No JsIndexer code change required.

| cell | phQ6 (no test in workspace) | phQ7 (test in workspace) | delta |
|---|---|---|---|
| placebo | 30% | **70%** | **+40pp** |
| rationale | 100% | 100% | 0 |

The mechanism: the test's `console.log("PASS: returns_null_on_failures")`
is the closest thing to a contract in code form. Even better than
a hand-authored `assert(result === null)` because of the explicit
verbal PASS labels.

**The prompt-engineering takeaway:** when designing a context
bundle for a code-gen prompt, **test files are first-class
context**, not background noise. Many editor LSPs hide tests by
default; for prompt building, surface them. The PASS/FAIL labels
in test code function as a contract restated in executable form.

---

## Lesson 7 — Indexer/context amplifies; it doesn't manufacture

**Source:** M10.3 phQ3, phQ4, phQ5 across the JS scenario series.

A consistent finding across the entire stub→clean-stub→real-LSP
arc:

| condition | bare-rule cell | rationale cell |
|---|---|---|
| Indexer alone, no rule | 0% | n/a |
| Rule alone, no indexer | 0% | 60-100% |
| Rule + indexer, no rationale | 0% | n/a |
| Rule + indexer + rationale | n/a | 100% (saturates) |

The indexer's job is to *amplify* explanation, not substitute for
it. "More context" doesn't make a model follow rules; it makes a
model follow rules MORE STRONGLY when there's already a reason
it should.

**The prompt-engineering takeaway:** treat extra context as
**conditional reinforcement** for explicit instructions, not a
replacement. If your prompt's instruction-shape is weak, more
context won't save it. Strengthen the instruction first, then
add context to amplify.

This generalizes: stuffing the prompt with more reference
material rarely helps when the actual rule is buried or
ambiguous. The Loom indexer work pivoted from "fix JS compliance"
to "amplify rationale-augmented prompts" specifically because the
data ruled out the substitution thesis.

---

## Lesson 8 — Capture rationale at the source

**Source:** M11.5 (whole milestone) + M0.5 dogfooding observations.

Every other lesson on this list says: rationale is load-bearing,
but users skip capturing it. Running `loom extract --rationale "..."`
manually after every chat message is a friction tax that
empirically nobody pays.

So the M11.5 intake hook exists precisely to shift that
discipline from human (manual capture) to harness (automatic
classify + persist). The classifier's 95.2% precision on chat
utterances + the linkage chain mechanism (`rationale_links` to
prior decisions) means most decisions can be captured without
the user typing anything.

**The prompt-engineering insight is meta:** the highest-leverage
prompt isn't the one *being engineered*. It's the one that
**captures human reasoning before it's lost**. Once captured,
delivery (Lesson 0) is solved by existing infrastructure. The
bottleneck is always at the input.

---

## Lesson 9 — In raw-prompt mode, imperative weight must live inside the rule, not in meta-instructions about the rule

**Source:** phT rule-precedence ablation
([`FINDINGS-bakeoff-v2-rule-precedence.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-rule-precedence.md)).

**Setup:** phS established that anti-rationale beats rule
(compliance drops to 0% on hostile rationale). phT asked: can a
rule be written so it pre-empts the rationale?

Five intervention layers tested, all paired with the same
ANTI_SOFT rationale:

| layer | intervention | compliance |
|---|---|---|
| (control) | standard rule | 0% |
| A: structure | rule restated AFTER rationale | 20% |
| B: text | inline "this rule takes precedence" | 20% |
| **B: text** | **absolute imperative wording** ("MUST NOT under any circumstances", "STRICT requirement that overrides general best practices") | **100%** |
| C: meta | top-of-prompt "Value: is authoritative, Rationale: is informational only" preamble | **0%** |

The two surprises:

1. **Absolute imperative wording inside the rule restored
   compliance to 100%.** Same semantic content as the standard
   rule, just rewritten with maximum imperative emphasis. From
   0% to 100% with no other changes.
2. **Meta-instructions about authority hierarchy DIDN'T WORK.**
   The preamble that explained "the Value: line is authoritative;
   ignore the Rationale: when they conflict" was completely
   ignored. 0% compliance — same as no intervention.

**The mechanism:** the model treats raw prompts as flat documents.
There's no privileged "instructions about instructions" layer.
Imperative-coded tokens carry weight when they sit in the rule's
own text. Imperative-coded tokens that sit in a *meta*
description of the rule don't carry weight.

This has direct implications beyond Loom: **for raw `/api/generate`
prompts, system-prompt-style authority needs to be woven INTO the
content it governs, not stated separately.** Chat-API users get
this for free via system messages; raw-prompt users have to
embed.

**Practical recipe.** When a rule MUST be followed (security,
compliance, contractual), write it with imperative weight in the
text:

> ❌ Standard: "Constraint: catch and swallow errors. Do NOT
>   propagate."
>
> ✅ Imperative: "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: catch
>   and swallow errors thrown by doFetch on every attempt. You
>   MUST NOT propagate errors under any circumstances. This is a
>   STRICT requirement that overrides general best practices."

The first survives anti-rationale dissent at 100%; the second
collapses to 0%.

**Caveat:** this is specific to raw-prompt mode (Ollama
`/api/generate` and similar). Chat-API system messages probably
work differently — likely R_meta_preamble would be effective
there because the API treats system messages as authoritative.
Untested at the time of writing.

---

## How these connect

If you trace the dependencies:

```
Lesson 1 (rationale is load-bearing)
   │
   ├─ Lesson 3 (explanation-shape > content)
   │     informs how strict to be at capture time
   │
   ├─ Lesson 7 (context amplifies)
   │     informs what infrastructure to build (indexers, hooks)
   │
   └─ Lesson 8 (capture at the source)
         informs the intake-hook architecture

Lesson 2 (bigger ≠ better) is independent
   informs model selection at the orchestration layer

Lesson 4 (guardrails) and Lesson 5 (enum tolerance) are
   meta-engineering disciplines that apply to every LLM
   integration, not just Loom

Lesson 6 (test refs) is a specific corollary of Lesson 7
   that happened to dominate the JS results
```

The full system Loom builds is essentially: **make Lesson 8
automatic, run Lesson 1 reliably as a result, configure Lesson
2 per project, and use Lessons 4-7 as guardrails so the whole
thing doesn't drift into noise.**

---

## What's NOT on this list (worth flagging)

Things you might expect from a prompt-engineering doc that the
Loom experiments didn't decisively validate:

- **Few-shot examples in prompts.** We use 0-shot for the
  classifier and 0-shot for the executor. Few-shot might help —
  untested. Loom's M0 work showed qwen3.5 hits parity with Opus
  on atomic tasks at zero-shot, so we never needed it.

- **Chain-of-thought reasoning prompts.** The classifier is
  output-only ("Output JSON only"). The executor produces code.
  Neither asks the model to reason out loud. We haven't measured
  whether CoT would help, but the latency cost (tokens) is real
  and Loom's value pitch is "fast hooks." We bias toward terse.

- **Temperature tuning.** All experiments use `temperature=0`
  for determinism. Higher temperatures might surface different
  failure modes — untested.

- **Prompt length limits.** All Loom prompts are ≤16k chars.
  Behavior at 100k+ char prompts is unverified.

- **Adversarial prompts.** Loom assumes a cooperative user.
  Adversarial users could probably trip the intake classifier
  to capture spam reqs; the conflict-detection backstop is the
  only defense and it's LLM-verified (not adversarial-resistant).

These are the obvious gaps if you wanted to extend this list. But
the eight lessons above are the ones the Loom data actually
*validated*.

---

## Where to dig deeper

- M8.1 Python-first smoke (D2 vs D3): the original "delivery is
  the mechanism" finding —
  [`FINDINGS-bakeoff-v2-pythonfirst-smoke.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-pythonfirst-smoke.md)
- M8.4 Cross-language map: the regime classification that drove
  M10 —
  [`FINDINGS-bakeoff-v2-cross-language-map.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-cross-language-map.md)
- M10.3 phQ3-phQ7: the JS series that decomposed every prompt
  axis (clean stub vs leaky stub vs real LSP vs LSP+test refs):
    - phQ3: [`FINDINGS-bakeoff-v2-js-stub-clean.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-stub-clean.md)
    - phQ4: [`FINDINGS-bakeoff-v2-js-no-stub-32b.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-no-stub-32b.md)
    - phQ5: [`FINDINGS-bakeoff-v2-js-real-lsp.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp.md)
    - phQ6: [`FINDINGS-bakeoff-v2-js-real-lsp-v2.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-real-lsp-v2.md)
    - phQ7: [`FINDINGS-bakeoff-v2-js-test-refs.md`](../experiments/bakeoff/FINDINGS-bakeoff-v2-js-test-refs.md)
- M11.5 P0 classifier pilot —
  [`FINDINGS-intake-classifier-pilot.md`](../experiments/pilot/FINDINGS-intake-classifier-pilot.md)
- M11 design doc (rationale linkage + intake hook) —
  [`DESIGN-rationale-linkage.md`](DESIGN-rationale-linkage.md)
