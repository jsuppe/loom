"""
Path normalization — M17.1.

Loom stores implementation paths relative to the project root so a
checked-out repo round-trips cleanly across machines / users. This
module owns the small bit of logic that resolves "the project root"
and converts user-typed paths (absolute, relative, mixed-slash) into
the canonical stored form (POSIX-slash, relative-to-root when
possible).

Two functions:

  * ``project_root(start=None)`` — walks up from ``start`` (or cwd)
    looking for a ``.git`` directory; falls back to the start
    directory itself when no git toplevel is found.
  * ``normalize_file_path(path, root=None)`` — returns the canonical
    stored form: POSIX-separator string, relative-to-root if the
    path lives inside the root, otherwise the resolved absolute
    string. Pure — never touches the filesystem beyond the
    ``Path.resolve()`` symlink lookup.

The store is the source of truth: a single project's impl rows are
all stored with the same convention. Whoever moves the project gets
correct paths automatically because they're relative.
"""
from __future__ import annotations

from pathlib import Path


def project_root(start: Path | str | None = None) -> Path:
    """Return the project root for the given starting directory.

    Searches upward from ``start`` (default: cwd) for the first
    ancestor containing a ``.git`` entry — that's the git toplevel
    and a reliable proxy for "project root." If no ancestor has
    one, returns the starting directory itself (no error — Loom
    can run in non-git directories).

    The returned path is fully resolved (symlinks followed).
    """
    if start is None:
        cur = Path.cwd().resolve()
    else:
        cur = Path(start).resolve()
    candidate = cur
    while True:
        if (candidate / ".git").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:  # filesystem root reached
            return cur
        candidate = parent


def normalize_file_path(
    path: Path | str,
    root: Path | str | None = None,
) -> str:
    """Convert a user-typed path into the canonical stored form.

    Rules:
      1. Resolve to absolute (handles relative paths, ``..``,
         symlinks).
      2. If the resolved path lives inside ``root``, return the
         relative form (POSIX separators).
      3. Otherwise return the resolved absolute form (POSIX
         separators) — Loom can reference files outside the
         project root (rare, e.g. cross-repo links), they just
         don't benefit from portability.

    ``root`` defaults to ``project_root()`` (cwd-relative git-toplevel
    discovery). Passed-in roots are resolved before comparison so
    the caller doesn't have to.

    Always returns forward-slash strings so the stored data is the
    same on Windows and POSIX hosts.
    """
    if root is None:
        root_path = project_root()
    else:
        root_path = Path(root).resolve()
    abs_path = Path(path).resolve()
    try:
        rel = abs_path.relative_to(root_path)
        return rel.as_posix()
    except ValueError:
        # Outside the project root — keep absolute. as_posix() on an
        # absolute Windows path gives e.g. "C:/Users/jonsu/..." which
        # is what we want stored (no backslash escaping headaches).
        return abs_path.as_posix()
