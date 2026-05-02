"""
LSP-backed semantic indexer for JavaScript and TypeScript.

Wraps ``typescript-language-server --stdio`` over JSON-RPC to surface
peek-references-style context for ``loom_exec``. Validated empirically
against the M10.3 phQ3/phQ4 falsifications, which established that
structural call-site context lifts compliance on rationale-augmented
prompts (+80pp on placebo, +20pp on rationale at qwen2.5-coder:32b).

Install requirement::

    npm install -g typescript-language-server typescript

If the binary isn't on PATH the indexer fails soft — first call warns
once and returns ``""``, so Loom keeps working without the indexer
installed (matching the M10.1 NoOpIndexer contract).

Output shape matches the phQ3 ``S1_JS_STUB_CLEAN_CONTEXT`` reference,
intentionally — that's the shape the stub falsification confirmed
carries the +80pp signal:

    // === SEMANTIC CONTEXT (lsp:ts-lsp for retry.js) ===
    //
    // References to fetchWithRetry (function, 3 results from
    // textDocument/references):
    //
    //   src/backoff_loop.js:34
    //       const result = await fetchWithRetry(url, this.attempts);
    //       if (result === null) {
    //           ...
    //
    // === END SEMANTIC CONTEXT ===

Concurrency: a single subprocess is spawned per ``JsIndexer`` instance
and reused across calls. ``threading.Lock`` guards request/response
correlation when multiple threads call ``context_for`` (rare in
practice but cheap to hold). Subprocess is shut down via ``shutdown()``
which is invoked from ``__del__`` and ``atexit``.
"""
from __future__ import annotations

import atexit
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import warnings
import weakref
from pathlib import Path
from typing import Optional

from loom.indexers import SemanticIndexer


_DEFAULT_BINARY = "typescript-language-server"

# How many lines of code to include after each reference site. Mirrors
# the phQ3 stub's snippet shape (4 lines after, 0 before).
_SNIPPET_LINES_AFTER = 4

# Caps to keep prompts bounded on large files. The phQ3 stub had
# 3 references; real codebases can have hundreds.
_MAX_SYMBOLS_PER_FILE = 5
_MAX_REFS_PER_SYMBOL = 5

# How many top-level Class symbols to include from each
# referenced sibling file, in the "Symbols defined in referenced
# files" section. phQ5 (M10.3d) found that this section is what
# closes the gap between hand-curated stubs and raw LSP refs on
# placebo-augmented prompts. 5 per file is enough for the typical
# Loom-target file (1-3 classes); larger files surface their
# first 5.
_MAX_TYPE_DEFS_PER_FILE = 5

# Cap on how many sibling files we open eagerly to populate the LSP's
# project view. typescript-language-server only resolves references in
# files it has loaded, so we open the workspace's JS/TS files up front.
# 200 is generous for typical Loom-target projects (~10s to low 100s of
# files) without risking pathological openings on a node_modules-laden
# checkout.
_MAX_PROJECT_FILES = 200

_PROJECT_GLOB_SUFFIXES = (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx")
_PROJECT_GLOB_IGNORE_DIRS = {"node_modules", ".git", "dist", "build", ".next"}

# LSP SymbolKind constants (subset). See:
# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
_KIND_CLASS = 5
_KIND_METHOD = 6
_KIND_FUNCTION = 12
_INTERESTING_KINDS = {_KIND_CLASS, _KIND_METHOD, _KIND_FUNCTION}
_KIND_NAMES = {
    _KIND_CLASS: "class",
    _KIND_METHOD: "method",
    _KIND_FUNCTION: "function",
}


# Track every live JsIndexer so atexit can shut them down cleanly even
# if the user drops their reference without calling shutdown().
_LIVE_INSTANCES: "weakref.WeakSet[JsIndexer]" = weakref.WeakSet()


@atexit.register
def _shutdown_all() -> None:
    for inst in list(_LIVE_INSTANCES):
        try:
            inst.shutdown()
        except Exception:
            pass


class JsIndexer(SemanticIndexer):
    """Real LSP-backed indexer for JavaScript and TypeScript via
    ``typescript-language-server``. See module docstring for design
    notes."""

    name = "ts-lsp"
    languages = ("javascript", "js", "typescript", "ts")

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
                    f"JsIndexer: language server unavailable, returning "
                    f"empty context. Install with `npm install -g "
                    f"typescript-language-server typescript`. ({e})",
                    RuntimeWarning, stacklevel=2,
                )
                return ""
            try:
                return self._build_context(Path(file))
            except Exception as e:
                warnings.warn(
                    f"JsIndexer: error building context for {file}: {e}",
                    RuntimeWarning, stacklevel=2,
                )
                return ""

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
        # LSP shutdown sequence: shutdown request → exit notification.
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
        # On Windows, npm-installed binaries have ``.cmd`` shims that
        # ``shutil.which`` finds when given the bare name.
        path = shutil.which(_DEFAULT_BINARY)
        if path is None:
            raise FileNotFoundError(
                f"{_DEFAULT_BINARY} not found on PATH"
            )
        return [path, "--stdio"]

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
        # LSP initialize handshake. workspaceFolders is what makes
        # typescript-language-server treat the root as a project (with
        # jsconfig.json/tsconfig.json discovery). Without it, queries
        # only see the single file we explicitly didOpen, breaking
        # cross-file references.
        root_uri = _path_to_uri(self._root)
        # hierarchicalDocumentSymbolSupport asks the server to return
        # DocumentSymbol[] (with `selectionRange` pointing at the
        # symbol's name only) instead of SymbolInformation[] (where
        # `location.range` spans the entire body). We need name-only
        # ranges to position the cursor correctly for references —
        # otherwise refs at the start of `async function fetchWithRetry`
        # land on the `async` keyword and return only same-file refs.
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
        # Headers terminate with a blank \r\n line.
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
        # Drain server-initiated traffic until we see our response.
        while True:
            msg = self._read_message()
            if msg.get("id") == request_id and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError(f"LSP error: {msg['error']}")
                return msg.get("result")
            # Server-initiated request (has both id and method): refuse
            # politely so we don't deadlock on workspace/configuration
            # or registerCapability.
            if "id" in msg and msg.get("method"):
                self._send_message({
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "result": None,
                })
            # Server-initiated notifications (no id): ignore.

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
                "languageId": _language_id_for(file),
                "version": 1,
                "text": text,
            },
        })
        self._opened.add(file)

    def _warm_project(self) -> None:
        """Open every JS/TS file under root once so cross-file
        references resolve. typescript-language-server only sees files
        it's been told about via ``didOpen``.

        ``didOpen`` is a notification (no response), so we force a
        synchronous parse afterward by issuing ``documentSymbol`` on
        each newly-opened file. Without this, ``textDocument/references``
        on the target sees a project that's only been parsed up to the
        target file itself — sibling files don't show up as reference
        sources until they've been indexed."""
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
        # Force parse by issuing one synchronous request per opened
        # file. We don't care about the response — we care that the
        # LSP has finished indexing each file before we query refs.
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

        # documentSymbol can return either DocumentSymbol[] (hierarchical,
        # has "selectionRange") or SymbolInformation[] (flat, has
        # "location"). Normalize to a flat list of top-level interesting
        # symbols.
        flat = _flatten_symbols(symbols)
        top = [s for s in flat if s["kind"] in _INTERESTING_KINDS]
        if not top:
            return ""

        out: list[str] = []
        out.append(f"// === SEMANTIC CONTEXT (lsp:{self.name} for {file.name}) ===")
        out.append("//")

        # Track sibling files that had at least one *non-import* reference
        # so we can append type definitions from those files (M10.3e).
        # Importing a symbol doesn't tell the executor anything about the
        # types in the importing file; an actual call site does.
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
            # Filter out reference lines that are just import statements.
            # phQ5 (M10.3d) showed these are noise that displaced curated
            # signal in the prompt — every import-line ref dilutes the
            # call-site density without adding information.
            filtered = [
                r for r in references
                if not _is_import_ref(_uri_to_path(r["uri"]),
                                      r["range"]["start"]["line"])
            ]
            if not filtered:
                continue
            kind_name = _KIND_NAMES.get(sym["kind"], "symbol")
            out.append(
                f"// References to {sym['name']} ({kind_name}, "
                f"{len(filtered)} results from textDocument/references):"
            )
            out.append("//")
            for ref in filtered[:_MAX_REFS_PER_SYMBOL]:
                ref_uri = ref["uri"]
                ref_path = _uri_to_path(ref_uri)
                ref_line = ref["range"]["start"]["line"]
                rel = _relative_to(ref_path, self._root)
                out.append(f"//   {rel}:{ref_line + 1}")
                snippet = _read_snippet(ref_path, ref_line,
                                        after=_SNIPPET_LINES_AFTER)
                for sl in snippet:
                    out.append(f"//       {sl.rstrip()}")
                out.append("//")
                # Note this file as worth scanning for adjacent type defs.
                if (ref_path != file.resolve()
                        and ref_path not in seen_siblings):
                    seen_siblings.add(ref_path)
                    interesting_siblings.append(ref_path)
            any_emitted = True

        if not any_emitted:
            return ""

        # M10.3e: adjacent type definitions from referenced files.
        type_def_lines = self._collect_adjacent_type_defs(
            interesting_siblings, exclude=file.resolve(),
        )
        if type_def_lines:
            out.append("// Symbols defined in referenced files:")
            out.append("//")
            for line in type_def_lines:
                out.append(f"//   {line}")
            out.append("//")

        out.append("// === END SEMANTIC CONTEXT ===")
        return "\n".join(out)

    def _collect_adjacent_type_defs(self, files: list[Path],
                                     *, exclude: Path) -> list[str]:
        """Query each referenced sibling file for its top-level Class
        definitions. Returns formatted single-line summaries — one per
        class, suffixed with ``// path:line``."""
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
                results.append(f"{signature}    // {rel}:{line_no + 1}")
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flatten_symbols(symbols: list) -> list[dict]:
    """Normalize ``DocumentSymbol[]`` or ``SymbolInformation[]`` into a
    flat list of ``{"name", "kind", "position"}``. Position is the
    cursor coordinate to use when calling ``textDocument/references``."""
    flat: list[dict] = []
    for sym in symbols:
        kind = sym.get("kind")
        name = sym.get("name", "?")
        # DocumentSymbol shape (hierarchical):
        if "selectionRange" in sym:
            pos = sym["selectionRange"]["start"]
            flat.append({"name": name, "kind": kind, "position": pos})
            for child in sym.get("children", []) or []:
                flat.extend(_flatten_symbols([child]))
        # SymbolInformation shape (flat, deprecated but still supported):
        elif "location" in sym:
            pos = sym["location"]["range"]["start"]
            flat.append({"name": name, "kind": kind, "position": pos})
    return flat


def _language_id_for(file: Path) -> str:
    suffix = file.suffix.lower()
    return {
        ".js": "javascript",
        ".jsx": "javascriptreact",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".tsx": "typescriptreact",
    }.get(suffix, "javascript")


def _path_to_uri(path: Path) -> str:
    s = str(Path(path).resolve()).replace("\\", "/")
    if not s.startswith("/"):
        s = "/" + s
    return "file://" + s


def _uri_to_path(uri: str) -> Path:
    from urllib.parse import unquote
    if uri.startswith("file:///"):
        s = unquote(uri[len("file://"):])
        # On Windows the URI looks like file:///C:/foo — drop the
        # leading slash before the drive letter.
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
    """Yield JS/TS source files under ``root`` (depth-first, ignoring
    common heavy directories). Caller is responsible for capping the
    number of files actually opened."""
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


_IMPORT_LINE_RE = re.compile(
    r"^\s*(?:import\b|export\s+\{[^}]*\}\s+from\b|export\s+\*\s+from\b"
    r"|(?:const|let|var)\s+[\w{}\s,]*=\s*require\s*\()"
)


def _is_import_ref(file: Path, line_num: int) -> bool:
    """Is the reference at ``file:line_num`` just an import or
    re-export statement? phQ5 (M10.3d) found that LSP's
    ``textDocument/references`` returns import lines as references,
    which dilutes call-site density without adding signal — every
    such ref displaces a real use site from the cap."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return False
    lines = text.splitlines()
    if line_num >= len(lines):
        return False
    return bool(_IMPORT_LINE_RE.match(lines[line_num]))


def _read_signature_line(file: Path, line_num: int) -> str:
    """Read the first non-empty line at or after ``line_num`` and
    strip it. Used for the bare class-signature line in the adjacent-
    type-defs section. Returns ``""`` on miss."""
    try:
        text = file.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = text.splitlines()
    for i in range(line_num, min(line_num + 3, len(lines))):
        stripped = lines[i].strip()
        if stripped:
            # Strip trailing `{` so we get just the declaration head.
            if stripped.endswith("{"):
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
