"""M28 — manual smoke test for ClangdIndexer against the S1 scenario.

Run once after installing clangd to verify the indexer produces
non-empty context that's in the pre-registered 500-4000 char range.

Not a pytest test because it requires clangd installed locally.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from loom.indexers_cpp import ClangdIndexer  # noqa: E402


SCENARIO_DIR = (
    REPO_ROOT
    / "experiments" / "bakeoff" / "benchmarks" / "crosssession_cpp"
    / "s1_swallow_runtime_error"
)
TARGET_FILE = SCENARIO_DIR / "reference" / "retry.hpp"


def _resolve_compile_db() -> Path:
    """Substitute ${SCENARIO_DIR} placeholders so clangd can consume it."""
    cdb = SCENARIO_DIR / "compile_commands.json"
    src = cdb.read_text(encoding="utf-8")
    out = src.replace("${SCENARIO_DIR}", SCENARIO_DIR.as_posix())
    cdb.write_text(out, encoding="utf-8")
    return cdb


def _restore_compile_db_template() -> None:
    """Re-write the templated form so the file we commit stays portable."""
    cdb = SCENARIO_DIR / "compile_commands.json"
    src = cdb.read_text(encoding="utf-8")
    out = src.replace(SCENARIO_DIR.as_posix(), "${SCENARIO_DIR}")
    cdb.write_text(out, encoding="utf-8")


def _find_clangd() -> Path:
    """Locate clangd. Tries PATH first, falls back to a scoop install."""
    on_path = shutil.which("clangd")
    if on_path:
        return Path(on_path)
    scoop = (Path.home() / "scoop" / "apps" / "llvm" / "current"
             / "bin" / "clangd.exe")
    if scoop.exists():
        return scoop
    raise FileNotFoundError(
        "clangd not found on PATH or at "
        "~/scoop/apps/llvm/current/bin/clangd.exe"
    )


def main() -> int:
    clangd = _find_clangd()
    print(f"clangd: {clangd}")
    print(f"target: {TARGET_FILE}")
    print(f"root  : {SCENARIO_DIR}")
    print()

    _resolve_compile_db()
    try:
        indexer = ClangdIndexer(
            root=SCENARIO_DIR,
            server_cmd=[str(clangd), "--background-index",
                        "--header-insertion=never", "--log=error"],
        )
        # Probe health (no LSP spawn).
        h = indexer.health()
        print(f"health: ok={h['ok']}  {h['detail']}")
        print()

        # Build context for retry.hpp.
        context = indexer.context_for(TARGET_FILE)

        print("=" * 60)
        print(f"CONTEXT ({len(context)} chars):")
        print("=" * 60)
        print(context)
        print("=" * 60)

        # Pre-reg contract: 500-4000 chars.
        n = len(context)
        if n == 0:
            print("\nWARN: empty context.")
            return 1
        if n < 500:
            print(f"\nWARN: context length {n} below pre-reg floor (500).")
            return 1
        if n > 4000:
            print(f"\nWARN: context length {n} above pre-reg cap (4000).")
            return 1
        print(f"\nOK: context length {n} within pre-reg band [500, 4000].")
        indexer.shutdown()
        return 0
    finally:
        _restore_compile_db_template()


if __name__ == "__main__":
    raise SystemExit(main())
