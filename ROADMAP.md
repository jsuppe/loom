# Loom Roadmap

## Milestone 1: CLI Foundations (DONE)

Make Loom reliable for tool use by AI agents.

- [x] **1.1 Portable shebang** — `#!/usr/bin/env python3`
- [x] **1.2 `--json` output** — 11 commands now support `--json` / `-j`
- [x] **1.3 Exit codes** — 0=success, 1=error, 2=drift/conflicts
- [x] **1.4 `rationale` field** — `--rationale` on `extract`, included in docs and JSON
- [x] **1.5 Implementation links in docs** — REQUIREMENTS.md shows linked files, drift warnings, traceability matrix; TEST_SPEC.md shows covered/uncovered code

## Milestone 2: Requirement Hygiene

Surface staleness without automatic deletion. Requirements are decisions — Loom should help users review and decide, never silently delete.

- [ ] **2.1 `last_referenced` timestamp** — Track when a requirement was last touched by `query`, `check`, `link`, `trace`, or `chain`. `setdefault` to `None` for backward compat.
- [ ] **2.2 `loom stale` command** — List requirements sorted by staleness. Flags: `--older-than 90d`, `--unlinked`. Read-only, `--json` from day one.
- [ ] **2.3 `loom archive` command** — New `archived` status (distinct from `superseded`). Excluded from `list`, `query`, `conflicts` by default. Recoverable via `loom set-status REQ-xxx pending`.
- [ ] **2.4 `loom review` (optional)** — Interactive walkthrough of stale requirements: keep / archive / supersede / skip. Non-interactive equivalent: `loom stale --json` + explicit commands.

Design principle: **surface, don't delete.**
1. `last_referenced` tracks activity passively (zero effort)
2. `loom stale` shows what's cold (read-only, safe)
3. User/agent decides: keep, archive, or supersede (explicit action)

## Milestone 3: Pluggable Embeddings

Remove hard dependency on local Ollama.

- [ ] **3.1 Provider interface** — Abstract `get_embedding()` to support `ollama` (default), `openai` (via `OPENAI_API_KEY`), and `hash` (deterministic fallback). Selection via `LOOM_EMBEDDING_PROVIDER` env var or `--embedding-provider` flag. Config stored in `.loom-config.json` per project.
- [ ] **3.2 Dimension validation** — Record embedding dimensions on first use. Reject mismatched dimensions with a clear error on subsequent calls.

## Milestone 4: Claude Code Integration (PARTIAL)

First-class tool integration with Claude Code sessions.

- [x] **4.1 Hooks** — `.claude/settings.json` with SessionStart (doctor + status), PostToolUse on Edit/Write (drift check), PostToolUse on Bash git commit (sync docs).
- [ ] **4.2 MCP server** — Thin Python MCP server (~200-300 lines) wrapping core verbs (`extract`, `query`, `check`, `link`, `status`, `sync`, `stale`) as typed MCP tools. Gives Claude Code structured schemas instead of Bash string parsing.

## Milestone 5: Metrics & Effectiveness Measurement

Track whether Loom is actually helping. Without measurement, you can't tell if the token cost is justified.

### 5.1 Event log

Append-only JSON log at `~/.openclaw/loom/<project>/.loom-events.json`. Each entry:

```json
{"event": "drift_detected", "file": "src/auth.py", "req_id": "REQ-042", "timestamp": "..."}
{"event": "conflict_found", "new_text": "...", "existing_id": "REQ-015", "timestamp": "..."}
{"event": "requirement_extracted", "req_id": "REQ-043", "domain": "behavior", "timestamp": "..."}
{"event": "implementation_linked", "file": "src/auth.py", "req_id": "REQ-043", "timestamp": "..."}
{"event": "check_clean", "file": "src/auth.py", "timestamp": "..."}
```

Events logged by existing commands — `check`, `conflicts`, `extract`, `link` — with a one-line append per action. No new dependencies.

### 5.2 `loom metrics` command

Reads the event log and reports effectiveness:

```
loom metrics -p myproject
loom metrics -p myproject --json
loom metrics -p myproject --since 30d
```

Output:
- **Requirements:** total extracted, active, archived, superseded
- **Coverage:** requirements with implementations / total, requirements with test specs / total
- **Drift:** times drift was detected, files affected, avg time from supersede to detection
- **Conflicts:** conflicts caught before implementation
- **Activity:** requirements extracted per week, links created per week
- **Staleness:** requirements with no references in 30/60/90 days

### 5.3 `loom health-score`

Single 0-100 score combining:
- Implementation coverage (% of reqs with linked code)
- Test spec coverage (% of reqs with test specs)
- Freshness (% of reqs referenced in last 90 days)
- Drift ratio (% of implementations not drifted)

Useful for CI gates or status dashboards:

```bash
SCORE=$(loom health-score -p myproject --json | jq '.score')
[ "$SCORE" -lt 50 ] && echo "Requirements health is degrading"
```

## Dependency Graph

```
Milestone 1 (DONE)
       │
       ├──────────────────────────┐
       ▼                          ▼
Milestone 2 (Hygiene)    Milestone 3 (Embeddings)
       │                          │
       ▼                          ▼
Milestone 4 (Integration) ◄──────┘
       │
       ▼
Milestone 5 (Metrics)
  5.1 Event log (needs extract/check/link/conflicts to log events)
  5.2 loom metrics (needs event log)
  5.3 loom health-score (needs metrics + coverage data)
```

Milestones 2 and 3 are independent and can run in parallel. Milestone 5 depends on Milestone 1 (JSON output) and benefits from 2 (staleness data feeds metrics).
