"""
LSP-backed semantic indexer for Python.

Wraps ``python-lsp-server`` (``pylsp``) over JSON-RPC to surface
peek-references-style context for ``loom_exec`` and structural-drift
signals for ``services.check``. Mirrors ``indexers_js.py`` shape —
same project-warming, same documentSymbol + textDocument/references
flow, same adjacent-class-defs section, same import-line filtering,
same soft-fail-when-binary-missing contract.

Install requirement::

    pip install python-lsp-server

The indexer invokes pylsp as ``python -m pylsp`` by default. This
sidesteps the Windows-Store-Python-doesn't-add-scripts-to-PATH
problem (pylsp is installed but not on PATH; ``-m`` works regardless).

If pylsp isn't importable, the indexer fails soft — first call warns
once and returns ``""``, matching the M10.1 NoOpIndexer contract.

Output shape matches ``JsIndexer`` so downstream consumers (loom_exec
prompt assembly, services.check) don't care which language they're
looking at:

    # === SEMANTIC CONTEXT (lsp:pylsp for retry.py) ===
    #
    # References to retry (function, 3 results from
    # textDocument/references):
    #
    #   src/consumer.py:34
    #       result = retry(fn, max_attempts=3)
    #       if result is None:
    #           ...
    #
    # === END SEMANTIC CONTEXT ===

Concurrency, lifecycle, and error handling all mirror ``JsIndexer``;
see that module's docstring for the design notes that apply equally.
"""
from __future__ import annotations

import atexit
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import warnings
import weakref
from pathlib import Path
from typing import Optional

from loom.indexers import SemanticIndexer


# Default module name to invoke via `python -m`. Lets the indexer work
# on Windows Store Python where `pylsp` script isn't on PATH but the
# package is importable.
_DEFAULT_MODULE = "pylsp"

# How many lines of code to include after each reference site.
# Mirrors JsIndexer's snippet shape (4 after, 0 before).
_SNIPPET_LINES_AFTER = 4

# Caps to keep prompts bounded on large files.
_MAX_SYMBOLS_PER_FILE = 5
_MAX_REFS_PER_SYMBOL = 5
_MAX_TYPE_DEFS_PER_FILE = 5
_MAX_PROJECT_FILES = 200

_PROJECT_GLOB_SUFFIXES = (".py", ".pyi")
_PROJECT_GLOB_IGNORE_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    "dist", "build", "node_modules", ".eggs",
}

# LSP SymbolKind constants (subset). Same constants as indexers_js.
_KIND_CLASS = 5
_KIND_METHOD = 6
_KIND_FUNCTION = 12
_INTERESTING_KINDS = {_KIND_CLASS, _KIND_METHOD, _KIND_FUNCTION}
_KIND_NAMES = {
    _KIND_CLASS: "class",
    _KIND_METHOD: "method",
    _KIND_FUNCTION: "function",
}


# Track every live PyIndexer so atexit can shut them down even if the
# user drops their reference without calling shutdown().
_LIVE_INSTANCES: "weakref.WeakSet[PyIndexer]" = weakref.WeakSet()


@atexit.register
def _shutdown_all() -> None:
    for inst in list(_LIVE_INSTANCES):
        try:
            inst.shutdown()
        except Exception:
            pass


class PyIndexer(SemanticIndexer):
    """Real LSP-backed indexer for Python via ``python-lsp-server``.

    See module docstring for design notes. Mirrors ``JsIndexer``
    structure so behavior is consistent across languages."""

    name = "pylsp"
    languages = ("python", "py")

    def __init__(self, root: Optional[Path] = None,
                 server_cmd: Optional[list[str]] = None) -> None:
        self._root = (root or Path.cwd()).resolve()
        self._server_cmd_override = server_cmd
        self._proc: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._next_id = 1
        self._opened: set[Path] = set()
        self._unavailable = False
        _LIVE_INSTANCES.add(self)

    # ------------------------------------------------------------------
    # SemanticIndexer interface
    # ------------------------------------------------------------------

    def context_for(self, file: Path) -> str:
        if self._unavailable:
            return ""
        with self._lock:
            try:
                self._ensure_started()
            except (FileNotFoundError, OSError, RuntimeError) as e:
                self._unavailable = True
                warnings.warn(
                    f"PyIndexer: language server unavailable, returning "
                    f"empty context. Install with `pip install "
                    f"python-lsp-server`. ({e})",
                    RuntimeWarning, stacklevel=2,
                )
                return ""
            try:
                return self._build_context(Path(file))
            except Exception as e:
                warnings.warn(
                    f"PyIndexer: error building context for {file}: {e}",
                    RuntimeWarning, stacklevel=2,
                )
                return ""

    def health(self) -> dict:
        """Probe whether ``pylsp`` is importable. Does NOT spawn the
        LSP — that's deferred to the first ``context_for`` call.
        ``loom indexer-doctor`` invokes this for a fast pre-flight."""
        if self._server_cmd_override:
            cmd = " ".join(self._server_cmd_override)
            return {
                "ok": True,
                "detail": f"server_cmd override: {cmd}",
            }
        spec = importlib.util.find_spec(_DEFAULT_MODULE)
        if spec is None:
            return {
                "ok": False,
                "detail": (
                    f"python-lsp-server not importable. Install with: "
                    f"pip install python-lsp-server"
                ),
            }
        return {
            "ok": True,
            "detail": f"module: {_DEFAULT_MODULE} ({spec.origin})",
        }

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        with self._lock:
            self._shutdown_locked()

    def _shutdown_locked(self) -> None:
        if self._proc is None or self._proc.poll() is not None:
            self._proc = None
            return
        try:
            self._send_request("shutdown", None)
            self._send_notification("exit", None)
        except Exception:
            pass
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._proc = None
        self._opened.clear()

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Subprocess + JSON-RPC
    # ------------------------------------------------------------------

    def _resolve_server_cmd(self) -> list[str]:
        if self._server_cmd_override:
            return self._server_cmd_override
        spec = importlib.util.find_spec(_DEFAULT_MODULE)
        if spec is None:
            raise FileNotFoundError(
                f"python-lsp-server (module {_DEFAULT_MODULE!r}) not "
                f"importable. Install: pip install python-lsp-server"
            )
        return [sys.executable, "-m", _DEFAULT_MODULE]

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        cmd = self._resolve_server_cmd()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        root_uri = _path_to_uri(self._root)
        self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "workspaceFolders": [{
                "uri": root_uri,
                "name": self._root.name or "workspace",
            }],
            "capabilities": {
                "textDocument": {
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                    },
                },
            },
        })
        self._send_notification("initialized", {})

    def _send_message(self, msg: dict) -> None:
        assert self._proc is not None and self._proc.stdin is not None
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self._proc.stdin.write(header + body)
        self._proc.stdin.flush()

    def _read_message(self) -> dict:
        assert self._proc is not None and self._proc.stdout is not None
        content_length = -1
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("LSP server closed the pipe")
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("ascii", errors="replace").strip()
            if decoded.lower().startswith("content-length:"):
                content_length = int(decoded.split(":", 1)[1].strip())
        if content_length < 0:
            raise RuntimeError("LSP response missing Content-Length")
        body = self._proc.stdout.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _send_request(self, method: str, params: Optional[dict]):
        request_id = self._next_id
        self._next_id += 1
        self._send_message({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params if params is not None else {},
        })
        while True:
            msg = self._read_message()
            if msg.get("id") == request_id and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(f"LSP error: {msg['error']}")
                return msg.get("result")
            if "id" in msg and msg.get("method"):
                # Server-initiated request — refuse politely.
                self._send_message({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": None,
                })

    def _send_notification(self, method: str, params: Optional[dict]) -> None:
        self._send_message({
            "jsonrpc": "2.0",
            "method": method,
            "params": params if params is not None else {},
        })

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _open_file(self, file: Path) -> None:
        if file in self._opened:
            return
        text = file.read_text(encoding="utf-8")
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": _path_to_uri(file),
                "languageId": "python",
                "version": 1,
                "text": text,
            },
        })
        self._opened.add(file)

    def _warm_project(self) -> None:
        """Open every Python file under root once so cross-file
        references resolve. Mirrors JsIndexer._warm_project — pylsp
        also only resolves refs in files it's been told about."""
        if self._proc is None:
            return
        newly_opened: list[Path] = []
        for path in _walk_project(self._root):
            if path in self._opened:
                continue
            if len(newly_opened) >= _MAX_PROJECT_FILES:
                break
            try:
                self._open_file(path)
                newly_opened.append(path)
            except (OSError, UnicodeDecodeError):
                pass
        # Force-parse with synchronous documentSymbol queries.
        for path in newly_opened:
            try:
                self._send_request("textDocument/documentSymbol", {
                    "textDocument": {"uri": _path_to_uri(path)},
                })
            except Exception:
                pass

    def _build_context(self, file: Path) -> str:
        if not file.exists():
            return ""
        self._warm_project()
        self._open_file(file)
        symbols = self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": _path_to_uri(file)},
        }) or []

        flat = _flatten_symbols(symbols)
        # pylsp returns SymbolInformation regardless of capability hint;
        # its position is the line-start (col 0), not the symbol name.
        # textDocument/references with col 0 returns nothing. Resolve
        # to the actual name offset within the line so refs land on
        # the identifier itself.
        for s in flat:
            s["position"] = _refine_position_to_name(
                file, s["position"], s["name"],
            )
        top = [s for s in flat if s["kind"] in _INTERESTING_KINDS]
        if not top:
            return ""

        out: list[str] = []
        out.append(f"# === SEMANTIC CONTEXT (lsp:{self.name} for {file.name}) ===")
        out.append("#")

        interesting_siblings: list[Path] = []
        seen_siblings: set[Path] = set()

        any_emitted = False
        for sym in top[:_MAX_SYMBOLS_PER_FILE]:
            references = self._send_request("textDocument/references", {
                "textDocument": {"uri": _path_to_uri(file)},
                "position": sym["position"],
                "context": {"includeDeclaration": False},
            }) or []
            if not references:
                continue
            filtered = [
                r for r in references
                if not _is_import_ref(_uri_to_path(r["uri"]),
                                      r["range"]["start"]["line"])
            ]
            if not filtered:
                continue
            kind_name = _KIND_NAMES.get(sym["kind"], "symbol")
            out.append(
                f"# References to {sym['name']} ({kind_name}, "
                f"{len(filtered)} results from textDocument/references):"
            )
            out.append("#")
            for ref in filtered[:_MAX_REFS_PER_SYMBOL]:
                ref_uri = ref["uri"]
                ref_path = _uri_to_path(ref_uri)
                ref_line = ref["range"]["start"]["line"]
                rel = _relative_to(ref_path, self._root)
                out.append(f"#   {rel}:{ref_line + 1}")
                snippet = _read_snippet(ref_path, ref_line,
                                        after=_SNIPPET_LINES_AFTER)
                for sl in snippet:
                    out.append(f"#       {sl.rstrip()}")
                out.append("#")
                if (ref_path != file.resolve()
                        and ref_path not in seen_siblings):
                    seen_siblings.add(ref_path)
                    interesting_siblings.append(ref_path)
            any_emitted = True

        if not any_emitted:
            return ""

        type_def_lines = self._collect_adjacent_type_defs(
            interesting_siblings, exclude=file.resolve(),
        )
        if type_def_lines:
            out.append("# Symbols defined in referenced files:")
            out.append("#")
            for line in type_def_lines:
                out.append(f"#   {line}")
            out.append("#")

        out.append("# === END SEMANTIC CONTEXT ===")
        return "\n".join(out)

    def _collect_adjacent_type_defs(self, files: list[Path],
                                     *, exclude: Path) -> list[str]:
        """Query each referenced sibling file for its top-level Class
        definitions. Returns single-line summaries with path:line."""
        if self._proc is None:
            return []
        results: list[str] = []
        for sibling in files:
            if sibling == exclude:
                continue
            try:
                self._open_file(sibling)
            except (OSError, UnicodeDecodeError):
                continue
            try:
                syms = self._send_request("textDocument/documentSymbol", {
                    "textDocument": {"uri": _path_to_uri(sibling)},
                }) or []
            except Exception:
                continue
            flat = _flatten_symbols(syms)
            classes = [s for s in flat if s["kind"] == _KIND_CLASS]
            if not classes:
                continue
            rel = _relative_to(sibling, self._root)
            for cls in classes[:_MAX_TYPE_DEFS_PER_FILE]:
                line_no = cls["position"]["line"]
                signature = _read_signature_line(sibling, line_no)
                if not signature:
                    continue
                results.append(f"{signature}    # {rel}:{line_no + 1}")
        return results


# ---------------------------------------------------------------------------
# Helpers — Python-specific variants of indexers_js helpers
# ---------------------------------------------------------------------------


def _flatten_symbols(symbols: list) -> list[dict]:
    """Normalize ``DocumentSymbol[]`` or ``SymbolInformation[]`` into a
    flat list of ``{name, kind, position}``. Same logic as
    indexers_js._flatten_symbols — symbol shape is LSP-standard and
    language-agnostic."""
    flat: list[dict] = []
    for sym in symbols:
        kind = sym.get("kind")
        name = sym.get("name", "?")
        if "selectionRange" in sym:
            pos = sym["selectionRange"]["start"]
            flat.append({"name": name, "kind": kind, "position": pos})
            for child in sym.get("children", []) or []:
                flat.extend(_flatten_symbols([child]))
        elif "location" in sym:
            pos = sym["location"]["range"]["start"]
            flat.append({"name": name, "kind": kind, "position": pos})
    return flat


def _path_to_uri(path: Path) -> str:
    s = str(Path(path).resolve()).replace("\\", "/")
    if not s.startswith("/"):
        s = "/" + s
    return "file://" + s


def _uri_to_path(uri: str) -> Path:
    from urllib.parse import unquote
    if uri.startswith("file:///"):
        s = unquote(uri[len("file://"):])
        if sys.platform == "win32" and len(s) >= 3 and s[0] == "/" and s[2] == ":":
            s = s[1:]
        return Path(s)
    return Path(unquote(uri))


def _relative_to(path: Path, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _walk_project(root: Path):
    """Yield Python source files under ``root``, ignoring heavy
    directories (.venv, __pycache__, etc.)."""
    stack: list[Path] = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (OSError, PermissionError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name in _PROJECT_GLOB_IGNORE_DIRS:
                    continue
                stack.append(entry)
            elif entry.is_file() and entry.suffix.lower() in _PROJECT_GLOB_SUFFIXES:
                yield entry


# Match Python import statements at the start of a line:
#   import x
#   import x as y
#   import x, y
#   from x import y
#   from x import (y, z)
#   from . import y
#   from .x import y
_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:import\s+\w|from\s+[\w.]+\s+import\b)"
)


def _is_import_ref(file: Path, line_num: int) -> bool:
    """Is the reference at ``file:line_num`` an import statement?
    Mirrors indexers_js._is_import_ref — pylsp's references include
    the import-line use which adds no call-site signal."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.splitlines()
    if line_num >= len(lines):
        return False
    return bool(_IMPORT_LINE_RE.match(lines[line_num]))


def _refine_position_to_name(file: Path, position: dict, name: str) -> dict:
    """pylsp returns SymbolInformation with position.character=0
    (line start, before ``def`` / ``class``). textDocument/references
    at column 0 returns nothing. Read the line, find the symbol name,
    and return a position pointing at the first character of the name.

    Falls back to the original position if the file can't be read or
    the name isn't found on the line (rare; defensive).
    """
    line_num = position.get("line", 0)
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return position
    lines = text.splitlines()
    if line_num >= len(lines):
        return position
    line = lines[line_num]
    # Find the name as a whole word, not a substring.
    pattern = r"\b" + re.escape(name) + r"\b"
    m = re.search(pattern, line)
    if m is None:
        return position
    return {"line": line_num, "character": m.start()}


def _read_signature_line(file: Path, line_num: int) -> str:
    """Read the first non-empty line at or after ``line_num`` and
    strip trailing ``:`` so the result is just the declaration head
    (e.g. ``class Foo(Bar)`` rather than ``class Foo(Bar):``)."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    for i in range(line_num, min(line_num + 3, len(lines))):
        stripped = lines[i].strip()
        if stripped:
            if stripped.endswith(":"):
                stripped = stripped[:-1].rstrip()
            return stripped
    return ""


def _read_snippet(file: Path, line: int, *, before: int = 0,
                  after: int = 4) -> list[str]:
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = text.splitlines()
    start = max(0, line - before)
    end = min(len(lines), line + after + 1)
    return lines[start:end]
