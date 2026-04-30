"""Idiom adherence checks for R6 RegexField additions.

Run programmatically by the harness. Returns a dict of bool checks
(each True/False). The harness sums them into an idiom-adherence
score. Failures here indicate qwen wrote correct-but-non-idiomatic
code — landed in the wrong file, didn't use the @dataclass pattern,
diverged from how Email/URL/UUID are structured.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict


def check_file_placement(workspace: Path) -> bool:
    """RegexField should live in pyschema/fields/strings.py
    (alongside Email/URL/UUID), not in a new file or in fields/regex.py."""
    strings_file = workspace / "pyschema" / "fields" / "strings.py"
    if not strings_file.exists():
        return False
    text = strings_file.read_text(encoding="utf-8")
    return "class RegexField" in text


def check_inherits_strfield(workspace: Path) -> bool:
    """RegexField must inherit from StrField (not Field directly,
    not from a different base)."""
    strings_file = workspace / "pyschema" / "fields" / "strings.py"
    if not strings_file.exists():
        return False
    try:
        tree = ast.parse(strings_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RegexField":
            return any(
                (isinstance(base, ast.Name) and base.id == "StrField")
                or (isinstance(base, ast.Attribute) and base.attr == "StrField")
                for base in node.bases
            )
    return False


def check_uses_dataclass(workspace: Path) -> bool:
    """RegexField should use the @dataclass decorator (matches the
    sibling field types — Email, URL, UUID all do)."""
    strings_file = workspace / "pyschema" / "fields" / "strings.py"
    if not strings_file.exists():
        return False
    try:
        tree = ast.parse(strings_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RegexField":
            return any(
                (isinstance(d, ast.Name) and d.id == "dataclass")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                    and d.func.id == "dataclass")
                for d in node.decorator_list
            )
    return False


def check_validate_calls_super(workspace: Path) -> bool:
    """RegexField.validate should call super().validate(value) and then
    apply the regex check — matches the Email/URL/UUID pattern."""
    strings_file = workspace / "pyschema" / "fields" / "strings.py"
    if not strings_file.exists():
        return False
    try:
        tree = ast.parse(strings_file.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "RegexField":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "validate":
                    # Look for super().validate(...) call somewhere in the body
                    for sub in ast.walk(item):
                        if (
                            isinstance(sub, ast.Call)
                            and isinstance(sub.func, ast.Attribute)
                            and sub.func.attr == "validate"
                            and isinstance(sub.func.value, ast.Call)
                            and isinstance(sub.func.value.func, ast.Name)
                            and sub.func.value.func.id == "super"
                        ):
                            return True
    return False


def run_all(workspace: Path) -> Dict[str, bool]:
    return {
        "file_placement": check_file_placement(workspace),
        "inherits_strfield": check_inherits_strfield(workspace),
        "uses_dataclass": check_uses_dataclass(workspace),
        "validate_calls_super": check_validate_calls_super(workspace),
    }


def score(checks: Dict[str, bool]) -> int:
    return sum(1 for v in checks.values() if v)


if __name__ == "__main__":
    import sys
    ws = Path(sys.argv[1])
    checks = run_all(ws)
    print(f"score: {score(checks)}/{len(checks)}")
    for k, v in checks.items():
        print(f"  {'OK' if v else 'NO'}: {k}")
