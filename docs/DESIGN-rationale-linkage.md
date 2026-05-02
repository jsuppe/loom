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
