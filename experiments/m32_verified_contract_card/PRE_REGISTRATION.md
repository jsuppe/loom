# M32 — Verified Contract Card validation: Pre-registration

**Drafted:** 2026-06-07
**Status:** **DRAFT — locks after user review of the locked card text + scenario extensions**
**Methodology pattern:** REQ-3896db58
**Builds on:**
- M10.2 N=10 confirmation (REQ-c38ea918) — the empirical anchor
- M28 / M29 / M28v2 refutations (REQ-2007b144 / REQ-e349a0ad / REQ-b096c333) — the contrast
- REQ-8c890e85 + PAT-c1e17beb — the pattern this experiment validates
- `docs/patterns/VERIFIED_CONTRACT_CARD.md` — the design under test

> **Hypothesis under test (single sentence):**
> Replacing the M10.2 stub's fictional context with a Verified Contract
> Card whose every citation resolves against real sibling files
> recovers the M10.2 rat-cell lift, demonstrating that the LLM's
> response is driven by content shape rather than by the
> unverifiability of the citations.

---

## Why this experiment

M10.2 N=10 established (REQ-c38ea918) that the M10.2 stub block lifts
the rat cell to 40% reproducibly — but the stub references files that
don't exist in the scenario (`src/backoff_loop.hpp`,
`src/sync_worker.cpp`) and an invented production-incident anchor.
Three competing readings of the mechanism are live:

1. **Content-shape reading:** the executor responds to the four
   load-bearing content categories (return+throw contract, caller-side
   assumption narration, decision-history anchor, type/identity
   references) regardless of whether the citations are verifiable.
   *Prediction:* M32 (same shape, real citations) lifts comparably.
2. **Unverifiability reading:** the M10.2 effect specifically depends
   on the model treating *unfalsifiable* citations as authoritative.
   When the cited files appear in the prompt's context bundle, the
   model can read them and may discount the card's narrative as
   redundant or contradictory.
   *Prediction:* M32 refutes — rat cell stays at 0%.
3. **Hybrid:** verifiable citations work but with a smaller lift than
   the M10.2 stub achieved.
   *Prediction:* M32 partial — rat cell in 10-29%.

M32 discriminates between (1) and (2), and quantifies (3) if it
materializes. Either confirm or refute is a real, deployable finding
about Loom's C++ direction.

## Pre-registered hypotheses

**H1 (primary):** Rat cell pass rate ≥ 30% under the Verified Contract
Card. Threshold chosen to match M10.2 N=10's measured 40% rat cell
with a 10pp tolerance for variance.

* **Confirms** (rat ≥ 30%): the content-shape reading is supported.
  VerifiedContractCard is a deployable C++ lever. EFFECTIVENESS.md
  upgrades C++ from "weak" to "mixed-with-pattern." REQ-8c890e85's
  status moves from `adopted` to a future `verified` once we wire
  loom doctor enforcement.
* **Refutes** (rat ≤ 10%): the unverifiability reading is supported.
  Verifiable equivalents do NOT recover the M10.2 effect — the
  mechanism is specifically about the model accepting unfalsifiable
  claims. **This kills the VerifiedContractCard deployable direction**
  but is a deep methodological finding (LLM weighting of
  unfalsifiable plausibility). EFFECTIVENESS.md C++ stays weak; the
  pattern doc is updated with the refutation in a "validated as
  non-effective" section.
* **Inconclusive** (10-29%): partial lift; the hybrid reading. Worth
  refining the card or extending the scenario.

**H2 (secondary, comparison):** If H1 confirms, the verified card's
rat cell is within ±15pp of M10.2 N=10's 40%. Tests whether
verifiability comes with a meaningful efficiency cost. If verified is
substantially below 40% but still ≥30%, the lift is real but
reduced — informative about how much of the M10.2 effect is content
shape vs. unfalsifiability.

**H3 (tertiary, STOP gate):** Off cell ≤ 20%.

This is the **load-bearing pre-reg discipline** for M32. The
VerifiedContractCard's "Return + throw contract" section is
*descriptive* of the existing code's behavior — but the existing code
implements the contrarian rule. A descriptively-honest card states
what the rule prescribes. If the off cell lifts (≥ 40%), the card's
content has substituted for the rule, which means:

- We can't distinguish "card lifted compliance" from "the card just
  re-included the rule"
- H1's verdict becomes uninterpretable

The locked mitigation: the card's contract section uses **descriptive
language about the current code** (M10.2's pattern). The rule cells
get the prescriptive rule text in addition. If off lifts, we audit
which content is leaking — and re-author the card more tersely if
needed for an M32v2 run.

## Locked scenario extension

The current `s1_swallow_runtime_error` scenario has only `retry.hpp` +
`tests/test_retry.cpp`. M32 requires:

| New file | Purpose | Compile-tested |
|---|---|---|
| `src/backoff_loop.hpp` | Defines `BackoffError`, `BackoffLedger`, `BackoffLoop::run`. `BackoffLoop::run` calls `fetchWithRetry` and uses `.has_value()` without try/catch, matching the M10.2 stub's claimed caller. | yes — compiles cleanly under `-std=c++17 -Wall -Wextra` |
| `src/sync_worker.cpp` | Defines `SyncWorker::pull` using `fetchWithRetry` (matches M10.2 stub's second claimed caller). | yes |
| `docs/ARCHITECTURE.md` | Real decision document explaining the swallow-vs-propagate decision. Replaces the M10.2 stub's invented "production incident 2024-09-12" anchor with a concrete written ADR. | n/a — text doc |
| `compile_commands.json` | Extended to include the new translation units so clangd sees them. | yes |

The grading test (`tests/test_retry.cpp`) is **not modified** — same
test, same falsifier, apples-to-apples grading with M10.2 / M28 / M29
/ M28v2.

**The new files are part of the locked harness.** They become an
extension of the S1 scenario itself; future C++ experiments inherit
them. Authored before M32 starts and committed to a stable git sha
that the pre-reg references.

## Locked Verified Contract Card text

The card is authored once before the sweep, persisted to a known
location, and reused verbatim across all 40 trials. Per the pattern's
verifiability constraint, every citation must resolve against the
extended scenario.

Text locked at sweep-start time, stored at
`experiments/m32_verified_contract_card/locked_card.md` BEFORE any
trial runs. The card's content is bounded by the pattern doc's
template (`docs/patterns/VERIFIED_CONTRACT_CARD.md` §
"Card structure").

Post-lock edits to the card require a `supersede` audit-log entry in
the loom store and an M32v2 pre-reg.

## Locked harness

| Component | Locked value |
|---|---|
| Driver | `experiments/m32_verified_contract_card/m32_smoke.py` — clone of `m28_clangd_smoke.py` with two changes: ClangdIndexer is registered (for the extended scenario's real sibling files) AND a `## Verified Contract Card` block is prepended above `## Requirements`. |
| Scenario | Extended `crosssession_cpp/s1_swallow_runtime_error/` with the new sibling files committed. |
| Executor model | `qwen2.5-coder:32b` (same as M28/M29/M28v2/M10.2) |
| Temperature / seed | Same as M28 (no explicit setting; REQ-ec63fa50 drift) |
| N per cell | 10 |
| Cells | off, on-rule, on-rule+placebo, on-rule+rat |
| Output dir | `experiments/bakeoff/runs-m32/` |

## Independent design review

**Status:** pending — user must review:

1. The H3 STOP gate threshold (off ≤ 20%). Is this strict enough,
   given the card's contract section overlaps with the rule's
   content? Should H3 be ≤ 10% or ≤ 30%?
2. The scenario extension authoring. The new sibling files should
   reflect a *plausible* real codebase — not constructed to maximize
   the card's effect. Worth a quick review of the new file shapes
   before they're locked.
3. The locked card text. The card is the experimental artifact; its
   exact wording is load-bearing. Review before commit.

Sub-agent review optional. Recommended if the user's review surfaces
ambiguity, OR if the new sibling files turn out to substantively
shape the result.

## Predictor's prior (locked)

I lean ~50% confirm, ~40% refute, ~10% inconclusive.

**Reasoning for confirm:** The LLM doesn't actually cross-check
verifiability claims — it just reads the prompt and produces
consistent text. If the M10.2 stub's content shape is what the model
responds to, then a verified card with the same shape should produce
the same response.

**Reasoning for refute:** With verifiable citations and the cited
files actually present in the prompt (via context_files), the model
might find the card's narrative redundant — or might find the
context-files reveal that the citations are *accurate but generic*
(no actual production-incident anchor; the ADR is dry). The M10.2
stub's prose had emotional weight ("production incident 2024-09-12
lost three hours") that a real ADR likely won't replicate.
**Reasoning for inconclusive:** mid-band reflects a real partial
effect — the verified card lifts something but less than the
fictional version.

If H1 confirms, the prior reasoning for refute becomes a follow-up:
characterize whether the lift is robust to "dry" decision-anchor
prose vs. "narrative" anchor prose. That's an M32v2.

## Methodology compliance checklist (REQ-3896db58)

| Step | Status |
|---|---|
| 1. Independent design review | pending — user must approve scenario extension + locked card text |
| 2. Pre-registration locked before code lands | locks after user approval; scenario extension follows |
| 3. Independent taxonomy check | N/A |
| 4. Cross-vendor judge calibration | N/A (deterministic g++ grading) |
| 5. Honest falsifier verdict | H1 ≤ 10% kills the deployable direction; H3 ≥ 40% kills H1's interpretability |

## Anti-Texas-sharpshooter commitments

Same standards as M28 / M29 / M28v2 / M10.2-N10. Explicitly:

1. **Exclusions locked.** Harness crashes → replace trial; no silent
   drops.
2. **Three pre-registered hypotheses (H1, H2, H3).** Post-hoc claims
   outside these are hypothesis-generation.
3. **Null results count.** H1 refutation kills the deployable
   direction; the finding goes into EFFECTIVENESS.md's honest-null
   section and the pattern doc gains a "validated as non-effective"
   notice.
4. **The card text is locked verbatim.** Edits require an M32v2
   pre-reg.
5. **The scenario extension files are locked.** Once committed,
   their contents are frozen for the duration of the M32 sweep.
6. **H3 STOP gate is binding.** If off ≥ 40%, the H1 verdict is
   tagged uninterpretable, the card is re-authored more tersely, and
   M32v2 runs against the new card.

## Sequencing

```
This pre-reg drafted
    ↓
User reviews (a) H3 threshold, (b) scenario extension shape,
              (c) locked card text
    ↓
Pre-reg locks → scenario extension authored + committed
    ↓
Locked card text authored from the extended scenario + committed
    ↓
Harness written (m32_smoke.py)
    ↓
Smoke trial (1 per cell)
    ↓
N=40 sweep
    ↓
Verdict + finding + EFFECTIVENESS.md update + pattern doc validation status update
```

## Effort estimate

| step | effort |
|---|---|
| User review of pre-reg + scenario shape + card | 15-30 min |
| Author scenario extension (3 new files + compile_commands update) | 2-3 hours |
| Author locked card text | 30 min |
| Author harness (clone m28 + insert card block) | 1 hour |
| Smoke trial | 15 min |
| N=40 sweep | ~30 min wall |
| Verdict + findings + downstream doc updates | 1 hour |

**Total estimated effort:** ~6 hours of focused work, runnable in one
session or split across two.

## What changes downstream

**If H1 confirms:**
- EFFECTIVENESS.md: C++ moves from "weak" to "mixed-with-pattern"
  with an explicit caveat that the lift requires the
  VerifiedContractCard pattern with all four content categories.
- `docs/patterns/VERIFIED_CONTRACT_CARD.md`: validation status moves
  from "design adopted; outcome validation queued" to "design adopted
  and validated at N=10 on S1; CI [X%, Y%]".
- REQ-8c890e85 status: `adopted` → a future `verified` once `loom
  doctor` enforcement also ships.
- A `loom contract <symbol>` CLI gets prioritized in M33.
- Token-efficiency rollup gains an M32 row showing the verified card's
  cost vs M10.2 N=10's.

**If H1 refutes:**
- EFFECTIVENESS.md: C++ stays weak. New honest-null #8 entry
  explicitly: "verifiable equivalents of the M10.2 stub do NOT
  recover the lift; the mechanism is specifically about
  unfalsifiable plausibility."
- `docs/patterns/VERIFIED_CONTRACT_CARD.md`: validation status moves
  to "design adopted; outcome validation REFUTED for this scenario."
- REQ-8c890e85 status: `adopted` → likely `deprecated` after a brief
  audit of whether the pattern still has *documentation* value even
  without compliance lift.
- M33 candidate: characterize the unfalsifiable-plausibility
  mechanism as a cross-model phenomenon; this becomes a research
  finding rather than a Loom feature direction.

Either outcome lands as a concrete result.

## References

- **Empirical anchor:** REQ-c38ea918 +
  [`../m10p2_replication/FINDINGS.md`](../m10p2_replication/FINDINGS.md)
- **Pattern under test:** REQ-8c890e85 + PAT-c1e17beb +
  [`../../docs/patterns/VERIFIED_CONTRACT_CARD.md`](../../docs/patterns/VERIFIED_CONTRACT_CARD.md)
- **Methodology pattern:** REQ-3896db58
- **Drift inherited from M28 (no explicit temperature):** REQ-ec63fa50
- **Contrast experiments (what didn't work):** REQ-2007b144 (M28),
  REQ-e349a0ad (M29), REQ-b096c333 (M28v2)
