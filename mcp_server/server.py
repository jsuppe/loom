#!/usr/bin/env python3
"""
Loom MCP server — skeleton for Milestone 4.2.

Exposes LoomStore as typed MCP tools so Claude Code can call Loom without
shelling out to `scripts/loom`. Phase A ships read-only tools only.

Prerequisites (not wired yet):
    pip install mcp

Run standalone:
    python3 mcp_server/server.py

Register in Claude Code via .mcp.json (see repo root).

Status: SKELETON — tools are declared but handlers are TODO. The intent
is to show structure and let a follow-up PR fill in the bodies.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Mirror the sys.path trick used by scripts/loom so we can import the
# store module without installing the package.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import store  # noqa: E402  (src/store.py)
import services  # noqa: E402  (src/services.py)

# ---------------------------------------------------------------------------
# MCP imports — guarded so the file is readable without the SDK installed.
# ---------------------------------------------------------------------------
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Resource, TextContent, Tool
except ImportError:  # pragma: no cover
    print("mcp SDK not installed. Run: pip install mcp", file=sys.stderr)
    raise

app = Server("loom")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_project(project: str | None) -> str:
    """Pick project name: explicit arg > LOOM_PROJECT env > cwd git repo name.

    TODO: factor get_project_name() out of scripts/loom into src/ so both
    the CLI and MCP server share it. For now, require explicit or env.
    """
    if project:
        return project
    env = os.environ.get("LOOM_PROJECT")
    if env:
        return env
    raise ValueError(
        "No project specified. Pass `project` arg or set LOOM_PROJECT env var."
    )


def _get_store(project: str | None) -> store.LoomStore:
    return store.LoomStore(project=_resolve_project(project))


def _embed(text: str) -> list[float]:
    """Embed text via the shared `src/embedding.py` helper.

    Process-local LRU cache lives inside that module, so long-lived MCP
    sessions get real cache reuse across tool calls (unlike the CLI,
    which cold-starts each invocation).
    """
    from embedding import get_embedding  # noqa: WPS433
    return get_embedding(text)


# ---------------------------------------------------------------------------
# Tool registry — Phase A (read-only)
# ---------------------------------------------------------------------------
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="loom_query",
            description="Semantic search over requirements in the Loom store.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "project": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="loom_list",
            description="List requirements. Filter by status if given.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "implemented",
                                "verified", "superseded"],
                    },
                    "include_superseded": {"type": "boolean", "default": False},
                },
            },
        ),
        Tool(
            name="loom_status",
            description="Project overview: requirement counts, drift summary.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string"}},
            },
        ),
        Tool(
            name="loom_trace",
            description=(
                "Bidirectional traceability. `target` is either a REQ-id "
                "(returns linked files) or a file path (returns linked reqs)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["target"],
            },
        ),
        Tool(
            name="loom_chain",
            description="Full traceability chain for a requirement: "
                        "req → patterns → specs → impls → tests.",
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["req_id"],
            },
        ),
        Tool(
            name="loom_coverage",
            description="Three-layer coverage gap analysis "
                        "(req→spec, spec→impl, spec→test).",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string"}},
            },
        ),
        Tool(
            name="loom_doctor",
            description="Health checks: Ollama, store, orphans, drift, coverage.",
            inputSchema={
                "type": "object",
                "properties": {"project": {"type": "string"}},
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to handler functions.

    Each handler returns a dict; we serialize to JSON text content.
    TODO: implement handlers. Each should be a thin wrapper over LoomStore
    methods — do NOT reimplement logic that already lives in scripts/loom.
    The correct move is to factor cmd_* bodies into callable functions in
    src/ and have both the CLI and these handlers invoke them.
    """
    import json

    handlers = {
        "loom_query": _handle_query,
        "loom_list": _handle_list,
        "loom_status": _handle_status,
        "loom_trace": _handle_trace,
        "loom_chain": _handle_chain,
        "loom_coverage": _handle_coverage,
        "loom_doctor": _handle_doctor,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    result = await handler(arguments)
    return [TextContent(type="text", text=json.dumps(result, default=str))]


# ---------------------------------------------------------------------------
# Handlers — stubs, to be filled in when 4.2 lands.
# ---------------------------------------------------------------------------
async def _handle_query(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    results = services.query(s, args["text"], limit=args.get("limit", 5))
    return {"results": results}


async def _handle_list(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    reqs = services.list_requirements(
        s, include_superseded=args.get("include_superseded", False)
    )
    # Optional post-filter by status — kept here because the CLI doesn't
    # need it but MCP clients asked for it in the tool schema.
    if status_filter := args.get("status"):
        reqs = [r for r in reqs if r["status"] == status_filter]
    return {"requirements": reqs}


async def _handle_status(args: dict[str, Any]) -> dict:
    return services.status(_get_store(args.get("project")))


async def _handle_trace(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.trace(s, args["target"])
    except LookupError as e:
        return {"error": str(e)}


async def _handle_chain(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.chain(s, args["req_id"])
    except LookupError as e:
        return {"error": str(e)}


async def _handle_coverage(args: dict[str, Any]) -> dict:
    return services.coverage(_get_store(args.get("project")))


async def _handle_doctor(args: dict[str, Any]) -> dict:
    return services.doctor(_get_store(args.get("project")))


# ---------------------------------------------------------------------------
# Resources — live views of generated docs and drift.
# ---------------------------------------------------------------------------
@app.list_resources()
async def list_resources() -> list[Resource]:
    # TODO: enumerate known projects from ~/.openclaw/loom/ and expose one
    # resource per project per doc. For now, return an empty list; resources
    # land alongside the write tools in Phase B.
    return []


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
