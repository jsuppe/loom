"""
LSP-backed semantic indexer for C and C++.

Wraps ``clangd`` over JSON-RPC to surface call-site / type-definition
context for ``loom_exec``. Implementation mirrors
:mod:`loom.indexers_js` exactly — same lifecycle, same message framing,
same context shape — so the architectural review of JsIndexer transfers
to this module.

The differences are all C++-specific:

* Server: ``clangd --background-index --header-insertion=never``
* File globs: ``.cpp / .cxx / .cc / .c / .hpp / .hxx / .hh / .h``
* LanguageId: ``cpp`` for C++ extensions, ``c`` for ``.c`` / ``.h``
* Project priming: clangd auto-discovers ``compile_commands.json``;
  we still explicitly ``didOpen`` the workspace files so the LSP keeps
  them resident.

Pre-registration anchor: ``experiments/m28_clangd_indexer/PRE_REGISTRATION.md``
locks the contract this module must satisfy on the M28 S1 C++ smoke —
the output shape must mirror the M10.2 ``StubCppIndexer`` (call sites
+ type definitions + enclosing function bodies, 500-4000 chars).

Install requirement::

    # Windows
    scoop install llvm
    # macOS
    brew install llvm
    # Ubuntu/Debian
    sudo apt install clangd-17

If ``clangd`` isn't on PATH the indexer fails soft — first call warns
once and returns ``""``, matching the NoOpIndexer contract.
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
import time
import warnings
import weakref
from pathlib import Path
from typing import Optional

from loom.indexers import SemanticIndexer


# How long to wait after priming files before issuing queries. clangd's
# background indexer scans the project asynchronously after each
# textDocument/didOpen; queries issued before indexing settles can return
# empty references results.
#
# Validated empirically against the M28 S1 C++ smoke (2 files, header
# + test): with 0s sleep, references for fetchWithRetry returned empty
# (only doFetch was emitted). With 1.5s, both functions returned the
# expected refs. The pre-registered smoke uses the same default; larger
# projects can override via LOOM_CLANGD_WARM_SLEEP_S.
_DEFAULT_WARM_SLEEP_S = 1.5


_DEFAULT_BINARY = "clangd"

# Snippet shape mirrors the M10.2 StubCppIndexer's reference output:
# the stub embedded the surrounding function body at each call site
# (~4 lines after each ref) so the executor could read the contract
# in context. We match that here.
_SNIPPET_LINES_AFTER = 4

# Caps. The S1 scenario has 1 target file with 1 symbol (fetchWithRetry)
# and a handful of refs. Real C++ projects can have thousands. Bounded
# at the JsIndexer-validated caps which produced the M10.3e +40pp lift
# on JS — same shape, same bounds.
_MAX_SYMBOLS_PER_FILE = 5
_MAX_REFS_PER_SYMBOL = 5
_MAX_TYPE_DEFS_PER_FILE = 5

# Project priming cap — generous enough for typical Loom-target C++
# projects, bounded enough that Boost-style template-heavy codebases
# don't OOM clangd on init. Pre-registered risk callout in M28
# PRE_REGISTRATION.md.
_MAX_PROJECT_FILES = 200

_PROJECT_GLOB_SUFFIXES = (
    ".cpp", ".cxx", ".cc",
    ".c",
    ".hpp", ".hxx", ".hh",
    ".h",
)
_PROJECT_GLOB_IGNORE_DIRS = {
    ".git", "build", "build-debug", "build-release", "out",
    "third_party", "vendor", "external", "node_modules",
    "cmake-build-debug", "cmake-build-release",
}

# LSP SymbolKind constants relevant for C/C++. Same numeric set as
# JsIndexer — they're standardized in the LSP spec.
# https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#symbolKind
_KIND_CLASS = 5
_KIND_METHOD = 6
_KIND_FUNCTION = 12
_KIND_STRUCT = 23  # C++-specific addition vs JsIndexer
_INTERESTING_KINDS = {_KIND_CLASS, _KIND_METHOD, _KIND_FUNCTION, _KIND_STRUCT}
_KIND_NAMES = {
    _KIND_CLASS: "class",
    _KIND_METHOD: "method",
    _KIND_FUNCTION: "function",
    _KIND_STRUCT: "struct",
}

# Type-def section uses these symbol kinds.
_TYPE_DEF_KINDS = {_KIND_CLASS, _KIND_STRUCT}


_LIVE_INSTANCES: "weakref.WeakSet[ClangdIndexer]" = weakref.WeakSet()


@atexit.register
def _shutdown_all() -> None:
    for inst in list(_LIVE_INSTANCES):
        try:
            inst.shutdown()
        except Exception:
            pass


class ClangdIndexer(SemanticIndexer):
    """LSP-backed indexer for C and C++ via ``clangd``.

    Requires ``compile_commands.json`` at the project root (or in
    ``build/``) — clangd auto-discovers it.

    Parameters
    ----------
    root:
        Project root. Defaults to ``Path.cwd()``. clangd is initialized
        with this as ``rootUri``.
    server_cmd:
        Override the launch command (for testing).
    """

    name = "clangd"
    languages = ("cpp", "c", "c++", "cxx", "h", "hpp")

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
                    f"ClangdIndexer: language server unavailable, "
                    f"returning empty context. Install with `scoop "
                    f"install llvm` (Windows), `brew install llvm` "
                    f"(macOS), or `apt install clangd-17` "
                    f"(Debian/Ubuntu). ({e})",
                    RuntimeWarning, stacklevel=2,
                )
                return ""
            try:
                return self._build_context(Path(file))
            except Exception as e:
                warnings.warn(
                    f"ClangdIndexer: error building context for {file}: {e}",
                    RuntimeWarning, stacklevel=2,
                )
                return ""

    def health(self) -> dict:
        """Probe whether clangd is reachable on PATH.

        Does NOT spawn the LSP — that's deferred to first
        ``context_for`` call. ``loom indexer-doctor`` invokes this for
        a fast pre-flight check.
        """
        if self._server_cmd_override:
            cmd = self._server_cmd_override[0]
            return {"ok": True, "detail": f"server_cmd override: {cmd}"}
        path = shutil.which(_DEFAULT_BINARY)
        if path is None:
            return {
                "ok": False,
                "detail": (
                    f"{_DEFAULT_BINARY} not found on PATH. Install via "
                    f"`scoop install llvm` (Windows) / `brew install "
                    f"llvm` (macOS) / `apt install clangd-17` "
                    f"(Debian/Ubuntu)."
                ),
            }
        # Verify compile_commands.json exists somewhere clangd will find
        # it — saves the user a confusing "indexer returned nothing"
        # debug session.
        cdb_candidates = [
            self._root / "compile_commands.json",
            self._root / "build" / "compile_commands.json",
        ]
        cdb_path = next((c for c in cdb_candidates if c.exists()), None)
        if cdb_path is None:
            return {
                "ok": False,
                "detail": (
                    f"compile_commands.json not found at "
                    f"{self._root}/compile_commands.json or "
                    f"{self._root}/build/compile_commands.json. "
                    f"clangd will fall back to default flags and may "
                    f"produce empty context. Generate via your build "
                    f"system: `cmake -B build -DCMAKE_EXPORT_COMPILE_"
                    f"COMMANDS=ON` for CMake projects."
                ),
            }
        return {
            "ok": True,
            "detail": f"binary: {path}; compile_commands: {cdb_path}",
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
        path = shutil.which(_DEFAULT_BINARY)
        if path is None:
            raise FileNotFoundError(
                f"{_DEFAULT_BINARY} not found on PATH"
            )
        # --background-index: clangd scans the project and builds an
        #     index in the background; speeds up cross-file references.
        # --header-insertion=never: don't auto-insert headers; we want
        #     a query interface, not a code-completion experience.
        # --log=error: suppress chatty info-level logging on stderr.
        return [path, "--background-index", "--header-insertion=never",
                "--log=error"]

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
        content_length = 0
        # Read headers until blank line.
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError(
                    "clangd terminated unexpectedly while reading headers"
                )
            line_str = line.decode("ascii", errors="replace").rstrip("\r\n")
            if not line_str:
                break
            if line_str.lower().startswith("content-length:"):
                content_length = int(line_str.split(":", 1)[1].strip())
        body = self._proc.stdout.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _send_request(self, method: str, params: Optional[dict]):
        req_id = self._next_id
        self._next_id += 1
        msg: dict = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        self._send_message(msg)
        # Drain notifications and other requests until we get our reply.
        # clangd emits a lot of $/progress and textDocument/publishDiagnostics
        # notifications during background indexing; skip them.
        while True:
            reply = self._read_message()
            if reply.get("id") == req_id:
                if "error" in reply:
                    raise RuntimeError(
                        f"clangd error on {method}: {reply['error']}"
                    )
                return reply.get("result")
            # Otherwise: notification or unrelated request, drop.

    def _send_notification(self, method: str, params: Optional[dict]) -> None:
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send_message(msg)

    # ------------------------------------------------------------------
    # File-open / project warm-up
    # ------------------------------------------------------------------

    def _open_file(self, file: Path) -> None:
        resolved = file.resolve()
        if resolved in self._opened:
            return
        try:
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise OSError(f"can't read {file}: {e}")
        self._send_notification("textDocument/didOpen", {
            "textDocument": {
                "uri": _path_to_uri(resolved),
                "languageId": _language_id_for(resolved),
                "version": 1,
                "text": text,
            },
        })
        self._opened.add(resolved)

    def _warm_project(self) -> None:
        """Eagerly open every C/C++ file in the project up to the cap.

        clangd's background index will find them too, but explicit
        ``didOpen`` ensures they're loaded by the time we issue queries.
        """
        opened_count = len(self._opened)
        if opened_count >= _MAX_PROJECT_FILES:
            return
        for path in _walk_project(self._root):
            if opened_count >= _MAX_PROJECT_FILES:
                break
            try:
                self._open_file(path)
                opened_count += 1
            except OSError:
                continue

    # ------------------------------------------------------------------
    # Context assembly — the load-bearing piece per the M28 pre-reg
    # ------------------------------------------------------------------

    def _build_context(self, file: Path) -> str:
        if not file.exists():
            return ""
        self._warm_project()
        self._open_file(file)
        # Wait for clangd's background index to settle. Without this,
        # textDocument/references can return empty results — validated
        # against the M28 S1 C++ smoke.
        sleep_s = float(
            os.environ.get("LOOM_CLANGD_WARM_SLEEP_S", _DEFAULT_WARM_SLEEP_S)
        )
        if sleep_s > 0:
            time.sleep(sleep_s)
        symbols = self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": _path_to_uri(file)},
        }) or []

        flat = _flatten_symbols(symbols)
        top = [s for s in flat if s["kind"] in _INTERESTING_KINDS]
        if not top:
            return ""

        out: list[str] = []
        out.append(
            f"// === SEMANTIC CONTEXT (lsp:{self.name} for {file.name}) ==="
        )
        out.append("//")

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
            kind_name = _KIND_NAMES.get(sym["kind"], "symbol")
            out.append(
                f"// References to {sym['name']} ({kind_name}, "
                f"{len(references)} results from textDocument/references):"
            )
            out.append("//")
            for ref in references[:_MAX_REFS_PER_SYMBOL]:
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
            out.append("// Symbols defined in referenced files:")
            out.append("//")
            for line in type_def_lines:
                out.append(f"//   {line}")
            out.append("//")

        out.append("// === END SEMANTIC CONTEXT ===")
        return "\n".join(out)

    def _collect_adjacent_type_defs(self, files: list[Path],
                                     *, exclude: Path) -> list[str]:
        """Query each referenced sibling file for its top-level
        class/struct definitions. Returns formatted single-line summaries.
        """
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
            type_defs = [s for s in flat if s["kind"] in _TYPE_DEF_KINDS]
            if not type_defs:
                continue
            rel = _relative_to(sibling, self._root)
            for td in type_defs[:_MAX_TYPE_DEFS_PER_FILE]:
                line_no = td["position"]["line"]
                signature = _read_signature_line(sibling, line_no)
                if not signature:
                    continue
                results.append(f"{signature}    // {rel}:{line_no + 1}")
        return results


# ---------------------------------------------------------------------------
# Helpers (mirrors of JsIndexer's helpers; lifted-and-adapted for C/C++)
# ---------------------------------------------------------------------------


def _flatten_symbols(symbols: list) -> list[dict]:
    """Normalize DocumentSymbol[] (hierarchical) or SymbolInformation[]
    (flat) into a flat list of ``{name, kind, position}`` dicts.

    ``position`` always points at the symbol's NAME (not its body) so
    refs land correctly.
    """
    flat: list[dict] = []
    for sym in symbols:
        if "selectionRange" in sym:
            # DocumentSymbol shape
            flat.append({
                "name": sym["name"],
                "kind": sym["kind"],
                "position": sym["selectionRange"]["start"],
            })
            for child in sym.get("children", []) or []:
                if "selectionRange" in child:
                    flat.append({
                        "name": child["name"],
                        "kind": child["kind"],
                        "position": child["selectionRange"]["start"],
                    })
        elif "location" in sym:
            # SymbolInformation shape — has body-range, not name-range
            flat.append({
                "name": sym["name"],
                "kind": sym["kind"],
                "position": sym["location"]["range"]["start"],
            })
    return flat


_CPP_EXTENSIONS = {".cpp", ".cxx", ".cc", ".hpp", ".hxx", ".hh"}
_C_EXTENSIONS = {".c", ".h"}


def _language_id_for(file: Path) -> str:
    ext = file.suffix.lower()
    if ext in _CPP_EXTENSIONS:
        return "cpp"
    if ext in _C_EXTENSIONS:
        # ``.h`` is ambiguous (C vs C++). clangd's compile_commands.json
        # entry resolves it via the TU that includes it. We label as
        # ``c`` here; clangd's CDB lookup wins.
        return "c"
    return "cpp"  # default


def _path_to_uri(path: Path) -> str:
    resolved = path.resolve()
    s = resolved.as_posix()
    if not s.startswith("/"):
        s = "/" + s
    return "file://" + s


def _uri_to_path(uri: str) -> Path:
    if uri.startswith("file:///"):
        raw = uri[len("file:///"):]
    elif uri.startswith("file://"):
        raw = uri[len("file://"):]
    else:
        raw = uri
    # Windows drive letters come through as /C:/... — strip leading
    # slash so pathlib treats it as an absolute path.
    if re.match(r"^/[A-Za-z]:/", raw):
        raw = raw[1:]
    return Path(raw)


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _walk_project(root: Path):
    """Yield each project source file, capped at _MAX_PROJECT_FILES."""
    yielded = 0
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune ignored dirs in-place to skip descending.
        dirnames[:] = [
            d for d in dirnames if d not in _PROJECT_GLOB_IGNORE_DIRS
        ]
        for name in filenames:
            if Path(name).suffix.lower() in _PROJECT_GLOB_SUFFIXES:
                yield Path(dirpath) / name
                yielded += 1
                if yielded >= _MAX_PROJECT_FILES:
                    return


def _read_signature_line(file: Path, line_num: int) -> str:
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
    lines = text.splitlines()
    if 0 <= line_num < len(lines):
        return lines[line_num].rstrip()
    return ""


def _read_snippet(file: Path, line: int, *, before: int = 0,
                  after: int = 4) -> list[str]:
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    lines = text.splitlines()
    start = max(0, line - before)
    end = min(len(lines), line + after + 1)
    return lines[start:end]
