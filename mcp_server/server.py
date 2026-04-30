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

from loom import store  # noqa: E402  (src/store.py)
from loom import services  # noqa: E402  (src/services.py)

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
    from loom.embedding import get_embedding  # noqa: WPS433
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
        # ----- Phase B: write tools -----
        # MCP clients should treat these as side-effecting; Claude Code
        # asks the user to approve each call by default.
        Tool(
            name="loom_extract",
            description=(
                "Add a requirement to the store. Returns the new req_id "
                "and any conflicts detected against existing requirements "
                "(the requirement is added regardless)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "enum": ["terminology", "behavior", "ui", "data", "architecture"],
                    },
                    "value": {"type": "string", "description": "Requirement text"},
                    "rationale": {"type": "string", "description": "Why this requirement exists"},
                    "project": {"type": "string"},
                },
                "required": ["domain", "value"],
            },
        ),
        Tool(
            name="loom_context",
            description=(
                "Pre-edit briefing for a file. Returns every requirement "
                "and specification linked to any implementation at that "
                "path, plus a drift flag and a one-line summary suitable "
                "for a system-reminder. Broader than loom_check — matches "
                "by file path, not by exact line range."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="loom_check",
            description=(
                "Check whether a file (or line range) has drifted from "
                "its linked requirements. Returns drift status and the "
                "list of linked requirements."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "lines": {
                        "type": "string",
                        "description": "Line range like '42-78' (optional)",
                    },
                    "project": {"type": "string"},
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="loom_link",
            description=(
                "Link a file (or line range) to one or more requirements "
                "and/or specifications. Provide req_ids, spec_ids, or both. "
                "If neither is provided, returns an error — use the "
                "loom_query tool first to find candidates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "lines": {"type": "string"},
                    "req_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "spec_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "project": {"type": "string"},
                },
                "required": ["file"],
            },
        ),
        Tool(
            name="loom_conflicts",
            description=(
                "Check whether a candidate requirement text would conflict "
                "with existing requirements. Read-only — does NOT add the "
                "requirement. Pass `text` as 'domain | requirement text' "
                "(or just the text; defaults to 'behavior' domain). Set "
                "`verify=true` to run an LLM verifier over the candidate "
                "pool — higher precision + catches logic-only contradictions, "
                "but adds ~1s of latency per check."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "project": {"type": "string"},
                    "verify": {
                        "type": "boolean",
                        "default": False,
                        "description": "Run LLM verifier (requires Ollama).",
                    },
                    "verify_model": {
                        "type": "string",
                        "description": (
                            "Ollama model name for verification "
                            "(default: qwen3.5:latest)."
                        ),
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="loom_sync",
            description=(
                "Regenerate REQUIREMENTS.md and TEST_SPEC.md from the store. "
                "Writes to `output_dir` (defaults to project's docs/ if omitted). "
                "`public=true` filters out IDs listed in PRIVATE.md."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to write the markdown files to",
                    },
                    "public": {
                        "type": "boolean",
                        "default": False,
                        "description": "Exclude private requirements",
                    },
                    "project": {"type": "string"},
                },
                "required": ["output_dir"],
            },
        ),
        Tool(
            name="loom_supersede",
            description=(
                "Mark a requirement as superseded. Returns the affected "
                "test spec ids so the caller can prompt for follow-up."
            ),
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
            name="loom_set_status",
            description=(
                "Set a requirement's implementation status: pending, "
                "in_progress, implemented, verified, superseded."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "implemented",
                                 "verified", "superseded"],
                    },
                    "project": {"type": "string"},
                },
                "required": ["req_id", "status"],
            },
        ),
        Tool(
            name="loom_refine",
            description=(
                "Elaborate a requirement: add elaboration text, optional "
                "acceptance criteria, conversation context, and/or status. "
                "`elaboration` is required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "elaboration": {"type": "string"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "conversation_context": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "implemented",
                                 "verified", "superseded"],
                    },
                    "project": {"type": "string"},
                },
                "required": ["req_id", "elaboration"],
            },
        ),
        # ----- Entity CRUD: specifications -----
        Tool(
            name="loom_spec_add",
            description=(
                "Add a specification describing HOW to implement a parent "
                "requirement. Returns the new SPEC-id."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string", "description": "Parent requirement ID"},
                    "description": {"type": "string"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "status": {
                        "type": "string",
                        "enum": ["draft", "approved", "implemented", "verified"],
                        "default": "draft",
                    },
                    "source_doc": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["req_id", "description"],
            },
        ),
        Tool(
            name="loom_spec_list",
            description="List specifications (optionally filtered by parent req).",
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string", "description": "Filter by parent req"},
                    "include_superseded": {"type": "boolean", "default": False},
                    "project": {"type": "string"},
                },
            },
        ),
        Tool(
            name="loom_spec_link",
            description=(
                "Link a file (or line range) to a specification. If an "
                "Implementation already exists at this location it's "
                "attached to the spec; otherwise a new one is created."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "spec_id": {"type": "string"},
                    "file": {"type": "string"},
                    "lines": {"type": "string"},
                    "project": {"type": "string"},
                },
                "required": ["spec_id", "file"],
            },
        ),
        # ----- Entity CRUD: patterns -----
        Tool(
            name="loom_pattern_add",
            description=(
                "Add a shared design pattern that applies to multiple "
                "requirements."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "applies_to": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of REQ-ids this pattern applies to",
                    },
                    "project": {"type": "string"},
                },
                "required": ["name", "description"],
            },
        ),
        Tool(
            name="loom_pattern_list",
            description="List design patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_deprecated": {"type": "boolean", "default": False},
                    "project": {"type": "string"},
                },
            },
        ),
        Tool(
            name="loom_pattern_apply",
            description="Attach a pattern to additional requirements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern_id": {"type": "string"},
                    "req_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "project": {"type": "string"},
                },
                "required": ["pattern_id", "req_ids"],
            },
        ),
        # ----- Entity CRUD: test specs -----
        Tool(
            name="loom_test_add",
            description=(
                "Add or update a TestSpec for a requirement. Fields not "
                "supplied inherit from an existing TestSpec if one exists."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "description": {"type": "string"},
                    "steps": {"type": "array", "items": {"type": "string"}},
                    "expected": {"type": "string"},
                    "automated": {"type": "boolean", "default": False},
                    "test_file": {"type": "string"},
                    "private": {"type": "boolean", "default": False},
                    "project": {"type": "string"},
                },
                "required": ["req_id"],
            },
        ),
        Tool(
            name="loom_test_verify",
            description="Mark a test as verified.",
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
            name="loom_test_list",
            description="List test specifications.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_private": {"type": "boolean", "default": True},
                    "project": {"type": "string"},
                },
            },
        ),
        Tool(
            name="loom_test_generate",
            description=(
                "Auto-generate TestSpecs from requirements' acceptance "
                "criteria. Skips reqs with existing test specs unless "
                "force=true."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "force": {"type": "boolean", "default": False},
                    "project": {"type": "string"},
                },
            },
        ),
        # ----- Misc -----
        Tool(
            name="loom_incomplete",
            description=(
                "List requirements missing elaboration or acceptance "
                "criteria. Read-only."
            ),
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
        "loom_extract": _handle_extract,
        "loom_context": _handle_context,
        "loom_check": _handle_check,
        "loom_link": _handle_link,
        "loom_conflicts": _handle_conflicts,
        "loom_sync": _handle_sync,
        "loom_supersede": _handle_supersede,
        "loom_set_status": _handle_set_status,
        "loom_refine": _handle_refine,
        "loom_spec_add": _handle_spec_add,
        "loom_spec_list": _handle_spec_list,
        "loom_spec_link": _handle_spec_link,
        "loom_pattern_add": _handle_pattern_add,
        "loom_pattern_list": _handle_pattern_list,
        "loom_pattern_apply": _handle_pattern_apply,
        "loom_test_add": _handle_test_add,
        "loom_test_verify": _handle_test_verify,
        "loom_test_list": _handle_test_list,
        "loom_test_generate": _handle_test_generate,
        "loom_incomplete": _handle_incomplete,
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


# ----- Phase B: write tool handlers -----

async def _handle_extract(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return services.extract(
        s,
        domain=args["domain"],
        value=args["value"],
        rationale=args.get("rationale"),
        msg_id=args.get("msg_id", "mcp"),
        session=args.get("session", "mcp"),
    )


async def _handle_context(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.context(s, args["file"])
    except LookupError as e:
        return {"error": str(e)}


async def _handle_check(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.check(s, args["file"], lines=args.get("lines"))
    except LookupError as e:
        return {"error": str(e)}


async def _handle_link(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.link(
            s, args["file"],
            lines=args.get("lines"),
            req_ids=args.get("req_ids", []),
            spec_ids=args.get("spec_ids", []),
        )
    except LookupError as e:
        return {"error": str(e)}


async def _handle_conflicts(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        found = services.conflicts(
            s, args["text"],
            verify=args.get("verify", False),
            verify_model=args.get("verify_model"),
        )
    except RuntimeError as e:
        return {"error": str(e)}
    return {
        "conflicts_found": len(found) > 0,
        "count": len(found),
        "conflicts": found,
    }


async def _handle_sync(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return services.sync(s, args["output_dir"], public=args.get("public", False))


async def _handle_supersede(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.supersede(s, args["req_id"])
    except (LookupError, ValueError) as e:
        return {"error": str(e)}


async def _handle_set_status(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.set_status(s, args["req_id"], args["status"])
    except (LookupError, ValueError) as e:
        return {"error": str(e)}


async def _handle_refine(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.refine(
            s, args["req_id"],
            elaboration=args["elaboration"],
            acceptance_criteria=args.get("acceptance_criteria"),
            conversation_context=args.get("conversation_context"),
            status=args.get("status"),
        )
    except (LookupError, ValueError) as e:
        return {"error": str(e)}


# ----- Entity CRUD handlers -----

async def _handle_spec_add(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.spec_add(
            s, args["req_id"], args["description"],
            acceptance_criteria=args.get("acceptance_criteria"),
            status=args.get("status", "draft"),
            source_doc=args.get("source_doc"),
        )
    except (LookupError, ValueError) as e:
        return {"error": str(e)}


async def _handle_spec_list(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return {
        "specifications": services.spec_list(
            s,
            req_id=args.get("req_id"),
            include_superseded=args.get("include_superseded", False),
        )
    }


async def _handle_spec_link(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.spec_link(
            s, args["spec_id"], args["file"], lines=args.get("lines")
        )
    except LookupError as e:
        return {"error": str(e)}


async def _handle_pattern_add(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.pattern_add(
            s, args["name"], args["description"],
            applies_to=args.get("applies_to", []),
        )
    except ValueError as e:
        return {"error": str(e)}


async def _handle_pattern_list(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return {
        "patterns": services.pattern_list(
            s, include_deprecated=args.get("include_deprecated", False)
        )
    }


async def _handle_pattern_apply(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.pattern_apply(s, args["pattern_id"], args["req_ids"])
    except LookupError as e:
        return {"error": str(e)}


async def _handle_test_add(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.test_add(
            s, args["req_id"],
            description=args.get("description"),
            steps=args.get("steps", ()),
            expected=args.get("expected"),
            automated=args.get("automated", False),
            test_file=args.get("test_file"),
            private=args.get("private", False),
        )
    except (LookupError, ValueError) as e:
        return {"error": str(e)}


async def _handle_test_verify(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    try:
        return services.test_verify(s, args["req_id"])
    except LookupError as e:
        return {"error": str(e)}


async def _handle_test_list(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return {
        "tests": services.test_list(
            s, include_private=args.get("include_private", True)
        )
    }


async def _handle_test_generate(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return services.test_generate(s, force=args.get("force", False))


async def _handle_incomplete(args: dict[str, Any]) -> dict:
    s = _get_store(args.get("project"))
    return {"incomplete": services.incomplete(s)}


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
