# Context bundle for TASK-gaps-1

This is what the *enhanced* condition receives in addition to the task
description. It pre-assembles the Loom artifacts (reqs, spec, relevant
sidecar) the agent would otherwise have to discover.

---

## Requirements

### REQ-gaps-1 [behavior]

**Value.** A `loom gaps` command surfaces outstanding gaps across the project,
ordered by what blocks execution progress.

**Rationale.** Without a single inventory, users re-derive state from
`loom incomplete` + `loom doctor` + `loom trace` every session.

**Acceptance criteria.**
- Returns all gaps for active (non-superseded) reqs by default
- Supports `--type T` (repeatable) for filtering by gap category
- Supports `--json`
- Supports `--limit N`
- Exit code 2 if any `unresolved_conflict` or `drift` gap exists

### REQ-gaps-2 [data]

**Value.** Each gap has a uniform shape:
`{type, entity_id, description, blocks, suggested_action}`.

**Rationale.** Uniform shape lets agents process gap lists without branching
per-field. Matches the contract `services.*` functions follow.

**Acceptance criteria.**
- Every returned gap has all five fields populated (no `None`)
- `blocks` is always a `list` (possibly empty)
- `suggested_action` is a single runnable command string

### REQ-gaps-3 [behavior]

**Value.** Gaps are ordered by what they block (execution > planning > docs).

**Rationale.** When an agent or user has limited turns, highest-leverage
gaps surface first.

**Acceptance criteria.**
- Returned list is sorted by priority, ties by `entity_id`

---

## Specification

### SPEC-gaps-1 [parent: REQ-gaps-1, REQ-gaps-2, REQ-gaps-3]

**Signature.** `services.gaps(store, types=None, limit=None) -> list[dict]`

**Gap types (priority order, highest first).**

| Priority | Type                  | Meaning                                                     |
|----------|-----------------------|-------------------------------------------------------------|
| 1        | `unresolved_conflict` | Two active reqs flagged as contradictory, neither superseded (future task) |
| 2        | `drift`               | Superseded req with active linked impls (future task)       |
| 3        | `missing_criteria`    | Active req with empty `acceptance_criteria`                 |
| 4        | `missing_spec`        | Active req with criteria but no Specification linked (future task) |
| 5        | `missing_elaboration` | Active req with empty `elaboration`                         |
| 6        | `orphan_impl`         | Implementation with no live `req_id` (all missing/superseded) |

**Filtering and limits.**
- `types=None` → all types; otherwise only the listed types
- `limit=None` → unlimited; otherwise cap at N after sorting
- Superseded reqs are silently skipped for `missing_criteria` /
  `missing_elaboration` (they're not actionable gaps).

**Deterministic ordering.** Sort key is `(priority, entity_id)`. Same input
always yields same output order.

---

## Sidecar excerpt: `src/services.py`

*(The full sidecar lives at `src/services.loom.md`. This is the TL;DR block
the hook would inject.)*

### Hard rules (do not break)

1. **No side-effects on output paths.** Never print, log to stdout, or call
   `sys.exit`. Debug lives in the caller or in `embedding.py`.
2. **`LookupError` for target-not-found.** Raised when the caller asked for
   `REQ-xyz` and it doesn't exist. Not `ValueError`, not `None`.
3. **`ValueError` for caller-prevented errors.** Bad shape, unknown status
   string, malformed lines spec. Programmer errors the caller could catch.
4. **Write services return warnings.** On partial failure, return
   `{linked: True, warnings: [...]}` rather than raising.
5. **Never raise for "empty result."** Empty store → `[]`, not exception.
6. **Deterministic ordering.** Every list output is sorted by a stable key
   (usually `entity_id`). Tests depend on this.

### ChromaDB metadata gotchas

- Empty lists are rejected by the metadata validator, so dataclasses
  substitute `["TBD"]` in `to_dict`. When reading back, treat `["TBD"]` as
  "unset".
- `from_dict` uses `setdefault` for newly-added fields — this is how older
  stores keep loading after schema additions.

### Common patterns

- Read one req: `store.get_requirement(id)` → `Requirement | None`.
- Read one impl: `store.get_implementation(id)` → `Implementation | None`.
- Iterate all reqs: `store.requirements.get(include=["metadatas"])` and
  iterate `ids` / `metadatas` arrays in parallel.
- Add an impl: pre-generate its id via `generate_impl_id(file, lines)`.
- Check superseded: `req.superseded_at is not None`.

### Performance invariants

- Prefer `store.<collection>.get(where={...})` to a full scan + Python
  filter — the benchmark caught a 340× regression on `context()` when a
  prior version iterated everything in Python.
- `status()` must not call `get_implementations_for_requirement` in a loop;
  build an index once, reuse.

### Completeness check for reqs

`Requirement.is_complete()` returns `True` when the req has non-empty
elaboration **and** at least one acceptance criterion.  "Non-empty" means
not `""`, not `["TBD"]` (the ChromaDB empty-list sentinel), not `[]`.
This same definition drives `missing_criteria` / `missing_elaboration`
gap detection.

### Implementation.satisfies shape

`Implementation.satisfies` is a list of dicts like
`[{"req_id": "REQ-abc"}, {"req_id": "REQ-def"}]`. In ChromaDB metadata it
is stored JSON-serialized under key `satisfies`. When reading an impl back,
parse with `json.loads(meta["satisfies"])`.

### Related services

- `services.incomplete(store)` — returns active reqs missing elaboration or
  criteria. Overlaps with `missing_criteria` / `missing_elaboration` but
  returns a different shape. The new `gaps()` is the uniform-shape
  replacement; `incomplete()` stays for backward compat.
- `services.conflicts(store, text)` — detects conflicting reqs given a
  proposed new text. Will be used by a later task to implement
  `unresolved_conflict` gap detection (not this task).
