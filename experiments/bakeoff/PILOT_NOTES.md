# Pilot notes (2026-04-24)

**Per PROTOCOL.md: pilot results do NOT count toward the real
experiment.** This file documents what the pilot runs surfaced so the
harness fixes are on the record.

## What the pilot caught

### Bug 1 — Parser wrong for `pytest -q` format
Fixed. `pytest -q` puts status first (`FAILED tests/...`); `pytest -v`
puts it last (`tests/... FAILED`). Switched to `-v` with a regex that
tolerates trailing percent markers.

### Bug 2 — Tool errors crashed the driver
Fixed. `ToolError` now caught and returned as
`{"ok": False, "error": ...}` so the engineer can recover (e.g. when
they try to read `tests/`).

### Bug 3 — `no_progress` window too aggressive
Fixed. Window was 3 (stop after 3 same-pass iterations); bumped to 5.
Reqs on this project cross-cut, so plateauing briefly is normal
mid-feature.

### Bug 4 — `collection_error` invisible to PO
Fixed. If pytest fails to import the implementation module (e.g. the
engineer named the class `Queue` instead of `TaskQueue`), pytest exits
with `rc != 0` and 0 tests collected. The old harness just reported
"0/0 passing" forever, leaving the PO confused. Now surfaces the
actual `ImportError` / `SyntaxError` / `AttributeError` in the
PO-facing summary so the PO can route the engineer to fix it.

### Bug 5 — `loom_tool_calls` never populated
Fixed. Metrics initialized the dict but nothing incremented it.
Wired through the engineer_turn tool dispatcher.

### Observation — PO needs per-class feedback, not just totals
Fixed. `_format_test_results` now groups by test class (which maps
to requirement area) so the PO can see "[TestAdd] 1/3" rather than
just "1/15 total." Also helps the PO know when a requirement is
"done enough" given that some REQ-1 tests depend on REQ-3 / REQ-6
features.

### Observation — PO got confused mid-requirement when tests can't all pass yet
Fixed (prompt edit). PO prompt now explicitly tells the PO that some
tests for REQ-N may legitimately fail until REQ-(N+k) is implemented,
and to advance when the engineer has made good-faith progress on
what was asked.

## Pilot data (NOT real; N=1 per condition)

| | final_pass_rate | iters | total_tokens |
|---|:---:|:---:|:---:|
| baseline | 1.00 | 6 | 25,696 |
| loom | 0.53 | 13 | 119,851 |

The pilot data suggests the experiment CAN produce outcomes that differ
by condition. Whether the true direction is positive, negative, or null
requires the full N=5 real run. Single pilots are noise.

Notably: the Loom pilot burned 4.7× more tokens than baseline to reach
a LOWER pass rate. If this direction holds in the real runs, it's a
critical finding — Loom overhead could outweigh its structural value
on projects small enough that context bundles aren't load-bearing.
Or it could be pilot noise. N=5 will tell.

## No amendments to PROTOCOL.md

All changes above were to the harness, not the protocol. The metrics,
stop conditions, sample size, and statistical plan remain exactly as
pre-registered.
