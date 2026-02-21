# Loom Integration

**Add this section to your AGENTS.md to enable automatic requirements tracing.**

---

## 🧵 Loom — Requirements Traceability

Loom tracks requirements from conversations and links them to code. Use it at these moments:

### When a Decision is Made

When you or the user decide how something should work, extract it:

```bash
# Format the requirement and pipe to loom
echo "REQUIREMENT: <domain> | <requirement text>" | loom extract -p <project>
```

Domains: terminology, behavior, ui, data, architecture

### Before Modifying Code

Check for drift (requirements that changed since the code was written):

```bash
loom check <file> -p <project>
```

If drift is found, review the superseded requirements before proceeding.

### After Implementing

Link your implementation to the requirements it satisfies:

```bash
loom link <file> --req REQ-xxx -p <project>
```

### During Heartbeats

Add to your HEARTBEAT.md:
```markdown
### Loom Status (weekly)
- Run `loom status -p <project>` to check for drift
- Note any drifted implementations for next work session
```

---

## Quick Reference

| Action | Command |
|--------|---------|
| Extract requirement | `echo "REQUIREMENT: domain \| text" \| loom extract` |
| Check file for drift | `loom check <file>` |
| Link code to requirement | `loom link <file> --req REQ-xxx` |
| Show all requirements | `loom list` |
| Search requirements | `loom query "search text"` |
| Status overview | `loom status` |

## Path Setup

Add to your shell or run directly:
```bash
export PATH="$HOME/.openclaw/skills/loom/scripts:$PATH"
```

Or invoke with full path:
```bash
~/.openclaw/skills/loom/scripts/loom status
```
