# Loom 🧵

**Weaving requirements through code.**

Loom is a semantic requirements traceability system for AI-assisted development. It extracts requirements from conversations, links them to code, detects conflicts, and maintains living documentation.

## Features

- **Requirement Extraction** — Parse decisions from natural language into structured requirements
- **Semantic Search** — Find requirements by meaning, not just keywords (via Ollama embeddings)
- **Conflict Detection** — Warns when new requirements overlap or contradict existing ones
- **Drift Detection** — Identifies code linked to superseded requirements
- **Living Documentation** — Auto-generates REQUIREMENTS.md and TEST_SPEC.md
- **Privacy Controls** — PRIVATE.md filters sensitive requirements from public docs

## Installation

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) with `nomic-embed-text` model
- [ChromaDB](https://www.trychroma.com) (installed automatically)

### As OpenClaw Skill

```bash
# Clone to your skills directory
git clone https://github.com/your-org/loom.git ~/.openclaw/skills/loom

# Create virtual environment and install dependencies
cd ~/.openclaw/skills/loom
python3 -m venv .venv
.venv/bin/pip install chromadb

# Pull the embedding model
ollama pull nomic-embed-text

# Add to OpenClaw config
# In ~/.openclaw/openclaw.json:
{
  "skills": {
    "load": {
      "extraDirs": ["~/.openclaw/skills"]
    }
  }
}
```

### Standalone

```bash
git clone https://github.com/your-org/loom.git
cd loom
python3 -m venv .venv
.venv/bin/pip install chromadb
ollama pull nomic-embed-text

# Add to PATH or use full path
export PATH="$PWD/scripts:$PATH"
```

## Quick Start

```bash
# Extract requirements from conversation
echo "REQUIREMENT: behavior | Users must confirm before deleting" | loom extract -p myproject

# List all requirements
loom list -p myproject

# Search semantically
loom query "deletion confirmation" -p myproject

# Check for conflicts before adding
loom conflicts --text "behavior | Allow quick delete without confirmation" -p myproject

# Generate documentation
loom sync -p myproject
```

## Usage Patterns

### For Humans (Chat-Based)

If you're working with an AI agent that has Loom integrated, just describe requirements naturally:

> "The app should require email verification before posting"

The agent will extract it, check for conflicts, and sync. For more precision, use the structured format:

> `REQUIREMENT: behavior | Email verification required before first post`

### For Agents

Add Loom to your `AGENTS.md` (see [agents.d/loom-integration.md](agents.d/loom-integration.md)):
- Extract requirements when decisions are made
- Check for drift before modifying code
- Sync documentation during heartbeats

### For CI/Automation

```bash
# Extract from a file or pipe
cat decisions.txt | loom extract -p myproject

# Check a file for drift before merge
loom check src/auth/login.dart -p myproject

# Fail CI if requirements have no test specs
loom tests -p myproject --public | grep -q "⚠️" && exit 1
```

## Managing Test Specs

Test specifications link requirements to verification steps.

### Add a Test Spec

```bash
loom test REQ-abc123 \
  -d "Verify email confirmation flow" \
  -s "Register new account;Check inbox for email;Click verification link;Attempt to post" \
  -e "Post succeeds only after email verified"
```

**Options:**
- `-d, --description` — What the test verifies
- `-s, --steps` — Semicolon-separated test steps
- `-e, --expected` — Expected outcome
- `-a, --automated` — Mark as automated test
- `--test-file` — Link to actual test file
- `--private` — Exclude from public docs

### Mark Test as Verified

```bash
loom verify REQ-abc123
```

### List All Test Specs

```bash
loom tests -p myproject
loom tests -p myproject --public  # Exclude private
```

## Keeping Things Consistent

### The Source of Truth

The **Loom store** (ChromaDB) is the source of truth, not the markdown files.

```
Loom Store (ChromaDB)
    ↓ loom sync
REQUIREMENTS.md + TEST_SPEC.md (generated)
    ↓ git push
GitHub repo (for sharing)
```

### Do NOT Edit Generated Files Directly

`REQUIREMENTS.md` and `TEST_SPEC.md` are regenerated on each `loom sync`. Direct edits will be overwritten.

**To modify requirements:**
```bash
# Add new
echo "REQUIREMENT: domain | text" | loom extract -p project

# Supersede old (marks as replaced, keeps history)
loom supersede REQ-oldid
```

**To modify test specs:**
```bash
# Update (overwrites previous)
loom test REQ-xxx -d "New description" -s "New;Steps" -e "New expected"
```

### Sync Workflow

```bash
cd /path/to/requirements-repo

# Regenerate docs from Loom store
loom --project myproject sync --output ./myproject

# Commit and push
git add -A && git commit -m "Sync requirements" && git push
```

For teams, run sync after any requirement changes to keep the repo current.

## Commands

| Command | Description |
|---------|-------------|
| `loom extract` | Extract requirements from stdin |
| `loom list` | List all requirements |
| `loom query <text>` | Semantic search |
| `loom check <file>` | Check file for requirement drift |
| `loom link <file>` | Link code to requirements |
| `loom conflicts --text` | Check for conflicts |
| `loom supersede <id>` | Mark requirement as superseded |
| `loom sync` | Generate REQUIREMENTS.md and TEST_SPEC.md |
| `loom test <id>` | Add/update test specification |
| `loom verify <id>` | Mark test as verified |
| `loom tests` | List test specifications |
| `loom status` | Show project overview |
| `loom doctor` | Run health checks |
| `loom init-private` | Create PRIVATE.md template |

## Requirement Format

Requirements are extracted from text matching this pattern:

```
REQUIREMENT: <domain> | <requirement text>
```

### Domains

- **terminology** — Naming conventions ("the app is called SpeakFit")
- **behavior** — How features work ("reset requires 3-second hold")
- **ui** — Visual/UX decisions ("mobile-friendly layout")
- **data** — Data model constraints ("timestamps in UTC")
- **architecture** — Technical decisions ("use PostgreSQL")

## Agent Integration

Add to your agent's AGENTS.md for automatic tracking:

```markdown
## Loom Integration

When a decision is made about how something should work:
→ Extract it: `echo "REQUIREMENT: domain | text" | loom extract`

Before modifying code:
→ Check for drift: `loom check <file>`

After implementing:
→ Link to requirements: `loom link <file> --req REQ-xxx`
```

## MCP Integration (Claude Code)

If you're using Claude Code, Loom can run as an **MCP server** so Claude
calls `loom_query`, `loom_extract`, etc. as first-class typed tools
instead of shelling out to the CLI. You also get three live resources
per project: `loom://requirements/{project}`, `loom://testspec/{project}`,
and `loom://drift/{project}`.

**Install the optional MCP dep:**

```bash
pip install -r requirements-mcp.txt
```

**Register the server.** Copy `.mcp.json.example` to `.mcp.json` in your
project root and adjust the paths if needed:

```bash
cp .mcp.json.example .mcp.json
```

Restart Claude Code (or reload via `/mcp`) and the `loom_*` tools
become available. See `mcp_server/README.md` for the full tool
inventory and architecture.

The CLI and MCP server share one code path (`src/services.py`), so
you can mix both in the same project — hooks and CI scripts keep
using the CLI while Claude Code sessions use MCP tools.

## Privacy

Create `PRIVATE.md` in your project to exclude sensitive requirements from public docs:

```markdown
# Private Requirements

- REQ-abc123 — Internal security policy
- REQ-def456 — Proprietary algorithm details
```

Then generate public docs:

```bash
loom sync --public
```

## How It Works

1. **Extraction**: Agent or user provides requirements in structured format
2. **Embedding**: Text is embedded using Ollama's nomic-embed-text (768 dimensions)
3. **Storage**: ChromaDB stores embeddings with metadata (versioned, timestamped)
4. **Search**: Queries use semantic similarity to find relevant requirements
5. **Conflict Detection**: New requirements are compared against existing for overlap
6. **Documentation**: Markdown files are regenerated on `loom sync`

## Data Storage

```
~/.openclaw/loom/<project>/
├── chroma.sqlite3          # ChromaDB database
├── .loom-specs.json        # Test specifications
└── PRIVATE.md              # Private requirement IDs
```

## Contributing

Contributions welcome! Please read CONTRIBUTING.md first.

## License

MIT License - see LICENSE file.
