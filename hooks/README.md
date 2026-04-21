# Loom hooks

Harness-level integration for Claude Code. These hooks run automatically on
tool events so an agent gets Loom context without having to remember to call
`loom check` / `loom trace` / `loom status` every time.

## loom_pretool.py

A `PreToolUse` hook that intercepts `Edit` / `Write` / `MultiEdit` /
`NotebookEdit` tool calls, runs `loom context <file>`, and injects the
briefing (linked requirements, specs, drift) into the agent's context
as a system-reminder. Non-blocking by default.

Why this exists: `loom` only helps when it's consulted at the right moment.
Putting that call in a hook makes it automatic — the harness executes the
hook, not the agent, so it can't be forgotten.

### Install (project-local)

Add to `.claude/settings.json` in this repo (or the repo you're editing
with Loom tracking enabled):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ${CLAUDE_PROJECT_DIR}/hooks/loom_pretool.py"
          }
        ]
      }
    ]
  }
}
```

### Install (user-global)

Add the same block to `~/.claude/settings.json`, pointing at an absolute
path (since `CLAUDE_PROJECT_DIR` expands per-project):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/loom/hooks/loom_pretool.py"
          }
        ]
      }
    ]
  }
}
```

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LOOM_BIN` | `loom` on PATH, else sibling `scripts/loom` | Loom CLI path |
| `LOOM_PROJECT` | auto-detected from git | Override project name |
| `LOOM_HOOK_BLOCK_ON_DRIFT` | `0` | Set to `1` to fail the tool call on drift |
| `LOOM_HOOK_DEBUG` | `0` | Set to `1` to log hook activity to stderr |

### What the agent sees

On an `Edit` to a tracked file, before the edit runs, Claude receives a
system-reminder like:

```
Loom: src/auth/login.py linked to 2 req(s) — DRIFT on REQ-abc12345
  - REQ-abc12345 [behavior] [SUPERSEDED]: users must confirm via email
  - REQ-def67890 [behavior]: session cookies rotate every 24h
```

If `LOOM_HOOK_BLOCK_ON_DRIFT=1` is set and any linked requirement is
superseded, the edit is rejected and the message is returned as the
block reason — forcing the agent to either update the link (via
`loom supersede` / `loom link`) or explicitly override.

### Failure modes

The hook is designed to never block unrelated work:

- Loom CLI missing → exit 0, tool proceeds.
- `loom context` errors → exit 0, tool proceeds.
- Stdin JSON malformed → exit 0, tool proceeds.
- No linked requirements → exit 0 silently.

Set `LOOM_HOOK_DEBUG=1` to trace why the hook stayed quiet.
