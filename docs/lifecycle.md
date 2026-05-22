# Requirement Lifecycle (M15)

Source of truth for `kind=requirement` lifecycle. Other kinds
(`finding`, `methodology`, `hypothesis`, `process_rule`) keep free
`set-status` — their states model research-arc semantics that don't
map cleanly to a code-progression graph. See M15 design discussion
for the rationale.

## States

| Status              | Meaning |
|---|---|
| `pending`           | Captured; no work started. |
| `rationale_needed`  | Captured without rationale or `rationale_links` (M11.1). Visible debt. |
| `in_progress`       | At least one implementation linked. |
| `implemented`       | Linked test spec has been verified at least once. |
| `verified`          | `implemented` AND no `drift_detected` events for N days (default 14, env: `LOOM_VERIFIED_STABLE_DAYS`). |
| `superseded`        | Replaced by a later capture. Terminal. |
| `archived`          | Soft-deleted (M2.3). Recoverable via `set-status pending`. |
| `provisional`       | Intake-captured, awaiting promotion (M14.3). Hidden from REQUIREMENTS.md. |

## Transition graph

Strict. Single-hop transitions:

```
            ┌───→ rationale_needed ──┐
            ↓                         ↓
        pending ←──→ in_progress ←──→ implemented ←──→ verified
            │             │                │              │
            │             │                │              │
            └─────────────┴──────→ superseded (terminal)  │
            │             │                │              │
            └─────────────┴────────────────┴──→ archived ─┘
                                                  │
                                                  └──→ pending (recovery)
```

Edge list (also encoded in `services._REQ_TRANSITIONS`):

```python
_REQ_TRANSITIONS = {
    "pending":          {"in_progress", "rationale_needed", "superseded", "archived"},
    "rationale_needed": {"pending", "in_progress", "superseded", "archived"},
    "in_progress":      {"pending", "implemented", "superseded", "archived"},
    "implemented":      {"in_progress", "verified", "superseded", "archived"},
    "verified":         {"implemented", "superseded", "archived"},
    "archived":         {"pending"},  # M2.3 recovery
    "superseded":       set(),         # terminal
    "provisional":      {"pending", "in_progress", "rationale_needed",
                         "superseded", "archived"},  # M14.3 promotion
}
```

## Fast-forward semantics

`set_status REQ-x <target>` for kind=requirement traverses the
transition graph via BFS and applies each intermediate hop, recording
a `status_changed` event per step. If no path exists (e.g. trying to
go `superseded → in_progress`), `ValueError` is raised with the
target unreachable error.

Examples:
* `set_status REQ-x verified` from `pending`:
  applies `pending → in_progress → implemented → verified`
  (3 events written).
* `set_status REQ-x pending` from `verified`:
  applies `verified → implemented → in_progress → pending`
  (3 events written — supports the regression case).
* `set_status REQ-x pending` from `superseded`: rejected — superseded
  is terminal except for `archived` (which doesn't apply since
  superseded ≠ archived).

This keeps the graph strict (no illegal end-states) without forcing
users to step-through manually.

## Auto-advance triggers

Three hooks fire automatic transitions on `kind=requirement`. Each
records an event with `trigger=<source>` so the audit trail
distinguishes manual moves from automatic ones.

| Trigger | From | To | Where |
|---|---|---|---|
| First `loom link` | `pending` or `rationale_needed` | `in_progress` | `services.link` |
| `test_verify` records a `last_verified` | `in_progress` | `implemented` | `services.test_verify` |
| `verify_stable --apply` | `implemented` | `verified` | `services.verify_stable` |

The `verify_stable` trigger requires:
1. Current status = `implemented`
2. No `drift_detected` events on this req in the last `N` days
3. `N` defaults to 14, override via `LOOM_VERIFIED_STABLE_DAYS`

Lazy display: `loom list` and `loom status` annotate `implemented`
reqs that are eligible but not yet bumped with `(stable Nd; run
loom verify-stable --apply to promote)`.

## Manual transitions

`loom set-status REQ-x <status> [--reason "..."]`

* `--reason` is **soft-required** for manual transitions in M15.
  Missing reason emits `DeprecationWarning` and will be hard-required
  in M15.next.
* The reason is persisted to the status-changed event in
  `.loom-events.jsonl`.
* Auto-advance hooks supply their own reason via the `trigger` field;
  manual calls need explicit text.

`loom supersede REQ-x` and `loom archive REQ-x` are unaffected — they
flow through their dedicated services (which set status as a
side-effect, no reason required since the action itself is the
reason).

## Stale-pending alarms

`loom doctor` warns when any active `kind=requirement` is:
* `status == "pending"`, AND
* age (since extraction) `> 30 days`, AND
* no linked implementations.

`loom metrics` reports `pending_age` per kind:
* `p50`, `p95`, `count_over_30d`, `count_total_pending`.

## Out of scope for M15

* Lifecycle for `kind != requirement` — finding/methodology/hypothesis/
  process_rule keep free `set-status` (per D2).
* Hard-requiring `--reason` (deferred to M15.next per D6).
* `loom lifecycle REQ-x` command (reads the event log to show
  transition history) — useful but not necessary for the visible-doc
  win; deferred.

## Acceptance

After M15 ships and the backfill migration runs on the dogfooded
store, the active `kind=requirement` distribution should be **≤30%
pending**. Measure via `loom metrics`; capture before/after as a
finding.
