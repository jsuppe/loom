# M28v2 — ClangdIndexer + LLM-summarized contract prose: Pre-registration

**Drafted:** 2026-06-06 (after M28 Phase 1 + M29 Phase A both REFUTED)
**Status:** **DRAFT — locks after user review of the summarization prompt**
**Methodology pattern:** REQ-3896db58
**Builds on:** M10.2 stub indexer (the prose-confounded baseline),
M28 ClangdIndexer (REQ-2007b144, falsified), M29 style constraint
(REQ-e349a0ad, falsified)

> **Hypothesis under test (single sentence):**
> Augmenting ClangdIndexer's structural-facts output with an
> LLM-summarized contract-prose layer recovers the M10.2 stub's rat
> cell lift, demonstrating that *prose*, not *structural facts*, is
> the C++ S1 carrier — and that the prose can be generated rather
> than hand-authored.

---

## Why this experiment

M28's FINDINGS.md established the asymmetry empirically:

| intervention | rat cell pass rate |
|---|---|
| M10.2 hand-curated stub (prose + structural facts) | 50% (3/6) |
| M28 ClangdIndexer (structural facts only) | 0% (0/10) |

The M10.2 stub block contained ~8 sentences of authored prose:

> "IMPORTANT: this call site does NOT have a try/catch around
> fetchWithRetry. It assumes fetchWithRetry returns std::nullopt on
> failure and never throws. If fetchWithRetry propagates
> std::runtime_error, BackoffLoop::run will let it bubble up uncaught
> — a contract violation that production hit on 2024-09-12."

ClangdIndexer's LSP output has the underlying facts (the call site,
no try/catch in the surrounding window) but none of the *contract
narration*. M28v2 tests whether wrapping the structural facts in
generated prose recovers the effect.

This is two questions packed in:

1. **Mechanism:** Does prose carry the M10.2 lift, OR was it
   something else about the hand-curated block (length, format,
   "IMPORTANT" caps, the production-incident anchor)?
2. **Scalability:** Can an LLM generate prose that works, OR is
   hand-authored prose load-bearing in a way that doesn't scale?

A confirmed H1 answers both: prose is the carrier AND LLM-generated
prose suffices. A refuted H1 with confirmed H3 narrows the M10.2
effect to specifically hand-authored prose — a meaningful (if
disappointing) finding.

## Pre-registered hypotheses

**H1 (primary):** Rat cell ≥ 30% on M28v2 vs M28's 0% baseline. The
30pp threshold is more aggressive than M28/M29's 20pp because M10.2
showed +40-50pp lift on rat cell with prose. A lift below 30pp
suggests the LLM-generated prose isn't as load-bearing as the
hand-curated version.

* **Confirms:** rat ≥ 30%. Prose is the carrier, LLM generation
  scales. EFFECTIVENESS.md gains a "C++ with LLM-augmented
  ClangdIndexer = mixed fit" claim.
* **Refutes:** rat ≤ 10%. Prose is not sufficient or LLM-generated
  prose is qualitatively worse than hand-curated.
* **Inconclusive:** 10-29%. Mid-band; expand N or audit the
  generated prose qualitatively.

**H2 (secondary, token efficiency):** Combined prompt input tokens
< 2,000 per trial. M28's input was 1,176; if the prose layer adds
≥ 800 input tokens, M28v2 prompts may approach context-window
overhead that defeats the lift. The 2,000 ceiling lets us call
"too expensive even if effective" a falsified efficiency claim.

**H3 (tertiary, STOP gate):** Off cell ≤ 20%.

This is the **critical pre-reg discipline** for M28v2. The LLM
summarizer is given the source file + structural facts. If the
summarizer infers the contract from the source (which it can — the
S1 code is small and self-explanatory) and the inferred contract
matches the contrarian rule, the prose will read like an inline
restatement of the rule. Off cell would lift because the model
already sees rule-equivalent content even before the explicit rule
appears.

**H3 fires (off ≥ 40%) means the summary prompt leaked.** Stop and
re-author the summary prompt to be more rule-neutral before
evaluating H1.

## The load-bearing artifact: the locked summarization prompt

The summarizer MUST be isolated from the rule and the task. Locked
input shape:

```
You are reading a small C/C++ source file plus a structural-facts
block extracted by an LSP indexer. Your job is to produce a brief
"contract description" — 4 to 8 sentences — explaining what the
function(s) in the file appear to do, what their callers seem to
expect, and what would observably change if the function's behavior
were different.

Rules:
- Do not speculate about bugs, fixes, or "should" statements.
- Do not recommend changes.
- Stay descriptive. Refer to the code that exists, the call sites
  in the structural facts, and the surrounding context.
- Write in plain prose, not bullet points.
- Keep it under 1000 characters.

# Source file
{source_file_content}

# Structural facts (from clangd)
{clangd_context}

# Contract description
```

What this prompt INTENTIONALLY does NOT contain:
- Any task description (`fetchWithRetry should propagate ...`)
- Any rule text (the contrarian "do not propagate" rule)
- Any leading question ("what would happen if X were Y")
- Any value-laden framing ("good" / "bad" / "correct")

What the prompt DOES contain (acknowledged confound):
- The source code itself — which a sufficiently capable LLM could
  read and infer the obvious contract from. The H3 STOP gate is
  the guard.
- The structural facts including call-site lines. A caller's
  `if (result.has_value())` pattern signals the no-throw contract
  even without a rule.

If H3 fires, the only way forward is to remove more from the
summarizer's input — e.g., omit call-site surrounding lines that
imply caller assumptions. Document the iteration as M28v2.1 with a
new locked prompt; do not modify this prompt post-hoc.

## Locked harness

| Component | Locked value |
|---|---|
| Driver | `experiments/m28v2_clangd_prose/m28v2_smoke.py` (clone of m28_clangd_smoke.py + summarizer call) |
| Scenario | Same S1 (`crosssession_cpp/s1_swallow_runtime_error/`) |
| Executor model (trial generator) | `qwen2.5-coder:32b` (same as M28, M10.2) |
| Summarizer model | `anthropic:claude-haiku-4-5` if `ANTHROPIC_API_KEY` set, else `qwen2.5-coder:32b`. The M28 F1 fix (REQ-cc95b9a1, commit f3e8940) means fallback emits a stderr warning so we know which model was used. |
| Temperature / seed | Same as M28 (matches phL2 verbatim, REQ-ec63fa50) |
| N per cell | 10 (matches M28/M29; Wilson 95% CI bands are comparable) |
| Cells | off, on-rule, on-rule+placebo, on-rule+rat |
| Prose caching | The summary is generated ONCE for retry.hpp at sweep start and reused across all 40 trials. The summary input does not depend on cell. |

## Independent design review

**Status:** PENDING. The user must review:

1. The summarization prompt above. Is the rule-leak risk acceptable
   given the H3 STOP gate? Are there words to remove or replace?
2. The H1 30pp threshold. Reasonable given M10.2's effective +50pp
   lift? Too aggressive given M28v2 may not match hand-authored
   quality?
3. The fallback summarizer choice. If `ANTHROPIC_API_KEY` isn't set,
   using qwen2.5-coder:32b as the summarizer means the same model is
   both summarizing AND generating — possible self-reinforcement
   confound. Acceptable for v1, or do we require Haiku?

Sub-agent review optional. Recommended IF either: (a) the user
flags an issue with the prompt that the sub-agent could
independently spot, or (b) the summarizer falls back to qwen and
we want a second opinion on the self-reinforcement risk.

## Methodology compliance checklist (REQ-3896db58)

| Step | Status |
|---|---|
| 1. Independent design review | pending — user must approve summarization prompt |
| 2. Pre-registration locked before code lands | locks after user approval |
| 3. Independent taxonomy check | N/A |
| 4. Cross-vendor judge calibration | N/A (grading is deterministic pytest) |
| 5. Honest falsifier verdict | bound by H1 ≤ 10pp falsifier and H3 ≥ 40pp STOP gate |

## Anti-Texas-sharpshooter commitments

Same standards as M28 / M29. Explicitly:

1. **Exclusions locked before run.** Summarizer-call failures or
   harness crashes → replace trial, never silently drop.
2. **Three pre-registered hypotheses (H1, H2, H3).** Any post-hoc
   claim outside these three is hypothesis-generation.
3. **Null results count.** H1 refutation is a real finding; do not
   spin "needs better summarizer" without re-pre-registering.
4. **The summarization prompt is locked verbatim.** Any change
   between this commit and M28v2's first trial requires a
   superseded-by audit-log entry in the loom store.
5. **H3 STOP gate is binding.** If off ≥ 40%, freeze the H1 verdict
   as "uninterpretable due to prose leak" and re-author the prompt
   in M28v2.1.

## Expected direction (locked predictor's prior)

I expect H1 to **confirm** (rat ≥ 30%) — the M10.2 stub data + the
M28/M29 falsifications form a chain of evidence that prose is the
carrier. The risk is H3 firing because the LLM summarizer infers the
contract from the code's obvious shape (a retry loop with a try/catch
that returns nullopt is contract-bearing on its face).

**If H1 confirms AND H3 passes**, this is the strongest possible
result: prose is the lever, the lever scales to LLM-generated text,
the pre-reg-disciplined chain has produced a working C++ intervention
after two falsifications.

**If H3 fires**, the summarization prompt needs iteration (M28v2.1)
to reduce leak. This is informative — it tells us how much of the
contract a capable LLM can infer from source alone.

**If H1 refutes with H3 passing**, the finding is "LLM-generated
prose is qualitatively different from hand-authored prose in a way
that matters for compliance." Worth investigating; would prompt a
diff study between the M10.2 stub's prose and the M28v2 generated
prose.

Logging this prior before the run prevents post-hoc rationalization
in any direction.

## Sequencing

```
This pre-reg drafted
    ↓
User reviews summarization prompt + thresholds
    ↓
[if approved] Pre-reg locked → harness written → smoke trial
    ↓
N=40 sweep → verdict → finding capture
    ↓
EFFECTIVENESS.md updated (gain or honest-null #6)
```

## Effort estimate

| step | effort |
|---|---|
| User review of summarization prompt | 5-15 min |
| Author m28v2_smoke.py (M28 harness + summarizer call) | 1-2 hours |
| Smoke test (1 trial per cell) | 5 min |
| Execute N=40 sweep | ~30 min wall |
| Verdict + finding capture + EFFECTIVENESS.md update | 0.5 day |

Total: ~1 day if H3 passes; +0.5 day if M28v2.1 iteration triggers.

## References

- **M28 pre-reg + findings** —
  [`../m28_clangd_indexer/PRE_REGISTRATION.md`](../m28_clangd_indexer/PRE_REGISTRATION.md),
  [`../m28_clangd_indexer/FINDINGS.md`](../m28_clangd_indexer/FINDINGS.md)
- **M29 pre-reg + findings** —
  [`../m29_style_constraint/PRE_REGISTRATION.md`](../m29_style_constraint/PRE_REGISTRATION.md),
  [`../m29_style_constraint/FINDINGS.md`](../m29_style_constraint/FINDINGS.md)
- **M10.2 baseline (the prose-confounded reference)** —
  [`../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md`](../bakeoff/FINDINGS-bakeoff-v2-cpp-stub-indexer.md)
- **M11.5 model dispatch pattern (anthropic-then-ollama):** REQ-ec36bd89
  and related in the loom store
- **REQ-cc95b9a1 (M28 F1 — silent fallback warning):** the warn-on-fallback
  fix that ensures we know which summarizer model was used
