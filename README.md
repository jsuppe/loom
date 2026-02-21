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
