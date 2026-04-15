---
name: loom
description: Extract requirements from conversations, link to code, detect drift. Use when making decisions, before modifying code, or to check staleness.
---

# Loom 🧵 — Requirements Traceability Skill

**Weaving requirements through code.**

Loom extracts requirements from your conversations, links them to code, and detects drift when requirements change.

## When to Use

This skill is **always active** via AGENTS.md integration. You invoke it at specific moments:

| Moment | Action | Command |
|--------|--------|---------|
| Decision made in chat | Extract requirement | `loom extract` |
| Before modifying code | Check for drift | `loom check <file>` |
| After implementing | Link to requirements | `loom link <file>` |
| Heartbeat | Scan for staleness | `loom status` |

## Commands

All commands are in `scripts/` (relative to this skill directory).

### `loom extract [--session <key>]`
Extract requirements from current or specified session.
- Parses conversation for decisions about behavior, terminology, UI, data
- Creates versioned requirements in the store
- If a requirement contradicts an existing one, supersedes the old version

### `loom check <file> [--lines <range>]`
Check a file for drift before modification.
- Finds linked requirements for the code section
- Warns if any linked requirements have been superseded
- Shows what changed so you can update accordingly

### `loom link <file> [--lines <range>] [--req <id>...]`
Link code to requirements it satisfies.
- Auto-detects likely requirements via semantic search
- Or manually specify with `--req`
- Creates implementation record with content hash

### `loom status [--project <name>]`
Show requirements overview.
- Count of active vs superseded requirements
- Implementations with drift (linked to superseded reqs)
- Recent extractions

### `loom query <text>`
Search requirements semantically.
- Returns matching requirements with provenance
- Use before implementing to find relevant constraints

## Integration Points

### AGENTS.md Addition
Add this to your AGENTS.md to make Loom automatic:

```markdown
## Loom Integration

When you make a decision about how something should work:
→ Run `loom extract` to capture it as a requirement

Before modifying code:
→ Run `loom check <file>` to verify no drift

After implementing a feature:
→ Run `loom link <file>` to trace it to requirements

During heartbeats (once per day):
→ Run `loom status` to surface staleness
```

### HEARTBEAT.md Addition
```markdown
### Loom Check (daily)
- Run `loom status` to check for drifted implementations
- If drift found, note in daily memory for next work session
```

## Requirement Domains

Loom categorizes requirements by domain:

- **terminology** — What things are called ("posts are called boats")
- **behavior** — How features work ("reset requires 3-second hold")
- **ui** — Visual/UX decisions ("mobile-friendly", "no markdown tables")
- **data** — Data model constraints ("time rounds down to half-hour")
- **architecture** — Technical decisions ("ChromaDB for vectors")

## Data Storage

- Store location: `~/.openclaw/loom/<project>/`
- Uses ChromaDB with persistent storage
- Three collections: requirements, implementations, chat_messages

## MCP Integration (Claude Code)

Loom also ships an MCP server so Claude Code can call verbs like
`loom_query`, `loom_extract`, `loom_trace`, `loom_chain` as first-class
tools — no shell subprocess, no string parsing. Three resources per
project (`loom://requirements/…`, `loom://testspec/…`, `loom://drift/…`)
stream live docs into Claude's context.

```bash
pip install -r requirements-mcp.txt
cp .mcp.json.example .mcp.json   # or adapt to your setup
```

Full tool inventory and architecture: `mcp_server/README.md`.

## Example Flow

```
User: "The app should use half-hour increments for time selection"

Agent thinks: This is a data/behavior requirement.
Agent runs: loom extract
→ Creates requirement: {domain: "data", value: "Time selection uses half-hour increments"}

Later, agent modifies TimeSelector.dart
Agent runs: loom check lib/widgets/time_selector.dart
→ Shows: Linked to REQ-042 "Time selection uses half-hour increments" ✓

Even later, user says: "Actually, let's use 15-minute increments"
Agent runs: loom extract
→ Supersedes REQ-042, creates REQ-043

Next heartbeat:
Agent runs: loom status
→ DRIFT: lib/widgets/time_selector.dart linked to superseded REQ-042
→ Agent notes: Need to update TimeSelector for 15-min increments
```

## Files

- `scripts/loom` — Main CLI (Python)
- `src/store.py` — ChromaDB interface
- `src/extractor.py` — LLM-powered requirement extraction
- `src/indexer.py` — Code indexing and embedding
- `prompts/extract.md` — Extraction prompt template
- `prompts/link.md` — Linking prompt template
