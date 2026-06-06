# M29 Phase A Findings — Style Constraint on C++ S1

**Date:** 2026-06-06
**Verdict:** **H1 REFUTED.** Style constraint alone does not lift the
rat cell on the locked S1 C++ benchmark. **H3 STOP gate passed**
(off cell 0%); the refutation is interpretable.

Captured as **REQ-e349a0ad** in the loom store.

---

## Result table

40 trials, qwen2.5-coder:32b, locked STYLE_CONSTRAINT block (902
chars) prepended above `## Requirements`, no semantic indexer.

| cell | M10.1b (N=5) | M28 clangd (N=10) | **M29 style (N=10)** | 95% CI |
|---|---|---|---|---|
| off | 0% | 0% | **0% (0/10)** | [0%, 28%] |
| on-rule | 0% | 0% | **0% (0/10)** | [0%, 28%] |
| on-rule+placebo | 20% | 20% | **10% (1/10)** | [2%, 40%] |
| on-rule+rat | 0% | 0% | **0% (0/10)** | [0%, 28%] |

Token costs vs M28: input dropped from 1,176 → 795 on rat cell
(**32% less prompt cost**); output unchanged at ~270. M29 is
cheaper-but-still-null.

## Pre-registered verdicts

| hypothesis | prediction | result | verdict |
|---|---|---|---|
| H1 (primary) | rat ≥ 20% (= M28_rat + 20pp) | 0% (CI 0-28%) | **REFUTED** |
| H2 (Phase B) | combined ≥ max(style, semantic) + 10pp | not run | **DROPPED** (Phase B was conditional on M28 H1 confirming; M28 refuted) |
| H3 (STOP gate) | off ≤ 20% | 0% | **passes** — no rule leak |

## The pre-registered prior was vindicated

Before the run, M29's `PRE_REGISTRATION.md` locked this prediction:

> "I expect H1 to **refute** on this specific scenario. Reasoning: the
> contrarian rule's text already pins the C++17 idiom ('Return
> std::nullopt when all attempts fail'), so adding a style block that
> says 'Use std::optional' is redundant with what the rule already
> says."

The data confirmed the prior. The finding is therefore:

> **"Style constraint is refuted for scenarios where the rule itself
> pins the idiom; the broader 'style constraint as a lever' hypothesis
> remains testable on scenarios where the rule is behavioral but does
> NOT pin HOW."**

Logging the prior before the run was important. Without it, the
post-hoc temptation would be either:

* **(a)** "Style block needs different wording" → endless iteration
  on the constraint text.
* **(b)** "Style constraint just doesn't help on C++" → overclaim a
  null result as a universal.

Both would have been wrong. The honest finding is narrower than
either.

## What's still on the table for C++

Two C++ S1 interventions have now been falsified cleanly under
locked pre-regs (M28, M29). The remaining candidates for what might
actually move the rat cell:

1. **M28v2 — LLM-summarized contract prose layer.** M28's FINDINGS.md
   established that M10.2's stub effect was carried by hand-authored
   contract prose, not structural facts. Augmenting ClangdIndexer
   with an LLM (Anthropic Haiku) pass that converts LSP refs into
   contract-style prose tests whether prose IS the carrier. Prediction
   (would be locked in M28v2's pre-reg): rat cell ≥ 30%.

2. **Different scenario shape — multi-file C++ with idiom-underspecified
   rule.** The S1 scenario is single-header AND has an idiom-pinning
   rule. Both constrain what style constraint and what semantic
   context can actually carry. A multi-file scenario with a behavioral
   rule that doesn't pin idiom would let M29 (or even ClangdIndexer)
   test in its proper habitat.

3. **Kythe Phase 2 — project-wide queries.** Original M10 Phase 2.
   Different mechanism from clangd: persistent project graph, stable
   tickets, cross-TU resolution. Substantially more infrastructure
   cost. Justifiable only if (1) and (2) above also fail.

4. **Honest "C++ stays weak" claim.** EFFECTIVENESS.md continues to
   list C++ in the weak zone. That IS a workplace-credible result —
   it tells teams "here's where Loom doesn't move the needle yet"
   instead of overclaiming.

## Methodology pattern: 7/7

The pre-reg pattern (REQ-3896db58) has now caught a useful signal in
seven consecutive arcs:

| arc | what the pattern caught |
|---|---|
| M22a.0 | 2 fatal design flaws pre-launch |
| M22a re-grade | F2 refined (binary grader overclaimed) |
| M22b | structural confounds pre-launch |
| M22e | workload-arm pivot pre-locked |
| M19v2 | wrong-prediction surfaced even with favorable result |
| M28 | clangd indexer falsification under locked H1 |
| **M29** | **refutation + scenario-mismatch flagged via locked predictor's prior** |

## Token efficiency snapshot

| intervention | rat rate | mean in-tok | mean out-tok | tokens/pass | note |
|---|---|---|---|---|---|
| phL (qwen3.5, no indexer) | 50% | 588 | 7,149 | 15,474 | high out-tok overhead |
| M10.1b (qwen2.5-coder:32b, no idx) | 0% | 581 | 266 | — | refuted (executor capacity not lever) |
| M10.2 (hand-curated stub, prose) | 50% | 1,111 | 259 | **2,740** | confounded but Pareto-optimal |
| M28 (ClangdIndexer LSP) | 0% | 1,176 | 273 | — | falsified |
| **M29 (style constraint, no indexer)** | **0%** | **795** | **270** | **—** | falsified; **32% cheaper than M28** |

## Artifacts

| artifact | path |
|---|---|
| Pre-registration | [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) |
| Locked harness | [`m29_style_smoke.py`](m29_style_smoke.py) |
| Trial summaries | [`../bakeoff/runs-m29/`](../bakeoff/runs-m29/) (40 JSONs) |
| Captured finding | REQ-e349a0ad (loom store) |

To reproduce on any machine with g++ and qwen2.5-coder:32b in Ollama:

```bash
PATH="<g++-bin>:$PATH" \
  python3 experiments/m29_style_constraint/m29_style_smoke.py --sweep --n 10
```
