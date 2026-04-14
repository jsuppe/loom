# Loom MCP Server (skeleton)

Thin MCP server that exposes `LoomStore` operations as typed tools to Claude
Code and other MCP-compatible clients. Status: **skeleton** — structure and
tool schemas are in place; handlers are TODO.

See `ROADMAP.md` → Milestone 4.2 for the design.

## Prerequisite refactors

Before filling in the handlers, two things should be factored out of
`scripts/loom` into `src/`:

1. **`get_embedding()`** → `src/embedding.py`. Currently lives in the CLI
   script with its LRU cache. The MCP server needs it too, and duplicating
   it would mean two caches out of sync.
2. **`cmd_*` function bodies** → shared callables in `src/`. The CLI's
   `cmd_status`, `cmd_trace`, `cmd_chain`, `cmd_coverage`, `cmd_doctor` all
   mix argparse handling with real logic. Split them so the MCP handlers
   can call the same functions without re-parsing args.

Once those land, each MCP handler becomes a 2-3 line wrapper.

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

## Phase A tools (read-only)

- `loom_query` — semantic search
- `loom_list` — list requirements
- `loom_status` — project overview
- `loom_trace` — bidirectional traceability
- `loom_chain` — full req→specs→impls→tests chain
- `loom_coverage` — gap analysis
- `loom_doctor` — health checks

## Phase B tools (write, planned)

- `loom_extract`, `loom_link`, `loom_check`, `loom_spec_create`,
  `loom_supersede`, `loom_sync`

## Resources (planned)

- `loom://requirements/{project}`
- `loom://testspec/{project}`
- `loom://drift/{project}`
