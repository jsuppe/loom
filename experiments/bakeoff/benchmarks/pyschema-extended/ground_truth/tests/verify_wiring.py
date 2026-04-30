"""Cross-file wiring checks for R6.

Tests whether qwen propagated the RegexField addition correctly
through the package's barrel exports. A correct refactor wires
RegexField into:
  - pyschema/fields/__init__.py  (re-export from .strings)
  - pyschema/__init__.py          (top-level barrel + __all__)
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict


def check_fields_init_exports(workspace: Path) -> bool:
    """fields/__init__.py should re-export RegexField from .strings."""
    init = workspace / "pyschema" / "fields" / "__init__.py"
    if not init.exists():
        return False
    text = init.read_text(encoding="utf-8")
    if "RegexField" not in text:
        return False
    # Must come from .strings (not e.g. .regex)
    return "from .strings import" in text and "RegexField" in text.split("from .strings import")[1].split("\n")[0]


def check_top_barrel_imports(workspace: Path) -> bool:
    """pyschema/__init__.py should import RegexField."""
    init = workspace / "pyschema" / "__init__.py"
    if not init.exists():
        return False
    text = init.read_text(encoding="utf-8")
    return "RegexField" in text


def check_top_barrel_all(workspace: Path) -> bool:
    """pyschema/__init__.py __all__ should include RegexField."""
    init = workspace / "pyschema" / "__init__.py"
    if not init.exists():
        return False
    text = init.read_text(encoding="utf-8")
    if "__all__" not in text:
        return False
    after_all = text.split("__all__")[1]
    return '"RegexField"' in after_all or "'RegexField'" in after_all


def check_top_level_import_works(workspace: Path) -> bool:
    """Live-import test: ``from pyschema import RegexField`` must succeed
    after the refactor. Catches the case where the refactor adds the
    class but breaks the top-level barrel."""
    import importlib
    import sys
    ws_str = str(workspace)
    if ws_str not in sys.path:
        sys.path.insert(0, ws_str)
    # Drop any cached pyschema modules so we hit the workspace's version
    cached = [k for k in sys.modules if k == "pyschema" or k.startswith("pyschema.")]
    for k in cached:
        del sys.modules[k]
    try:
        mod = importlib.import_module("pyschema")
        return hasattr(mod, "RegexField")
    except Exception:
        return False
    finally:
        # Clean up to keep the harness re-runnable
        cached = [k for k in sys.modules if k == "pyschema" or k.startswith("pyschema.")]
        for k in cached:
            del sys.modules[k]
        if ws_str in sys.path:
            sys.path.remove(ws_str)


def run_all(workspace: Path) -> Dict[str, bool]:
    return {
        "fields_init_re_export": check_fields_init_exports(workspace),
        "top_barrel_import": check_top_barrel_imports(workspace),
        "top_barrel_all": check_top_barrel_all(workspace),
        "top_level_import_works": check_top_level_import_works(workspace),
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
