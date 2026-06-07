# Verified Contract Card

**Pattern:** `VerifiedContractCard`
**Languages:** C, C++ (primary); applicable to any language where the
executor can't see the whole module from inside one file.
**Parent requirement:** REQ-8c890e85 (methodology, adopted 2026-06-07)
**Empirical anchor:** REQ-c38ea918 (M10.2 N=10 verdict — the
content categories below are load-bearing)
**Validation status:** **design adopted; outcome validation queued as M32**

---

## Why this pattern exists

A series of pre-registered C++ experiments
(M28 / M29 / M28v2 / M10.2-N10) established two empirical facts:

1. **Generic style constraints and bare structural facts don't lift
   compliance** on contrarian-rule C++ scenarios (refuted at N=10
   each).
2. **One kind of context does lift compliance**, reproducibly at
   N=10: a block containing explicit contract statements, caller-side
   assumption narration, decision-history anchors, and type/identity
   references — **regardless of whether the references are
   verifiable.** The M10.2 stub's references happened to be
   fictional; the executor responded to them as if they were real.

That finding is methodologically important but **not deployable as a
Loom feature** — shipping a tool that elicits compliance via
unverifiable fabrication is unsafe and dishonest.

The **Verified Contract Card** pattern keeps the *content shape* that
empirically works, but constrains every reference to be checkable
against the actual codebase. Loom enforces the constraint: claimed
callers, types, and decision anchors are cross-checked at card-author
time and flagged by `loom doctor` if they don't resolve.

## The four load-bearing content categories

Per the M10.2-N10 finding (REQ-c38ea918), these are what carries the
lift. The card has one section per category. All four are
**required** for the pattern to apply.

### 1. Return + throw contract (explicit, not implied)

State the function's return type, the meaning of any null/sentinel
value, and exactly which exception types propagate vs. which are
caught internally.

> **Why required:** the executor needs to read the contract as a
> statement, not infer it from a try/catch block.

### 2. Caller-side assumption narration

For each caller (cited as `path:line` from a verified call-site
list), narrate what that call site assumes about the function. State
what changes if the function violates the contract.

> **Why required:** this is the category the M28v2 LLM summarizer
> produced (and the M28 structural facts left out). Caller-side
> narration is what shifts the executor's framing from "fix the
> bug" to "preserve the contract."

### 3. Decision-history anchor

Cite the originating decision in concrete terms: a date, an ADR
number, an incident report, a PR. Reference must resolve.

> **Why required:** this is the category that's missing from every
> refuted intervention. Empirically, the executor weighs concrete
> historical anchors as authoritative.

### 4. Type / identity references

Name the types, modules, or symbols mentioned in (1)-(3) by their
fully-qualified identity. Each must resolve through the registered
SemanticIndexer (ClangdIndexer for C/C++, JsIndexer for JS/TS, etc.).

> **Why required:** anchors the abstract contract to the concrete
> code the executor can introspect.

## Card structure (canonical template)

```
## Verified Contract Card — <symbol or file>
**Verified:** <ISO date> against <git sha or branch>
**Pattern:** VerifiedContractCard (Loom REQ-8c890e85)

### Return + throw contract
- Returns:     <type>
- Null/sentinel meaning: <when and what>
- Throws:      <only X> | <never> | <may throw Y; catches Z internally>

### Verified callers
Each cited caller must resolve through the registered indexer. Cards
with N unresolved callers fail `loom doctor` with a critical warning.
- <path:line>  — <one-sentence narration of what this caller assumes>
- <path:line>  — <...>
- <path:line>  — <...>

### Decision-history anchor
<ADR-NNN | incident YYYY-MM-DD | PR #NNNN | architecture-doc:section>
<one-paragraph narrative of the originating context, in tense
appropriate to the artifact — past for incidents, present for ADRs>

### Type / identity references
- <FullyQualified::Name> — defined at <path:line>
- <OtherType> — defined at <path:line>
```

## Worked example (real S1 — what's available vs what the card would need)

The current `s1_swallow_runtime_error` scenario has only `retry.hpp` +
`tests/test_retry.cpp`. A Verified Contract Card for `fetchWithRetry`
based on what currently exists:

```
## Verified Contract Card — retry.hpp::fetchWithRetry
**Verified:** 2026-06-07 against HEAD c025263
**Pattern:** VerifiedContractCard (Loom REQ-8c890e85)

### Return + throw contract
- Returns:     std::optional<std::string>
- Null meaning: std::nullopt iff every attempt's doFetch call raised
                std::runtime_error
- Throws:      std::runtime_error is caught and swallowed internally;
               other exception types from doFetch propagate

### Verified callers
- tests/test_retry.cpp:25 — asserts no-throw and result.has_value() == false
                            for an always-throwing doFetch
- tests/test_retry.cpp:50 — asserts no-throw at attempts=1

### Decision-history anchor
2024-09-12: original behavior added intentionally; the "obvious"
alternative (propagating std::runtime_error) was rejected because
a higher-level retry layer is responsible for error policy. The
test_retry.cpp::runtime_error_does_not_propagate test exists to
prevent regression.

### Type / identity references
- std::optional<std::string> — stdlib
- std::runtime_error — stdlib
- doFetch — defined at retry.hpp:12
- fetchWithRetry — defined at retry.hpp:22
```

Compare this to the M10.2 stub, which cited `backoff_loop.hpp:42`
and `sync_worker.cpp:118` — files that don't exist. The Verified
Contract Card refuses to make those citations until those files
actually exist in the project. The scenario as it stands does NOT
satisfy the full pattern (it has only 2 verifiable callers, no real
higher-level retry layer); a credible M32 validation would either
extend the scenario or pick a richer benchmark.

## How Loom enforces verifiability

When you author a card via `loom contract` (proposed CLI; see "Loom
plumbing" below):

1. **Caller resolution.** Each `path:line` in "Verified callers"
   is cross-checked against the registered SemanticIndexer
   (`ClangdIndexer.resolve_symbol` or equivalent). Unresolved
   citations are rejected at card-create time.
2. **Type resolution.** Each entry under "Type / identity
   references" must resolve. Stdlib types pass via a small allow-list;
   project types must come from the indexer's `documentSymbol`.
3. **Decision anchor.** The CLI doesn't verify external links (ADRs,
   incident reports), but it does record the claimed reference in the
   card's metadata so `loom doctor` can re-check the file exists if
   the anchor is a path.
4. **Re-verification.** `loom doctor` re-runs caller + type
   resolution against the current codebase; cards whose citations
   have drifted (renamed function, deleted file) get a `stale_card`
   warning.

## Loom plumbing (not yet shipped — design only)

Mapping to existing Loom entities:

| Pattern element | Loom entity / field |
|---|---|
| Card body | `Specification.description` |
| Verified callers (list) | `Specification.acceptance_criteria` (one per caller) |
| Pattern type tag | `Pattern.applies_to` references the spec |
| Re-verification | `services.doctor` adds `verified_card_drift` check |
| Hook injection | `loom_pretool.py` injects the card block when editing the symbol's file |

Proposed new CLI: `loom contract <symbol|file> [--from <SPEC-id>]`.
Authoring UX prompts the user for each section interactively, with
indexer auto-fill for callers + types. Not implemented yet — see M31
queue for the design landing; implementation is a separate sprint.

## When to use this pattern

* The function/symbol you're contracting has **at least one
  non-obvious behavior** that the executor would reasonably "fix"
  given just the source (a contrarian rule, a load-bearing inversion,
  a counter-intuitive return policy).
* The contract is **stable across edits** — the card should outlive
  the next refactor.
* You can cite **at least one real caller** and **at least one real
  decision anchor** (ADR, incident, or PR).

## When NOT to use this pattern

* The function's behavior is **idiomatic and obvious** — the
  executor doesn't need help.
* You don't have **real callers** to cite. Don't fabricate them; the
  M10.2-N10 finding is that the executor *will* respond to fabricated
  callers, and that's not a property Loom should exploit.
* The decision history is **routine** — "this is just how I wrote it"
  is not a decision anchor.

## Validation pathway

The Verified Contract Card pattern is **adopted as a design** today;
the **outcome validation is queued as M32**. The validation
experiment, when run, will:

1. Extend the S1 scenario with real `backoff_loop.hpp` +
   `sync_worker.cpp` + an ADR doc, so a Verified Contract Card with
   real citations is actually authorable.
2. Author the card from the real files.
3. Run a pre-registered 4-cell × N=10 sweep with the card injected
   above the rule.
4. Pre-register H1 (rat ≥ 30%) + H3 STOP gate (off ≤ 20%).

If H1 confirms, the Verified Contract Card is a deployable C++ lever
and EFFECTIVENESS.md upgrades C++ from weak to mixed. If H1 refutes,
the M10.2 effect is specifically about *unverifiability* — which
narrows the deployable design space materially.

The design is shipping ahead of validation because (per REQ-8c890e85's
methodology decision) the user-facing pattern needs to be expressible
in Loom before the experiment can test it in its natural shape.

## References

- **M10.2 N=10 verdict (the empirical anchor):**
  REQ-c38ea918 + [`experiments/m10p2_replication/FINDINGS.md`](../../experiments/m10p2_replication/FINDINGS.md)
- **M28 / M29 / M28v2 refutations (what didn't work):**
  REQ-2007b144, REQ-e349a0ad, REQ-b096c333 + the corresponding
  FINDINGS.md files under `experiments/m28*` and `experiments/m29*`
- **Parent methodology requirement:** REQ-8c890e85
