# M11.5 P0 — Intake-classifier pilot results

**Date:** 2026-05-02
**Question:** Does the requirement-shape classifier prompt + qwen3.5
hit the precision ≥ 90% gate the M11.5 spec specifies as the
go/no-go for building the intake hook?
**Approach:** 40 hand-labeled chat utterances (20 positive
requirement-shape, 20 negative). Each runs through the verbatim
spec prompt via `services._call_decomposer_llm`. Score precision
(false positives = polluted store), recall, latency, and observed
failure modes.
**N:** 40 trials, 0 errors, 0 parse failures.

---

## TL;DR

> **Gate cleared.** Precision **95.2%** (1 false positive in 21
> positives), recall **100%** (all 20 real requirements detected),
> F1 0.976. p50 latency 454ms, p95 617ms — well inside the 1s/5s
> budget the spec set.
>
> The single false positive ("Make this faster if possible.") is a
> genuinely ambiguous case my own dataset notes flagged as borderline.
> No systematic failure mode worth iterating on the prompt for.
>
> Domain extraction was 50% accurate, but the misses are split
> between (a) subjective category overlap (behavior vs architecture)
> and (b) the model inventing `security` as a domain not in the
> prompt's enumeration. The M11.5 spec's domain-whitelist guardrail
> already routes unexpected domains to the propose branch, so this
> doesn't undermine the auto-capture story.
>
> **Verdict: ship P1 (hook scaffold).**

---

## Empirical record

| metric | value | spec target |
|---|---|---|
| N | 40 | 30-50 ✓ |
| Positives correctly captured | 20/20 | — |
| Negatives correctly skipped | 19/20 | — |
| Precision | **0.952** | **≥ 0.90 ✓** |
| Recall | 1.000 | (secondary) |
| F1 | 0.976 | — |
| Accuracy | 0.975 | — |
| Errors / parse failures | 0 / 0 | 0 ✓ |
| Latency p50 | 454 ms | ≤ 500 ms ✓ |
| Latency p95 | 617 ms | (informational) |

Per-utterance results:
`experiments/pilot/intake_classifier_results_ollama_qwen3.5_latest.json`.

---

## The single false positive

**N17:** "Make this faster if possible."
The dataset's own notes flagged this as "vague optimization request,
not a measurable requirement." The classifier returned:

```json
{"is_requirement": true,
 "domain": "behavior",
 "value": "The system must improve its performance speed.",
 "rationale_excerpt": "Make this faster if possible."}
```

This is genuinely ambiguous. "Make this faster" CAN be read as a
performance requirement (system must be fast). The dataset author's
intuition was that "if possible" softens it to a request rather than
a rule, but reasonable people would split. Iterating on the prompt
to catch this would risk over-pruning genuine vague-but-real
performance requirements.

**Mitigation in the hook architecture:** N17-style cases with
`if possible` / `try to` / `would be nice` softeners should ideally
land in the propose branch (user picks) rather than auto-link, so
the user gets a chance to reject before persistence. The proposed
implementation: a softener-detection guardrail in the hook before
deciding the branch — if the value contains hedging language,
downgrade auto-capture to propose regardless of candidate score.

---

## Domain accuracy — secondary metric, not blocking

10/20 true positives matched my expected domain. The misses break
down:

| pattern | count | examples |
|---|---|---|
| behavior ↔ architecture (subjective) | 5 | P01 (rate-limit), P03 (retry loop), P05 (don't edit configs), P14 (structured logging), P18 (reversible migrations) |
| inventing `security` (not in enum) | 2 | P11 (validate URLs), P20 (SQL injection) |
| ui ↔ behavior | 1 | P12 (dashboard FPS) |
| data ↔ behavior | 2 | P09 (state-transition logging), P10 (export formats) |

Two distinct issues with different fixes:

1. **Subjective overlap (8 of 10 misses).** "Rate-limit endpoint X"
   is genuinely both behavior (what it does) and architecture (a
   project-wide constraint). This is a labeling-disagreement issue,
   not a model error. Domain matters for filtering / downstream
   surfacing but not for whether the requirement is captured. Not
   fixing.

2. **Out-of-enum value (`security`).** The model invented a domain
   not in the prompt's enumeration. Two possible fixes:
   - Tighten the prompt: "Output domain MUST be one of [...]; if
     none fit, use 'behavior'."
   - Add `security` to the canonical domain list (it's a real
     concern that doesn't fit cleanly into the existing four).
   The intake hook's domain whitelist (`behavior`, `data`,
   `architecture` for auto-capture) would route `security`-labeled
   reqs to the propose branch — user can confirm + correct domain
   manually. So this isn't blocking either.

If we wanted to harden the prompt, it would be a single-line
addition. Not doing it now — current behavior is graceful.

---

## What this rules in / rules out

**Rules in:** building the intake hook (M11.5 P1+) is justified.
The prompt + qwen3.5:latest combo passes the precision gate
comfortably with consistent sub-1s latency. Auto-capture on the
high-confidence branch will not pollute the store at any
problematic rate.

**Rules in:** the spec's three-branch decision tree is correct.
Recall at 100% means the classifier finds real requirements; the
worst case for the auto-capture branch is that *one ambiguous
hedge-language utterance per ~40 messages* sneaks through, and
the reversibility surface (`loom set-status REQ-x archived`) is
a tractable correction.

**Rules out:** the spec's "softener-detection guardrail" is
worth adding to the hook before P1 ships. N17 is exactly the
shape that guardrail catches.

**Doesn't rule out:** Anthropic Haiku as an alternative model.
The pilot ran qwen3.5:latest because `ANTHROPIC_API_KEY` wasn't
visible to the subprocess (env-passing quirk). qwen3.5 already
clears the gate — Haiku would likely match or improve, but it's
not necessary to validate further before P1.

---

## Recommended next moves

1. **Add a softener-detection guardrail to the spec** before P1
   ships. The N17 false-positive shape is detectable lexically
   ("if possible", "try to", "would be nice", "maybe", "consider")
   — when present, downgrade auto-capture to propose regardless
   of candidate score.
2. **Begin P1: hook scaffold.** `hooks/loom_intake.py` per the
   M11.5 spec, manually invocable for testing before being
   registered as a Claude Code hook in P2.
3. **Optional:** rerun the pilot with Anthropic Haiku for
   comparison once the env-passing is sorted. Not blocking.
4. **Optional:** add `security` to the canonical domain list, OR
   tighten the prompt to enforce the existing enum.

---

## Files of record

- `experiments/pilot/intake_classifier_dataset.json` — 40-item
  labeled set
- `experiments/pilot/intake_classifier_pilot.py` — runner / gate
- `experiments/pilot/intake_classifier_results_ollama_qwen3.5_latest.json`
  — per-utterance results, latency profile, raw model output
- `docs/DESIGN-rationale-linkage.md` Part 2 — M11.5 spec
- `ROADMAP.md` — M11.5 P0 status
