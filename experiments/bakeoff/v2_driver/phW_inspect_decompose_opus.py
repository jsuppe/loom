#!/usr/bin/env python3
"""
Phase W probe — does Opus-driven decomposition produce R6m-precision
titles, or are titles coarse regardless of model?

Phase V probe showed `loom decompose` (Ollama qwen2.5-coder:32b)
produces 4-6 word titles. The hypothesis: this could be a model-
quality issue (Opus would do better) OR a prompt-quality issue
(the decompose prompt's example teaches coarse titles).

This probe calls `claude -p --model opus` with the *exact same*
decomposer prompt + R6 spec content, and inspects the resulting
titles. If Opus also produces coarse titles, the gap is in the
prompt template, not the model.

No persistence, no harness — just one prompt → one response →
print the titles.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")


SPEC_RULE = (
    "Constraint for adding RegexField (multi-step refactor):\n"
    "- Place the new class in `pyschema/fields/strings.py` "
    "(alongside EmailField/URLField/UUIDField, all string-typed "
    "specializations of StrField).\n"
    "- Inherit from `StrField` so it gets length validators + str "
    "coercion for free.\n"
    "- Decorate with `@dataclass` to match the sibling field types.\n"
    "- Override `validate()` to call `super().validate(value)` first, "
    "then apply `re.match(self.pattern, result)` — raise "
    "ValidationError on mismatch.\n"
    "- Re-export RegexField from `pyschema/fields/__init__.py` and "
    "add it to that file's `__all__`.\n"
    "- Re-export RegexField from `pyschema/__init__.py` and add it "
    "to its `__all__` (alphabetically after `Pattern`).\n"
    "- Default for `pattern: str` should be empty string \"\" so "
    "existing dataclass field-ordering rules are not violated.\n"
)

PARENT_REQ_VALUE = (
    "Add a RegexField type to pyschema-extended that takes a regex "
    "pattern: str and validates string inputs against the pattern."
)


def main() -> int:
    decompose_template = (LOOM_DIR / "prompts" / "decompose.md").read_text(encoding="utf-8")

    user_msg = (
        decompose_template
        + "\n---\n\n## Input specification to decompose\n\n"
        + "### SPEC-test (parent: REQ-test)\n"
        + SPEC_RULE
        + "\n## Parent requirement\n\n"
        + "### REQ-test [behavior]\n"
        + f"Value: {PARENT_REQ_VALUE}\n\n"
        + "Now produce the task decomposition per the rules above.\n"
    )

    print(f"[prompt] {len(user_msg)} chars")
    print("[opus] calling claude -p --model opus ...")
    t0 = time.time()
    proc = subprocess.run(
        ["claude", "-p",
         "--no-session-persistence",
         "--dangerously-skip-permissions",
         "--output-format", "json",
         "--model", "opus"],
        input=user_msg,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    elapsed = time.time() - t0
    print(f"[opus] {elapsed:.1f}s rc={proc.returncode}")

    if proc.returncode != 0:
        print(f"FAILED stderr: {proc.stderr[-1000:]}")
        return 1

    data = json.loads(proc.stdout)
    response = data.get("result", "")
    cost = data.get("total_cost_usd", 0)
    print(f"[opus] response_chars={len(response)}  cost=${cost:.4f}")
    print()
    print("=" * 70)
    print("OPUS RESPONSE:")
    print("=" * 70)
    print(response)
    print("=" * 70)
    print()

    # Try to extract titles
    import re
    titles = re.findall(r"^\s*-\s*title:\s*(.+)$", response, re.MULTILINE)
    if titles:
        print(f"[titles] {len(titles)} extracted:")
        for i, t in enumerate(titles, 1):
            print(f"  T{i}: {t.strip()}")
        title_lengths = [len(t.strip().strip("\"'")) for t in titles]
        print(f"[lengths] avg={sum(title_lengths)/len(title_lengths):.0f} chars  "
              f"max={max(title_lengths)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
