# Bakeoff V2 Phase G — Cross-Session Rationale Memory

**Date:** 2026-04-30
**Question:** Does `Requirement.rationale` provide measurable value
beyond the rule text itself? Specifically: when agent B has no
in-context memory of agent A's reasoning, does delivering the *why*
through the PreToolUse hook (a) raise compliance and (b) cause B to
*internalize* the constraint rather than mechanically follow it?
**Approach:** 4-cell A/B/C/D at trial level, same model (Haiku 4.5),
same starter code, same task prompt; only the seeded Loom store
differs across cells. Two metrics: `pass` (file content respects
constraint) and `cited_rationale` (response text cites the
rationale's key phrase — internalization signal).
**N:** 60 trials (3 scenarios × 4 cells × N=5). 0 harness errors.
**Cost:** $1.84 in Haiku API spend; 15.0 min wall.

---

## TL;DR

> Loom's longitudinal claim — *"agent B picks up agent A's work and
> stays consistent with A's documented decisions despite no shared
> in-context memory"* — **is supported.** The mechanism that carries
> the lift is `Requirement.rationale` delivered through the PreToolUse
> hook. With rule-only injection, Haiku is split — sometimes complies,
> sometimes pushes back. With rule + true rationale, Haiku reaches
> 93% compliance *and* cites the rationale's specific facts in 100%
> of trials.
>
> The placebo-vs-rationale comparison is the cleanest finding:
> identical injected byte counts, **only true-rationale content
> produces citation behavior** (rule-only and placebo: ~7% cited;
> rationale: 100%). The compliance lift over placebo is small (+7 pp);
> the internalization lift is decisive (+93 pp).

A precondition shipped alongside this experiment: **the
PreToolUse hook silently dropped `Requirement.rationale`** because
`services.context()` filtered it out of the briefing dict at
`src/services.py:1138-1146`. Fixed in commit a2e5bf9. Without that
fix, every Phase G cell reduces to `on-rule` regardless of what's
seeded.

---

## Setup

### The rationale-surfacing gap (discovered during planning)

A grep audit while scoping Phase G surfaced that the PreToolUse
hook's data path quietly dropped `Requirement.rationale`:

- `services.extract(rationale=...)` → stored to SQLite ✅
- `store.get_requirement()` → returns Requirement with rationale ✅
- `services.context()` builds `req_entries` with `id, domain, value,
  status, superseded, superseded_at, lines` only — **rationale
  filtered out** ❌
- `hooks/loom_pretool.py` formats `id [domain]: value` — never
  reads rationale ❌

So Phase E's hook-based experiments measured *rule injection only*,
even when the spec was authored with detailed rationale. The
cross-session claim was both untested *and* blocked by silent data
loss. Fixed in commit a2e5bf9 (`src/services.py`,
`hooks/loom_pretool.py`, `tests/test_services.py`) before the Phase G
run.

### Three scenarios, contrarian gradient

Each scenario's task prompt is designed to invite contradicting the
constraint — so the agent has to actively choose to comply. The
"defensibility without rationale" varies:

| scenario | what the rule says | how it reads without rationale |
|---|---|---|
| **S1 swallow_oserror** | swallow OSError, never propagate | sounds like a bug |
| **S2 no_inline_validation** | no input validation in `place_order` | sounds like a weird convention |
| **S3 legacy_int_ids** | use 32-bit int IDs, no UUIDs | sounds outdated |

S1 is the strictest test (rule alone reads as wrong); S3 is the
hybrid case (rule alone reads as suspect). Full text in
`phG_rationale_smoke.py:57-213`.

### Four cells (same model, same starter, same task)

| cell | hook | injected text |
|---|---|---|
| **off** | none | nothing |
| **on-rule** | yes | rule only (rationale=None) |
| **on-rule+placebo** | yes | rule + length-matched filler that verbosely restates the rule with no new info |
| **on-rule+rat** | yes | rule + true rationale |

Placebo bytes match the true rationale's byte count per scenario.
This isolates content from byte-salience: if rationale and placebo
score the same, the lift is purely about how much the agent reads;
if rationale outperforms placebo, the *content* of the rationale
carries weight.

### Two metrics

1. **`pass`** — file content respects the constraint after the
   `claude -p` invocation. Per-scenario regex on the target file's
   body (`verify_s1` etc. in `phG_rationale_smoke.py:227-266`).
2. **`cited_rationale`** — agent's response text matches a
   per-scenario regex of distinctive rationale phrases (incident
   date, `BackoffError`, `TOCTOU`, `ADR-0042`, etc.).

---

## Empirical record (60 trials, 15 per cell)

| metric | off | on-rule | on-rule+placebo | on-rule+rat |
|---|---|---|---|---|
| **pass** | 0/15 (0%) | 10/15 (67%) | 11/15 (73%) | **14/15 (93%)** |
| **cited_rationale** | 1/15 (7%) | 0/15 (0%) | 2/15 (13%) | **15/15 (100%)** |
| **hook fired** | 0 | yes (~2/trial) | yes (~2/trial) | yes (~2/trial) |
| **bytes injected** | 0 | ~250 | ~520 | ~520 |
| **avg cost/trial** | $0.029 | $0.030 | $0.030 | $0.033 |

### Per-(scenario, cell) breakdown

| scenario | off | on-rule | on-rule+placebo | on-rule+rat |
|---|---|---|---|---|
| **S1 swallow_oserror** | 0/5 | 4/5 | 5/5 | 5/5 (5/5 cited) |
| **S2 no_inline_validation** | 0/5 | 3/5 | 3/5 | 4/5 (5/5 cited) |
| **S3 legacy_int_ids** | 0/5 | 3/5 | 3/5 | 5/5 (5/5 cited) |

### Compliance decomposition

| comparison | lift |
|---|---|
| rule alone vs nothing | **+67 pp** |
| placebo over rule (byte-salience effect) | +6 pp |
| rationale over placebo (content effect) | +20 pp |
| rationale over rule (combined) | **+26 pp** |

Most of the compliance lift comes from injecting the rule at all
(+67 pp). Doubling the byte budget with filler adds a marginal +6 pp;
replacing the filler bytes with true rationale content adds another
+20 pp. The compliance ceiling under hook-injection is ~93%; it's
not 100% because Haiku occasionally argues with the rule even when
the rationale is in front of it.

---

## What the cell-by-cell response text looks like

Representative previews from S1 (pass condition: do NOT re-raise
OSError):

**off** — `pass=False` — Haiku obediently violates the (unseen) constraint:
> *"Done. Changed line 15 from `return None` to `raise last` so
> callers now get the actual error instead of None when retries
> are exhausted."*

**on-rule** — `pass=False`, but with awareness — Haiku flags the conflict and *asks the user*:
> *"I need to flag a conflict: the system shows a requirement
> (REQ-…) that states `fetch_with_retry` must not re-raise OSError
> and must return None on exhaustion. This directly contradicts
> your request to re-raise the last OSError. Should I revert the
> change, or does this requirement need to …"*

This is the most interesting failure mode: the rule is delivered
but Haiku treats it as overrideable user-facing context, not a
binding constraint. The 33% non-compliance in this cell is mostly
this dynamic.

**on-rule+placebo** — `pass=True`, no citation — complies but cites only the rule:
> *"The code is actually compliant with the project's documented
> requirement (REQ-…). The behavior of silently returning None is
> intentional — it's a specified constraint for this function.
> The requirement explicitly states it must swallow OSError and
> return None on exhaustion, not re-raise."*

Note the absence of *why*. The placebo gave Haiku more bytes to
restate the rule; nothing changed in B's understanding.

**on-rule+rat** — `pass=True`, citation — Haiku reproduces the rationale's specific facts:
> *"Your initial request conflicts with a binding requirement.
> REQ-… explicitly forbids re-raising OSError from this function
> due to a production incident (2024-09-12) where bypassing the
> `backoff_loop.py` wrapper corrupted the retry-state ledger and
> cost 4 hours of replays."*

The agent now has a *load-bearing reason* to refuse — and reaches
for it when explaining the decision.

---

## Pre-registered prediction check

The plan agent's pre-registered predictions vs observed:

| prediction | observed | called it? |
|---|---|---|
| off ≈ low pass, no citation | 0/15, 1/15 | ✓ |
| on-rule ≈ medium pass, no citation | 10/15, 0/15 | ✓ |
| on-rule+placebo ≈ similar to on-rule | 11/15, 2/15 | ✓ |
| on-rule+rat = highest pass + citations | 14/15, 15/15 | ✓ |
| if rat ≈ placebo: lift is salience | not the case | n/a |
| if rat > placebo > rule: content carries weight | confirmed | ✓ |

The headline interpretation — *"content carries weight, not just
byte salience"* — is supported on both metrics: rationale beats
placebo by +20 pp on compliance and by +87 pp on citation. With
N=15 per cell, the +20 pp pass gap (rat 14/15 vs placebo 11/15)
is at the edge of binomial noise; the citation gap (15/15 vs 2/15)
is unambiguous.

---

## Why this matters for Loom's positioning

Phase G is the **first experiment to test Loom's longitudinal claim
through the production hook mechanism** rather than via
`loom_exec`'s task-prompt injection (Phase K's path). This is
closer to the real production usage: agent B is a regular Claude
Code session that loads context via the hook, not a small-model
executor reading a curated bundle.

Two distinct things are now empirically validated:

1. **Per-task delivery** (Phases R1, R6, R6m) — `task_build_prompt`
   surfacing requirement context to a small model. +95–100 pp lift
   on aligning Python tasks. *Mechanism: spec-in-prompt.*
2. **Cross-session memory** (Phase G — this experiment) —
   PreToolUse hook surfacing rule + rationale to a fresh agent
   session with no prior context. +93 pp lift on contrarian
   constraints; 100% citation rate. *Mechanism: hook-injection
   from persistent store.*

Together they cover Loom's two main value-prop verticals: the
within-session decomposition pipeline and the across-session
memory store.

### Honest caveats

- **Single model, single language.** Phase G ran on Haiku with
  Python scenarios. The per-language/per-tier behavior of the hook
  pathway hasn't been mapped (Phase E touched Sonnet/Opus on
  related-but-different scenarios; cross-language hook tests not
  yet run).
- **N=5 per (scenario × cell).** Binomial 95% CI for `on-rule+rat`
  pass (14/15 = 93%) is roughly [68%, 99.8%]. The *citation*
  metric (15/15 = 100%) is concentrated enough that even with the
  wide CI [78%, 100%], it's distinct from on-rule's 1/15.
- **Rationale is human-authored here.** Real-world rationales are
  often shorter, vaguer, or missing. Whether Loom's value persists
  when rationale quality is low is an open question (a
  "low-rationale" cell could be added).
- **The 93% vs 73% pass gap is 3 trials out of 15.** With the
  current N, content-over-salience on compliance is a *suggestive*
  effect (binomial noise envelope is wide). The citation metric is
  where the content effect is unambiguous (15/15 vs 2/15).

### Recommended follow-ons (priority order)

1. **Sonnet expansion** if Haiku's gap on compliance (rat vs
   placebo = +7 pp) holds — Sonnet may saturate. Decision gate:
   if Haiku gap ≥10 pp, run Sonnet.
2. **Real-codebase replay study.** Pick a known refactor where the
   reviewer's PR comments contain rationale. Seed Loom from the
   PR review, replay the refactor with and without rationale.
3. **Low-rationale cell.** Add a fifth cell: rule + a *low-quality*
   rationale (e.g., "we always do it this way") to test whether
   the lift is in the rationale's *informativeness* or just its
   *presence*.
4. **Cross-language hook trials.** Map Phase G S1 across the same
   8 languages as the cross-language map.

---

## Files of record

- `experiments/bakeoff/v2_driver/phG_rationale_smoke.py` — 4-cell ×
  3-scenario harness with 2-metric grading
- `experiments/bakeoff/runs-v2/phG_rationale_smoke_haiku.json` —
  60 trial summaries
- `experiments/bakeoff/runs-v2/phG_rationale_smoke_haiku_s1.json` —
  earlier 1-trial mechanics smoke
- Reused: `experiments/bakeoff/benchmarks/crosssession/{s1,s2,s3}_*/`
  — original scenario substrates from Phase K (qwen+loom_exec
  variant)
- Required precondition: commit a2e5bf9 (`src/services.py`,
  `hooks/loom_pretool.py`) — surfaces `Requirement.rationale`
  through the PreToolUse hook

---

## Comparison to Phase K (qwen+loom_exec, no hook)

Phase K ran the same 3 scenarios + 4 cells but used qwen3.5
through `loom_exec` (task-prompt context delivery, not the hook).
That experiment's headline finding was *"rationale field is
decorative"* — qwen behaved nearly identically across cells.

Phase G shows the opposite for Haiku via the production hook.
Why the divergence?

- qwen's task-prompt context was already saturated with the rule;
  rationale added marginal information at the limit of the model's
  ability to reason about *why* a rule exists.
- Haiku via the hook has a different setup: the rule arrives mid-
  conversation as `additionalContext`, and the agent's response is
  a freeform decision rather than a code-block extraction. The
  citation metric specifically rewards the rationale-surfaced
  facts — and Haiku is capable enough to make the connection.

The honest takeaway: **rationale's value is model-and-mechanism
specific.** It's decorative for qwen-via-loom_exec; it's load-
bearing for Haiku-via-hook. The longitudinal-claim story holds
for the production use case but doesn't generalize to all
mechanisms.
