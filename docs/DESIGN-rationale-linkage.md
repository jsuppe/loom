# Design — Rationale Linkage (proposed M11.1)

**Status:** sketch, not committed.
**Author:** captured 2026-05-02 from a design conversation about rationale-capture-at-intake.
**Companion roadmap entry:** none yet — would slot as M11 if approved.

## Motivation

The full M10 experimental series (phQ3 / phQ4 / phQ5 / phQ7) showed that
**rationale is the load-bearing signal for compliance** on contrarian
specs — not the indexer, not the executor, not the model size. Bare
rule + no rationale = 0% on contrarian cells; rule + rationale = 100%
saturation. The indexer amplifies the rationale; it does not
manufacture compliance.

That makes **rationale capture** the single most important user
discipline. And it is the discipline users skip most often — running
`loom extract --rationale "..."` after every chat is a friction tax,
and rationale typed minutes after the decision is usually thinner than
the actual reasoning was.

The design below shifts rationale capture from a manual step to a
structured field that supports two modes:

1. **Linkage** — most "new" requirements derive from existing
   decisions. Capturing the link is more honest (and durable) than
   re-prosing the rationale.
2. **Free-form text** — when there's a genuinely novel decision, prose
   rationale is preserved as today.

Plus a third, visibility state:

3. **`rationale_needed`** — the agent didn't find linkage *and* the
   user didn't supply prose. Surfaced as visible debt rather than
   silently captured as "no rationale."

## Data-model changes

### `Requirement` (in `src/loom/store.py`)

Two new fields, one new status. All backward-compatible via
`setdefault` in `from_dict`.

```diff
 @dataclass
 class Requirement:
     id: str
     domain: str
     value: str
     source_msg_id: str
     source_session: str
     timestamp: str
     superseded_at: Optional[str] = None
     elaboration: Optional[str] = None
     rationale: Optional[str] = None
+    # M11: structured citation chain. When this requirement derives
+    # from one or more prior decisions, list their req_ids here.
+    # Coexists with `rationale` (prose) — a requirement may have
+    # both, either, or neither (the third case sets
+    # status="rationale_needed" so it surfaces as debt).
+    rationale_links: Optional[List[str]] = None
-    status: str = "pending"
+    status: str = "pending"  # +rationale_needed in M11
     acceptance_criteria: Optional[List[str]] = None
     test_spec_id: Optional[str] = None
     conversation_context: Optional[str] = None
     last_referenced: Optional[str] = None
```

`to_dict` / `from_dict` migration:

```python
@classmethod
def from_dict(cls, d):
    d.setdefault('elaboration', None)
    d.setdefault('rationale', None)
+   d.setdefault('rationale_links', None)
    d.setdefault('status', 'pending')
    # ... unchanged
    return cls(**d)
```

Empty-list sentinel handling matches `acceptance_criteria` —
`["TBD"]` round-trips as "unset."

### `VALID_STATUSES` (in `src/loom/services.py`)

```diff
 VALID_STATUSES = (
     "pending", "in_progress", "implemented", "verified",
-    "superseded", "archived",
+    "superseded", "archived", "rationale_needed",
 )
```

`rationale_needed` is filtered from `loom list` and `loom query` by
default the same way `archived` is — surfaced explicitly via
`--include-rationale-needed` or `--all`. It IS counted in
`loom stale` (it's the most actionable kind of stale).

### `is_complete()` semantics

Currently: `elaboration AND acceptance_criteria`. The proposed
extension:

```python
def is_complete(self) -> bool:
    has_rationale = bool(self.rationale or self.rationale_links)
    return bool(
        self.elaboration
        and self.acceptance_criteria
        and len(self.acceptance_criteria) > 0
        and has_rationale  # M11 addition
    )
```

This is breaking for callers who relied on `is_complete()` returning
True for reqs without rationale. Audit needed before flipping.
Probably gate behind a config flag for one release, then make
default in the next.

## Service layer

### New: `services.find_related_requirements`

```python
def find_related_requirements(
    store: LoomStore,
    text: str,
    *,
    limit: int = 5,
    min_score: float = 0.45,  # cosine similarity threshold; calibrate
    exclude_superseded: bool = True,
    exclude_archived: bool = True,
) -> list[dict[str, Any]]:
    """Semantic + textual search for prior decisions related to ``text``.

    Wraps `services.query` with: (a) a confidence floor below which
    matches are dropped, (b) status filtering by default, (c) a
    structured shape for the intake hook to consume.

    Returns:
        [{
            "req_id": str,
            "value": str,
            "domain": str,
            "rationale": Optional[str],  # the link target's rationale
            "rationale_links": Optional[list[str]],  # transitive chain
            "score": float,  # 0..1 cosine similarity
            "reason": str,  # human-readable why-it-matched
        }]

    The reason string is short and prompt-friendly — ``"shares 'rate
    limit', 'checkout'"`` — so the agent can quote it back to the user.
    """
```

Implementation: leans on existing `services.query` (already returns
ranked semantic matches via the embedding store). The new layer adds
score-floor, status-filter, and shape-massage. ~50 LoC.

### Updated: `services.extract`

Today: `extract(text, rationale=None, ...)`. Add:

```python
def extract(
    store: LoomStore,
    domain: str,
    value: str,
    *,
    rationale: Optional[str] = None,
    rationale_links: Optional[list[str]] = None,  # NEW
    # ... existing kwargs
) -> dict:
```

Validation rules at extract time:
1. If `rationale_links` is given, every entry must resolve to an
   existing non-superseded requirement (else `ValueError`).
2. If neither `rationale` nor `rationale_links` is present, the new
   requirement's status defaults to `"rationale_needed"` instead of
   `"pending"`.
3. If `rationale_links` would create a cycle (req A links to B, B
   already links to A), reject with `ValueError`.

### Updated: `services.set_status`

Allow `set_status(req_id, "rationale_needed")` so the user can flip
an existing req into the visible-debt state. And the inverse —
flipping out of `rationale_needed` requires `rationale` or
`rationale_links` to be set, else `ValueError`.

### Updated: `services.metrics` and `services.health_score`

`rationale_needed` reqs count against:
- `coverage` (counted as "with rationale" only when
  `rationale OR rationale_links` is non-empty)
- `health_score`'s rationale component (NEW component, replacing
  one slot in the equal-weighted average — see below)

### Possible: new health-score component

Current health-score components (M5.3): `impl_coverage`,
`test_coverage`, `freshness`, `non_drift`. Proposed addition:

```
rationale_coverage = % of active reqs with rationale_text OR rationale_links
```

Either:
- (a) extend to 5 components (new equal-weighted average)
- (b) replace one (probably `non_drift`, which is the noisiest signal)
- (c) leave health_score alone and surface rationale-coverage as a
  separate metric

(a) is simplest; (b) is most opinionated; (c) is most conservative.
I'd start with (c) and watch how the new field is used before
changing the headline number.

## CLI surface

### `loom extract` gains `--derives-from`

```bash
loom extract --derives-from REQ-payment-rate-limit \
             "Rate-limit the refund endpoint at 10 req/min" \
             --domain behavior
```

`--derives-from` can be repeated for multi-link citations. If
neither `--rationale` nor `--derives-from` is provided, the new
req lands as `status=rationale_needed` (with a warning printed
unless `--no-rationale` is explicitly passed).

### `loom related` (new read-only command)

```bash
loom related "rate-limit the refund endpoint" --json
# → ranked list of related existing reqs with scores + reasons
```

Used by the intake hook (next phase) but also useful standalone for
"is this already a thing we decided?"

### `loom needs-rationale` (new read-only command)

```bash
loom needs-rationale --json
# → list of reqs in status=rationale_needed
```

Purely a debt-visibility surface. Pairs with `loom stale` and
`loom doctor` as the third "what's degraded" view.

## Rendering

### `REQUIREMENTS.md` (in `src/loom/docs.py`)

Each requirement section gains a "Builds on" subsection when
`rationale_links` is non-empty:

```markdown
### REQ-refund-rate-limit [behavior]
Rate-limit the refund endpoint at 10 req/min.

**Rationale:** (none captured directly)

**Builds on:**
- REQ-payment-rate-limit (rationale: "incident 2024-09-12 — abuse via
  rapid retries; rate-limit on every payment-path endpoint")

**Linked code:**
- src/refund.py:42-78
```

For requirements with `status=rationale_needed`, a clear marker:

```markdown
### REQ-foo-bar [behavior]   ⚠ rationale_needed
Some requirement value here.

**Rationale needed.** No prose rationale captured and no
linkage to prior decisions found. Use `loom set-status REQ-foo-bar
pending` after adding `--rationale "..."` or
`--derives-from REQ-X`.
```

### Traceability matrix

Adds a "Derives from" column when any req in the project has links.

## Migration / backwards compatibility

Existing stores have:
- Reqs with `rationale_text` (or None)
- No `rationale_links`
- Status in {pending, in_progress, implemented, verified, superseded, archived}

After M11:
- New `rationale_links` field defaults to None on read (`setdefault`)
- New status `rationale_needed` is opt-in — existing reqs are NOT
  retroactively flipped into it
- `is_complete()` extension is gated on a config flag for at least
  one release
- A new helper `loom audit-rationale` can suggest reqs to flag as
  `rationale_needed` (no prose, no links) but the user opts in per-req

Net: existing stores load unchanged; the new behavior only kicks in
for new extractions or explicit retroactive flagging.

## Open questions

1. **~~Confidence threshold~~ CALIBRATED.** Pilot ran 2026-05-02
   (`experiments/pilot/rationale_linkage_pilot.py`) on a synthetic
   24-req corpus with 8 hand-labeled queries. Results: top-1
   precision 71%, **top-2 precision 100%**. Correct-match scores
   ranged 0.713–0.818; the unrelated baseline query topped at 0.600.
   **Recommended threshold: 0.66** for "include in candidate list."
   The 0.45 placeholder in earlier drafts was much too generous.
   See "Pilot Results" section below.

2. **Cycle detection.** `loom chain` already walks linkage chains
   for impl/spec/pattern relationships; the rationale-link graph
   needs the same cycle protection. Probably reuse the existing
   chain code's traversal with an added visited-set.

3. **Multi-link UX — CONFIRMED, propose top-2.** Pilot Q4
   showed the top-1 match losing by 0.003 to a near-miss when the
   query was genuinely ambiguous between two related decisions —
   so auto-linking top-1 would silently pick wrong on edge cases
   that look confident. Propose top-2 with the user choosing
   (or accepting "both" or "neither"). Top-2 precision was 100%
   on the pilot, so the user is reliably being shown the correct
   match somewhere in the pair.

4. **Transitive rationale display.** When REQ-C derives from REQ-B
   which derives from REQ-A, does REQUIREMENTS.md show only the
   direct parent or the full chain? Probably direct parent inline,
   with a "trace ancestors" command for the full chain.

5. **Migration of existing stores.** Should `loom audit-rationale`
   automatically flip rationale-less reqs into `rationale_needed`,
   or only flag them for the user to flip manually? Auto-flipping
   could surprise users with sudden visible debt; manual flagging
   creates more friction. Probably manual with a `--all-yes` escape.

## Cost estimate

| piece | LoC | risk |
|---|---|---|
| `Requirement` field + migration | ~30 | low — pattern is established |
| `services.find_related_requirements` | ~80 | medium — threshold calibration |
| `services.extract` validation extensions | ~40 | low |
| `loom related` + `loom needs-rationale` CLI | ~60 | low |
| Rendering changes in `docs.py` | ~50 | low |
| Health-score / metrics integration | ~30 | low if going with option (c) |
| Tests (mechanic-only) | ~150 | medium — calibration tests |
| **Subtotal (mechanic, no intake hook)** | **~440** | medium |
| Intake hook + classifier | ~250 | high — UX-sensitive |
| **Total (mechanic + hook)** | **~690** | mixed |

The mechanic is committable as a self-contained unit (no intake hook
needed). The intake hook depends on the mechanic but can ship later.

## Pilot Results — 2026-05-02

`experiments/pilot/rationale_linkage_pilot.py` synthesized a
24-requirement corpus drawn from Loom's domain (drift, hooks,
embeddings, indexers, runners, docs — 4 reqs each across 6
sub-domains) and ran 8 hand-labeled queries against
`services.query` to measure precision and score distribution.

| metric | value |
|---|---|
| Top-1 precision (expected = top hit) | 5/7 = 71% |
| Top-2 precision (expected in top 2) | **7/7 = 100%** |
| Correct-match score range | 0.713 — 0.818 |
| Unrelated-query score (deployment query against Loom corpus) | 0.600 |
| Min-correct vs max-unrelated separation | clean (0.713 vs 0.600) |
| Recommended threshold | **0.66** |

**Two failure modes observed (informative, not blocking):**

1. **Q1 (sub-domain disambiguation):** Query asked about
   "content-divergence drift"; expected DRF-1 (content drift),
   got DRF-4 (superseded drift) at top with DRF-1 second. Both
   are in the drift cluster — embeddings correctly clustered
   but ranked the wrong intra-cluster member top. Top-2 caught
   it.

2. **Q4 (genuine ambiguity):** Query about switching embedding
   providers. Top-1 (IDX-1, "pluggable SemanticIndexer") and
   top-2 (EMB-2, "embedding cache key includes provider") were
   separated by 0.003 — within noise. The query mentioned
   "without breaking existing search" which read more like
   indexer language than embedding-cache language. Honest
   ambiguity; top-2 caught the expected match.

**Verdict:** the mechanic works, threshold is calibrated, and
the design's "propose top-2 instead of auto-link top-1" instinct
is empirically validated.

## Recommendation

Build the mechanic with the calibrated threshold and top-2
proposal UX. Single PR shape:

> `feat(rationale): linkage data model + queries (M11.1)`
> — `Requirement.rationale_links` field, `rationale_needed` status,
> `services.find_related_requirements(text, min_score=0.66, limit=2)`,
> `loom extract --derives-from`, `loom related`,
> `loom needs-rationale`, doc rendering. ~440 LoC, day of work.

Then defer the intake hook until the mechanic has been used
in a real workflow (even our own) for a week or two, to surface
UX issues before automating.

---

# Part 2 — Detailed spec for deferred pieces (M11.2–M11.5)

**Added:** 2026-05-02 after M11.1 shipped (commit `ac42e38`).

The mechanic is in the codebase. Below is a prototype-grade
specification of the four deferred pieces, ordered by dependency.
The intake hook (M11.5) is the load-bearing one; the others
prepare the ground.

## M11.2 — REQUIREMENTS.md rendering

**Status:** straightforward. Code lives in `src/loom/docs.py`.

### Two visible changes per requirement section

When a requirement has `rationale_links`, render a "Builds on:"
subsection between the value text and the linked-code block.
Each entry includes the parent's id, value (truncated), and
inline rationale (also truncated):

```markdown
### REQ-refund-rate-limit [behavior]
Rate-limit the refund endpoint at 10 req/min.

**Rationale:** (none captured directly)

**Builds on:**
- `REQ-payment-rate-limit` — Rate-limit on every payment-path endpoint.
  *Rationale: incident 2024-09-12 — abuse via rapid retries.*

**Linked code:**
- `src/refund.py:42-78`
```

When a requirement has `status="rationale_needed"`, prepend a
visible marker to its heading and replace the rationale section
with a remediation prompt:

```markdown
### REQ-foo-bar [behavior]   ⚠ rationale_needed
Some requirement value here.

**Rationale needed.** No prose rationale captured and no linkage to
prior decisions found. To resolve: `loom set-status REQ-foo-bar
pending` after running `loom extract` again with `--rationale "..."`
or `--derives-from REQ-X`.
```

### Traceability matrix changes

The matrix at the bottom of `REQUIREMENTS.md` gains a "Derives from"
column when any req in the project has links. Empty cell when none.

### Implementation outline

1. In `docs.generate_requirements_doc`, after the existing rationale
   block, walk `req.rationale_links` and emit a "Builds on:" section.
   Helper: `_render_link_chain(store, req_ids: list[str]) -> str`
   that fetches each parent, truncates value to 80 chars, and inlines
   parent's rationale truncated to 80 chars.
2. In the per-req heading, conditionally suffix `   ⚠ rationale_needed`
   when `req.status == "rationale_needed"`.
3. Replace the rationale-section body with the remediation prompt
   when `req.status == "rationale_needed"` and rationale/links are
   both empty.
4. In the traceability matrix builder, detect whether any req has
   `rationale_links`; if so, add a "Derives from" column populated
   with the comma-separated link ids (or `—` for empty).

### Tests

- Renders "Builds on:" block when links present
- Omits "Builds on:" when links empty
- Renders ⚠ marker on `rationale_needed` requirements
- Renders remediation prompt when status is `rationale_needed`
- Traceability matrix column appears only when any req has links

### Cost

~50 LoC + 5 tests.

---

## M11.3 — Health-score integration

**Status:** design decision more than implementation. The current
4-component average (impl_coverage, test_coverage, freshness,
non_drift) doesn't reflect rationale completeness. Three options
were enumerated in Part 1; this section commits to one.

### Decision: option (a) — add a 5th equal-weighted component

```python
rationale_coverage = (
    100.0 * sum(
        1 for r in active_reqs
        if r.rationale or r.rationale_links
    ) / len(active_reqs)
)
```

Active = excludes superseded, archived, AND `rationale_needed`
reqs (since `rationale_needed` is precisely "no rationale," it
would double-count against the score otherwise — better to exclude
from the denominator and let the surface area shrink visibly).

`score = mean(impl_coverage, test_coverage, freshness, non_drift,
rationale_coverage)` rounded to int.

### Why option (a)

Option (b) — replace `non_drift` — was the most opinionated but
loses the existing drift signal. Option (c) — surface separately
without changing the headline — is the most conservative but
defeats the purpose of having a CI-gateable score: if rationale
isn't in the score, CI will silently degrade as users stop
capturing rationale.

Option (a) does change the absolute numbers — a project that was
scoring 75 before may score 60 after if rationale coverage is low.
That's the point. Document the breaking change explicitly so users
who pinned health-score thresholds in CI can re-tune.

### Implementation outline

1. In `services.health_score`, add `rationale_coverage` to the
   components dict.
2. Update the score formula to average all 5 components.
3. Update the docstring + the design comment in CLAUDE.md.
4. Add a CHANGELOG note about the score formula change.

### Tests

- New component returns 100 when every active req has rationale
- New component returns 0 when none do
- `rationale_needed` reqs are excluded from the denominator
- Score reflects 5-component average correctly

### Cost

~30 LoC + 4 tests.

---

## M11.4 — `is_complete()` extension

**Status:** breaking change for callers, gated behind a config flag.

Current:
```python
def is_complete(self) -> bool:
    return bool(
        self.elaboration
        and self.acceptance_criteria
        and len(self.acceptance_criteria) > 0
    )
```

Proposed:
```python
def is_complete(self) -> bool:
    has_rationale = bool(self.rationale or self.rationale_links)
    return bool(
        self.elaboration
        and self.acceptance_criteria
        and len(self.acceptance_criteria) > 0
        and has_rationale
    )
```

### Migration plan

1. **Phase A (one release):** add `LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=1`
   env flag. When set, `is_complete()` includes the rationale check.
   Default off — preserves current behavior. Document the flag in
   CLAUDE.md and the changelog.
2. **Phase B (next release after A):** flip default to on. Users who
   need the old behavior set
   `LOOM_REQUIRE_RATIONALE_FOR_COMPLETE=0`.
3. **Phase C (release after B):** remove the flag. `is_complete()`
   permanently includes rationale.

### Audit step

Before phase B, ship a `loom audit-rationale` command that lists
every `is_complete()=True` requirement that would become
`is_complete()=False` under the new check. Lets users plan the
migration.

### Cost

~30 LoC for is_complete extension + audit command, ~3 tests.

---

## M11.5 — Intake hook (the load-bearing prototype target)

**Status:** prototype-grade spec for a new `UserPromptSubmit` hook
that sits between the user's chat message and the agent's
response, classifies requirement-shape utterances, runs
`find_related_requirements`, and either persists with linkage,
flags as `rationale_needed`, or asks the agent to ask the user.

### Goal

Shift rationale capture from "user remembers to type
`loom extract --rationale`" to "harness intercepts and either
captures or surfaces the gap." The empirical thesis from M10.3
is that rationale is the load-bearing signal; the operational
gap is that users skip capturing it. This hook closes that gap.

### Architecture

```
                    ┌─────────────────────────────────┐
                    │  Claude Code agent              │
                    └─────────────────────────────────┘
                              ▲          │
                user message  │          │ system-reminder
                              │          ▼
        ┌────────────────────────────────────────────────┐
        │  hooks/loom_intake.py     (UserPromptSubmit)   │
        │                                                │
        │  1. classify (cheap LLM, yes/no + extract)     │
        │  2. if requirement-shape:                      │
        │       services.find_related_requirements()     │
        │  3. branch:                                    │
        │       - high-confidence linkage → extract +    │
        │         inject "captured as REQ-X derived      │
        │         from REQ-Y" reminder                   │
        │       - low-confidence       → propose top-2   │
        │         in reminder, ask agent to confirm      │
        │       - no candidates       → flag             │
        │         rationale_needed, ask agent to ask     │
        │         user                                   │
        │  4. log event to <data_dir>/.intake-log.jsonl  │
        └────────────────────────────────────────────────┘
                              │
                              ▼
                       LoomStore
```

The hook is a Python script registered via Claude Code's
`UserPromptSubmit` hook event, just like `hooks/loom_pretool.py`
is registered for `PreToolUse`. Hook fires per user message, runs
in <500ms (latency budget below), returns exit code 0 with
optional system-reminder text on stdout.

### Classifier design

#### Prompt template

```
You are a requirement-detection classifier for a software project.
The user just sent a message in a chat about the project. Decide
whether the message contains a SOFTWARE REQUIREMENT — a statement
about how the system MUST or SHOULD behave, look, or be structured.

NOT requirements:
  - Questions ("can you...", "what does...", "how do I...")
  - Code edits or fixes ("fix the bug", "make this work")
  - Style preferences without behavior implications ("use 4 spaces")
  - Commentary on the agent's work ("looks good", "try again")

ARE requirements:
  - "X must do Y when Z"
  - "We should rate-limit endpoint X"
  - "Users need to see Y before deleting"
  - "Don't ever propagate errors from the retry loop"

Output JSON only, exactly one of:

  {"is_requirement": false}

  {"is_requirement": true,
   "domain": "behavior" | "ui" | "data" | "architecture" | "terminology",
   "value": "<one-sentence requirement statement>",
   "rationale_excerpt": "<verbatim sentence from the message that
                         explains WHY, or empty string if not present>"}

User message:
\"\"\"
{user_message}
\"\"\"
```

#### Model selection

`qwen3.5:latest` — small, fast, general-purpose, ~5s p95. Loom's
existing `services._call_decomposer_llm` shape is the right call
pattern. Override via `LOOM_INTAKE_MODEL` env.

Anthropic Haiku 4.5 (`claude-haiku-4-5-20251001`) is the obvious
fallback when `ANTHROPIC_API_KEY` is set — Haiku's classification
quality is better than qwen3.5 and the latency is comparable.
Provider selection follows the existing
`services._default_decomposer_model()` pattern: anthropic if API key
present, else ollama.

#### Output parsing

```python
import json

def parse_classifier_output(content: str) -> dict | None:
    """Parse the classifier's JSON. Returns None on any parse
    failure — the hook treats unparseable output as 'not a
    requirement' (silent no-op) rather than crashing the user
    prompt path."""
    try:
        data = json.loads(content.strip().split("\n")[-1].strip())
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("is_requirement"):
        return {"is_requirement": False}
    if not data.get("domain") or not data.get("value"):
        return None
    return data
```

#### Calibration

Classifier accuracy must be measured before deploying. The
existing pilot harness shape (`experiments/pilot/`) extends
naturally:

`experiments/pilot/intake_classifier_pilot.py` — 30-50 hand-labeled
chat utterances split between "is requirement" and "is not." Run
through the classifier and measure precision/recall. Bar to ship:
**precision ≥ 90%** (false positive of "this is a requirement"
when it isn't is the worst failure mode — pollutes the store).
Recall is less critical; missing some requirements is recoverable
via `loom extract` later.

### Three-branch decision tree

After successful classification with `is_requirement=true`:

```python
candidates = services.find_related_requirements(
    store, classifier_output["value"],
    min_score=0.66,  # M11.1 calibrated default
    limit=2,
)

# Branch 1: high-confidence linkage
if candidates and candidates[0]["score"] >= 0.80:
    auto_link = [candidates[0]["req_id"]]
    if len(candidates) >= 2 and candidates[1]["score"] >= 0.78:
        auto_link.append(candidates[1]["req_id"])
    result = services.extract(
        store,
        domain=classifier_output["domain"],
        value=classifier_output["value"],
        rationale=classifier_output.get("rationale_excerpt") or None,
        rationale_links=auto_link,
        msg_id=user_msg_id,
        session=session_id,
    )
    inject_reminder(
        f"Loom captured this as {result['req_id']} derived from "
        f"{', '.join(auto_link)}. If that's wrong, run "
        f"`loom set-status {result['req_id']} archived` and re-extract."
    )

# Branch 2: low-confidence / multiple plausible candidates
elif candidates:
    proposals = "\n".join(
        f"  - {c['req_id']}: {c['value'][:80]} (score {c['score']})"
        for c in candidates
    )
    inject_reminder(
        f"Loom thinks this might be a requirement. Possible "
        f"linkages:\n{proposals}\n"
        f"In your next response, confirm which (if any) this "
        f"derives from, then run `loom extract --derives-from "
        f"REQ-X --rationale \"...\"`. If none apply, ask the "
        f"user for the rationale."
    )

# Branch 3: no candidates above threshold
else:
    if classifier_output.get("rationale_excerpt"):
        # User already said why; capture it.
        result = services.extract(
            store,
            domain=classifier_output["domain"],
            value=classifier_output["value"],
            rationale=classifier_output["rationale_excerpt"],
            msg_id=user_msg_id,
            session=session_id,
        )
        inject_reminder(
            f"Loom captured this as {result['req_id']} with the "
            f"rationale you supplied. No related prior decisions "
            f"found."
        )
    else:
        # No rationale anywhere — flag and ask agent to ask user.
        inject_reminder(
            f"Loom detected a requirement but found no rationale "
            f"or related prior decisions. Before editing, ask the "
            f"user *why* this is needed — what's the constraint, "
            f"deadline, or incident this addresses? Then run "
            f"`loom extract --rationale \"...\"`."
        )
```

### Reminder format

System-reminders are written to stdout in the format Claude Code
hooks expect. Sample shape:

```
<system-reminder source="loom-intake">
Loom captured this as REQ-abc12345 derived from REQ-payment-rate-limit
(rationale: incident 2024-09-12 — abuse via rapid retries).

If that's wrong, run `loom set-status REQ-abc12345 archived` and
re-extract with the correct linkage.
</system-reminder>
```

Reminders are kept under 500 chars to fit cleanly in the agent's
context without dominating it.

### Storage

Per-fire log at `<data_dir>/.intake-log.jsonl` parallel to
`.hook-log.jsonl`. One JSON object per line:

```json
{
  "ts": "2026-05-02T15:00:00Z",
  "session_id": "...",
  "msg_id": "...",
  "classifier_latency_ms": 380,
  "is_requirement": true,
  "branch": "auto_link" | "propose" | "no_candidates" | "no_rationale",
  "captured_req_id": "REQ-abc12345" | null,
  "candidates_top_score": 0.82,
  "candidates_count": 2,
  "rationale_source": "linked" | "prose" | "needed",
  "auto_linked_to": ["REQ-..."]
}
```

Consumed by:
- `loom intake-stats` (new command, mirrors `loom cost`) — reports
  per-day classifier accuracy, branch distribution, capture rate.
- `loom doctor` — surfaces if classifier latency p95 exceeds the
  budget.

### Telemetry / metrics this enables

- **Capture rate**: `# auto-captured + # surfaced` / `# user
  messages classified as requirements`
- **Linkage coverage**: `# auto-captured with links` / `# auto-
  captured`
- **Debt growth**: `# rationale_needed reqs created per day`
- **Classifier confidence histogram**: distribution of top-1
  scores from `find_related_requirements`

### False-positive guardrails

The biggest risk is the classifier saying "this is a requirement"
when it isn't, polluting the store with noise.

Mitigations, in order of strength:

1. **High precision threshold.** Don't ship until classifier
   precision ≥ 90% on the pilot set.
2. **Domain whitelist.** Only auto-capture for domains in
   `behavior`, `data`, `architecture`. Requirements with `domain=ui`
   or `terminology` get the propose branch (user pick) by default
   — those are noisier categories.
3. **Conflict-detection backstop.** Every auto-capture goes through
   the existing `loom conflicts --verify` LLM-verified path. If a
   high-overlap conflict is detected, downgrade from auto-capture
   to propose.
4. **Daily-budget cap.** Hard cap of N auto-captures per day per
   project (env override). Prevents runaway capture from a noisy
   classifier or a chat session full of edge cases.
5. **Reversibility surface.** The reminder always includes the
   "if that's wrong, archive it" instruction. Auto-capture is
   non-destructive — easy to roll back per req.

### Failure modes (graceful degradation)

| failure | behavior |
|---|---|
| Classifier LLM unavailable | hook silently no-ops; log entry with `error: "llm_unavailable"`; user message passes through untouched |
| Classifier returns malformed JSON | parsed as "not a requirement"; logged with `error: "parse_failed"` |
| `services.find_related_requirements` raises | log + skip the linkage step; fall through to propose-or-no-candidates branch with empty candidates |
| `services.extract` raises (e.g. cycle, dup) | log + emit reminder explaining the rejection so the user/agent can correct |
| Daily budget exceeded | log + skip auto-capture; suggest manual capture |
| Hook latency exceeds 5s timeout | the hook returns no reminder; user message passes through; logged as latency violation |

### Performance budget

| stage | target latency | hard ceiling |
|---|---|---|
| Classifier call | ≤ 500 ms p50 | 5 s |
| `find_related_requirements` | ≤ 100 ms p50 | 1 s |
| `extract` (when auto-capture) | ≤ 200 ms p50 | 2 s |
| Total per fire | ≤ 1 s p50 | 5 s |

The 5s hard ceiling matches `OLLAMA_LOAD_TIMEOUT`'s default. If
the classifier model isn't already resident in VRAM (per the M10
keep_alive fix), first-fire latency may exceed budget; warm-up
ping at hook initialization mitigates.

### Test plan

#### Unit tests (`tests/test_intake_hook.py`)

1. Classifier output parsing
   - valid `is_requirement: true` shape → returns dict
   - valid `is_requirement: false` shape → returns dict
   - malformed JSON → returns None
   - missing required fields → returns None
2. Three-branch decision logic (mocked classifier + candidates)
   - high-score candidate → auto_link branch invoked
   - mid-score candidate → propose branch invoked
   - empty candidates + rationale_excerpt → branch 3a
   - empty candidates + no rationale → branch 3b
3. False-positive guardrails
   - daily budget cap exits cleanly when reached
   - classifier-detected ui/terminology domain forced to propose
   - conflict on auto-capture downgrades to propose
4. Failure modes
   - classifier raises → no_op + log entry
   - extract raises (cycle) → reminder emitted with error message
   - latency budget violation → no_op + log entry

#### Integration test

Run the hook against a real (small) corpus with classifier set to
the deterministic-stub model. Validate end-to-end: user message →
hook fires → store updated → JSONL log entry written → reminder
emitted.

#### Manual UX validation

Two chat-style scripts (each ~20 turns) where a user is making
incremental design decisions. Run with the hook enabled. Two
human reviewers independently rate:
- Did the hook capture the right requirements? (target ≥ 90%)
- Did the hook capture noise? (target ≤ 5% of messages)
- Are the reminder messages helpful or noisy? (5-point scale,
  target mean ≥ 4)
- Is the branch choice (auto vs propose vs ask) appropriate?

### Implementation phases

| phase | scope | exit criteria |
|---|---|---|
| **P0** classifier pilot | Write `experiments/pilot/intake_classifier_pilot.py`, hand-label 30-50 utterances, measure precision/recall | Precision ≥ 90% on labeled set |
| **P1** hook scaffold | `hooks/loom_intake.py` with classifier + three-branch logic. JSONL log. Daily budget cap. Manual invocation only (no `UserPromptSubmit` registration yet). | Unit tests pass; can be invoked from CLI for testing |
| **P2** Claude Code integration | Register as `UserPromptSubmit` in `.claude/settings.json`. Document install steps. Run on 1 real chat session and inspect log. | Hook fires correctly on real session; no false positives observed |
| **P3** stats + observability | `loom intake-stats` command. Doctor integration. | Stats command useful; latency p95 within budget |
| **P4** documentation + agents.d snippet | `agents.d/intake-hook.md` describing the workflow for AGENTS.md projects. CLAUDE.md update. | Docs landed; another user can install and run |

P0 is a hard gate. If precision < 90%, iterate on the classifier
prompt (or model choice) before P1.

### Cost

| piece | LoC | risk |
|---|---|---|
| P0 classifier pilot | ~150 (harness + labeled set) | low |
| P1 hook scaffold | ~300 | medium |
| P2 Claude Code integration + settings | ~50 | low |
| P3 intake-stats + doctor | ~120 | low |
| P4 docs + agents.d snippet | ~100 | low |
| **Subtotal (intake hook)** | **~720** | medium |
| Tests | ~400 | medium |
| **Total** | **~1,120** | medium |

### Open questions

1. **Should the hook also process *agent* responses?** Sometimes
   the agent says "I'll make this validate inputs," which is a
   requirement-shape commitment. Capturing those would close
   another gap. But it's a different failure mode (agent
   hallucinations vs user intent) and probably belongs in a
   separate hook (`PreToolUse` already-ish does this for
   `Edit`/`Write`).

2. **Cross-session continuity.** When the user starts a new chat
   session about an in-flight feature, should the hook surface
   recent `rationale_needed` reqs as "you have unfinished
   business"? Probably yes, but it's a separate UX surface from
   the per-message intake.

3. **Hook ordering.** If both `loom_intake.py` (UserPromptSubmit)
   and `loom_pretool.py` (PreToolUse) are registered, the
   pretool hook could read intake's `rationale_needed` reqs
   and surface them inline. Need to verify Claude Code passes
   intake-injected reminders into the agent's context before
   pretool fires.

4. **Privacy of intake log.** `.intake-log.jsonl` will contain
   excerpts of every classified user message. That's potentially
   sensitive. Default policy: log lives under `<data_dir>` (per-
   project, local-only); never synced to a remote unless the user
   explicitly does so. Document the privacy implication.

---

## Implementation order (across all of M11)

```
M11.1 (DONE: data model + queries)
   │
   ├──── M11.2 doc rendering (independent — can ship anytime)
   ├──── M11.3 health-score (independent — can ship anytime)
   └──── M11.4 is_complete (independent — gated rollout)
            │
            ▼
       M11.5 intake hook (depends on the mechanic + benefits from
                          11.2/11.3 for visibility)
                │
                ├── P0 classifier pilot (gate)
                ├── P1 hook scaffold
                ├── P2 Claude Code integration
                ├── P3 stats / doctor
                └── P4 docs
```

11.2, 11.3, 11.4 can land in any order or in parallel. The intake
hook should land last because:
- It depends on `find_related_requirements` (11.1, done)
- It benefits from doc rendering surfacing the captured links
- It benefits from the health-score reflecting capture coverage
- The breaking `is_complete()` change should land before the hook
  starts auto-capturing reqs that may or may not pass the new check

### Recommended next prototype

**Start with P0 of M11.5** — the classifier pilot. It's the gate
that determines whether the rest of the intake hook is feasible.
~150 LoC + a few hours of hand-labeling. If it clears the 90%
precision bar, the entire M11.5 path is justified; if not, we
either iterate on the classifier or pivot to a different intake
shape (e.g. user-explicit-trigger via a slash command rather than
auto-classification).

11.2/11.3/11.4 are useful but not blocking — they can ship in
small follow-up PRs.
