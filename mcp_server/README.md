# Loom MCP Server

Thin MCP server that exposes `LoomStore` operations as typed tools to
Claude Code and other MCP-compatible clients. Phase A (read) and Phase
B (write) tools are shipped; handlers all delegate to
`loom.services.*` so the CLI and MCP surfaces stay in lockstep.

See `ROADMAP.md` → Milestone 4.2 for the design.

## Installing

```bash
pip install 'loom-cli[mcp]'
# Or, from a clone in dev mode:
pip install -e '.[mcp]'
```

The `[mcp]` extra pulls in the `mcp` Python SDK alongside the core
package.

## Running standalone (for testing)

```bash
LOOM_PROJECT=myproject python3 mcp_server/server.py
```

The server speaks stdio MCP, so it expects a client on the other end.

## Registering with Claude Code

Add to `.mcp.json` in the repo root:

```json
{
  "mcpServers": {
    "loom": {
      "command": "python3",
      "args": ["mcp_server/server.py"],
      "env": {"LOOM_PROJECT": "loom"}
    }
  }
}
```

## Phase A tools (read-only) — shipped

- `loom_query` — semantic search
- `loom_list` — list requirements
- `loom_status` — project overview
- `loom_trace` — bidirectional traceability
- `loom_chain` — full req→specs→impls→tests chain
- `loom_coverage` — gap analysis
- `loom_doctor` — health checks

## Phase B tools — shipped

Requirement-level:
- `loom_extract` — add a requirement (returns conflicts if any)
- `loom_check` — drift check for a file
- `loom_link` — link a file to req(s) and/or spec(s)
- `loom_conflicts` — read-only conflict probe (does NOT add)
- `loom_sync` — regenerate REQUIREMENTS.md and TEST_SPEC.md
- `loom_supersede` — mark a requirement as superseded
- `loom_set_status` — set req status (pending/in_progress/...)
- `loom_refine` — elaborate a req with criteria, context, status
- `loom_incomplete` — list reqs missing elaboration/criteria

Specifications:
- `loom_spec_add`, `loom_spec_list`, `loom_spec_link`

Patterns:
- `loom_pattern_add`, `loom_pattern_list`, `loom_pattern_apply`

Test specs:
- `loom_test_add`, `loom_test_verify`, `loom_test_list`,
  `loom_test_generate`

Phase B is complete. CLI-only verbs (no MCP exposure):
- `init-private` — writes a template file; not appropriate as an MCP tool
- `archive`, `stale`, `metrics`, `health-score`, `cost` — added in v1
  (M2 / M5); MCP coverage TBD as a follow-up if there's demand. The
  underlying services (`services.archive`, `services.stale`,
  `services.metrics`, `services.health_score`) already return
  JSON-shape data, so wiring them up is one handler each.

## Resources (planned)

- `loom://requirements/{project}`
- `loom://testspec/{project}`
- `loom://drift/{project}`
