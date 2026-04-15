# Loom MCP Server (skeleton)

Thin MCP server that exposes `LoomStore` operations as typed tools to Claude
Code and other MCP-compatible clients. Status: **skeleton** — structure and
tool schemas are in place; handlers are TODO.

See `ROADMAP.md` → Milestone 4.2 for the design.

## Prerequisite refactors

Before filling in the handlers, two things should be factored out of
`scripts/loom` into `src/`:

1. ~~**`get_embedding()`** → `src/embedding.py`~~ — **DONE.** The MCP
   server now imports from `embedding` directly.
2. **`cmd_*` function bodies** → `src/services.py`. **In progress.** The
   CLI's `cmd_*` functions mix argparse handling with real logic. We're
   splitting them so MCP handlers can call shared functions without
   re-parsing args or rendering strings.

   **Done:** all CLI verbs are now services (`status`, `query`,
   `list_requirements`, `trace`, `chain`, `coverage`, `doctor`,
   `conflicts`, `extract`, `check`, `link`, `detect_requirements`,
   `sync`, `supersede`, `set_status`, `refine`, `spec_add`/`spec_list`/
   `spec_link`, `pattern_add`/`pattern_list`/`pattern_apply`,
   `test_add`/`test_verify`/`test_list`/`test_generate`, `incomplete`).
   Their `cmd_*` counterparts in `scripts/loom` are thin wrappers over
   `services.py`.

Each MCP handler should collapse to 2-3 lines once its service exists.

## Installing

```bash
pip install mcp
```

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

Phase B is complete. Only `init-private` remains CLI-only (it
writes a template file — not appropriate as an MCP tool).

## Resources (planned)

- `loom://requirements/{project}`
- `loom://testspec/{project}`
- `loom://drift/{project}`
