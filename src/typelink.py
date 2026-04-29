"""typelink.py — cross-file type/signature verifiers (Milestone 7).

Per-language extractors that produce a canonical `TypeContract` from a
source file. Used by `loom typelink` CLI verbs and by `loom_exec`'s
post-task check (gated on `LOOM_TYPELINK=1`).

Registry shape:
    VERIFIERS: dict[str, Verifier]      # keyed by fence/language name

Each verifier owns:
    extract(file_path) -> list[Symbol]  # parse the file's public surface
    diff(expected, got) -> list[Diff]   # structural diff between contracts
    additive(old, new)  -> bool         # is new a superset of old?

V1 ships:
    - python_ast (stdlib `ast`; <50ms per file)
    - dart_regex (regex over class/method declarations; <10ms per file)

Deferred to v2:
    - tsc (TypeScript via `tsc --emitDeclarationOnly`)
    - libclang (C++ via `clang.cindex`)

Failure surface for `loom_exec`:
    A `typelink_fail` outcome with a structured diff is much easier
    for an executor agent (or a calling Claude session) to act on
    than a 2 KB compile error tail.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from store import Symbol  # noqa: I100


# ---------------------------------------------------------------------------
# Diff model
# ---------------------------------------------------------------------------

@dataclass
class Diff:
    """One structural difference between two contracts."""
    kind: str                 # "missing_symbol" | "extra_symbol" | "signature_mismatch" | ...
    symbol: str               # the symbol name affected
    expected: Optional[str] = None
    got: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Verifier registry
# ---------------------------------------------------------------------------

@dataclass
class Verifier:
    """Per-language type-contract verifier."""
    name: str                                 # "python_ast", "dart_regex"
    language: str                             # "python", "dart"
    file_extensions: list[str] = field(default_factory=list)
    fence: str = ""                           # "python", "dart" — matches runners.py
    extract: Callable[[Path], list[Symbol]] = lambda p: []


def _normalize_signature(sig: str) -> str:
    """Whitespace-normalize a signature so trivial formatting differences
    don't surface as drifts."""
    return re.sub(r"\s+", " ", sig).strip()


# ---------------------------------------------------------------------------
# Python verifier (stdlib `ast`)
# ---------------------------------------------------------------------------

def _python_signature_for(node: ast.AST) -> str:
    """Render a canonical Python signature for an ast node."""
    if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
        try:
            args_str = ast.unparse(node.args)
        except Exception:
            args_str = ", ".join(a.arg for a in node.args.args)
        ret = ""
        if node.returns is not None:
            try: ret = " -> " + ast.unparse(node.returns)
            except Exception: ret = " -> ?"
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        return _normalize_signature(f"{prefix}{node.name}({args_str}){ret}")
    if isinstance(node, ast.ClassDef):
        bases = []
        for b in node.bases:
            try: bases.append(ast.unparse(b))
            except Exception: bases.append("?")
        if bases:
            return _normalize_signature(f"class {node.name}({', '.join(bases)})")
        return _normalize_signature(f"class {node.name}")
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        try: return _normalize_signature(ast.unparse(node))
        except Exception: return "<assign>"
    return "<?>"


def _python_field_for(node: ast.AST) -> Optional[Symbol]:
    """If the node is a class-level field declaration, render it as a Symbol."""
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        ann = ""
        try: ann = ast.unparse(node.annotation)
        except Exception: ann = "?"
        return Symbol(
            name=node.target.id,
            kind="field",
            signature=_normalize_signature(f"{node.target.id}: {ann}"),
            line=getattr(node, "lineno", 0),
        )
    if isinstance(node, ast.Assign):
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if len(targets) == 1:
            try: rhs = ast.unparse(node.value)
            except Exception: rhs = "?"
            return Symbol(
                name=targets[0],
                kind="field",
                signature=_normalize_signature(f"{targets[0]} = {rhs}"),
                line=getattr(node, "lineno", 0),
            )
    return None


def python_extract(file: Path) -> list[Symbol]:
    """Extract public top-level symbols (and class members) from a Python file.

    Public = doesn't start with underscore. Top-level functions, classes,
    type aliases, and assignments are captured. For classes, fields and
    methods (also non-underscore) are nested as `Symbol.parent`.
    """
    try:
        source = file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file))
    except (OSError, SyntaxError):
        return []

    symbols: list[Symbol] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            symbols.append(Symbol(
                name=node.name,
                kind="class",
                signature=_python_signature_for(node),
                line=getattr(node, "lineno", 0),
            ))
            # Walk class body for public methods + fields.
            for child in node.body:
                if (isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and not child.name.startswith("_")):
                    symbols.append(Symbol(
                        name=f"{node.name}.{child.name}",
                        kind="method",
                        signature=_python_signature_for(child),
                        parent=node.name,
                        line=getattr(child, "lineno", 0),
                    ))
                elif isinstance(child, (ast.AnnAssign, ast.Assign)):
                    fld = _python_field_for(child)
                    if fld and not fld.name.startswith("_"):
                        fld.name = f"{node.name}.{fld.name}"
                        fld.parent = node.name
                        symbols.append(fld)
        elif (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and not node.name.startswith("_")):
            symbols.append(Symbol(
                name=node.name,
                kind="function",
                signature=_python_signature_for(node),
                line=getattr(node, "lineno", 0),
            ))
        elif isinstance(node, ast.Assign):
            fld = _python_field_for(node)
            if fld and not fld.name.startswith("_"):
                fld.kind = "const"
                symbols.append(fld)
    return symbols


# ---------------------------------------------------------------------------
# Dart verifier (regex)
# ---------------------------------------------------------------------------

# These regexes target the surface our inventory benchmarks declare;
# they're not a full Dart parser. Good enough for v1 since the
# benchmarks share a stable shape.
DART_CLASS_RE = re.compile(
    r"^(?:abstract\s+)?(?:class|enum)\s+(\w+)"
    r"(?:\s*<[^>]+>)?"                 # generic type params
    r"(?:\s+(?:extends|implements|with)\s+[^{]+)?"
    r"\s*\{",
    re.MULTILINE,
)
DART_TOP_FUNC_RE = re.compile(
    r"^([\w<>?\s,]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:\{|=>)",
    re.MULTILINE,
)
DART_METHOD_RE = re.compile(
    r"^\s+(?!return|throw|if|while|for|switch|case|default|continue|"
    r"break|else|try|catch|finally|assert|do|var|final|const|late|"
    r"static|yield|await|new\b)"
    r"(?:static\s+)?([\w<>?\s,\[\]]+?)\s+(\w+)\s*\(([^)]*)\)"
    r"\s*(?:\{|=>|;)",
    re.MULTILINE,
)
DART_FIELD_RE = re.compile(
    r"^\s+(?:final\s+|const\s+|late\s+)*"  # modifiers
    r"([\w<>?\[\]]+)\s+(\w+)\s*(?:=\s*[^;]+)?;",
    re.MULTILINE,
)
DART_CONSTRUCTOR_RE = re.compile(
    r"^\s+(?:const\s+|factory\s+)?"
    r"(\w+)(?:\.(\w+))?"               # ClassName or ClassName.named
    r"\s*\(([^)]*)\)"
    r"\s*(?::\s*[^{;]+)?"              # init list
    r"\s*(?:\{|;|=>)",
    re.MULTILINE,
)


def _dart_extract_class_body(source: str, class_name: str) -> str:
    """Pull the body of `class X { ... }` out of source. Naive
    brace-matching that handles nested braces."""
    match = re.search(
        rf"(?:abstract\s+)?(?:class|enum)\s+{re.escape(class_name)}\b[^{{]*\{{",
        source,
    )
    if not match:
        return ""
    start = match.end()  # right after the opening {
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[start:i - 1] if depth == 0 else source[start:]


def _strip_dart_comments(source: str) -> str:
    """Remove // and /* */ comments without altering line numbering."""
    # Strip line comments. Replace with spaces to preserve column.
    cleaned = re.sub(
        r"//[^\n]*",
        lambda m: " " * len(m.group(0)),
        source,
    )
    # Strip block comments — collapse to spaces, keeping newlines.
    def _block(m: re.Match) -> str:
        text = m.group(0)
        return "".join("\n" if c == "\n" else " " for c in text)
    cleaned = re.sub(r"/\*.*?\*/", _block, cleaned, flags=re.DOTALL)
    return cleaned


def _extract_class_body_lines(source: str, class_name: str) -> tuple[list[str], int]:
    """Find `class X { ... }` and return (lines_inside_body, start_line).

    Brace-tracks the opening { to its matching }. Returns body lines
    along with the source line number where the body starts (1-based).
    """
    pat = re.compile(
        rf"(?:abstract\s+)?(?:class|enum)\s+{re.escape(class_name)}\b[^{{]*\{{",
    )
    m = pat.search(source)
    if not m:
        return [], 0
    start = m.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    body = source[start:i - 1] if depth == 0 else source[start:]
    start_line = source.count("\n", 0, start) + 1
    return body.split("\n"), start_line


def _balanced_paren_match(text: str, start: int) -> int:
    """Given text and position of `(`, return the index AFTER the
    matching `)`. Returns -1 if unmatched."""
    if start >= len(text) or text[start] != "(":
        return -1
    depth = 1
    i = start + 1
    while i < len(text) and depth > 0:
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        i += 1
    return i if depth == 0 else -1


def _walk_dart_declarations(text: str) -> list[tuple[str, str, str]]:
    """Find Dart declarations (return_type, name, params) at depth 0
    of `text`. Handles nested parens in params (records syntax).

    Returns list of (return_type_or_empty, name, params_string).
    Constructors are returned with empty return_type.
    """
    out: list[tuple[str, str, str]] = []
    # Pattern: optional modifiers + (return_type)? + name + (
    # We scan for `(` at depth 0 of the parent text, then walk back to
    # find the name and forward to find the balanced `)`.
    i = 0
    while i < len(text):
        if text[i] == "(":
            close = _balanced_paren_match(text, i)
            if close == -1:
                i += 1
                continue
            params = text[i + 1:close - 1]
            # Walk back from `(` to find the identifier (the method/
            # constructor name) — last word before whitespace.
            j = i
            while j > 0 and text[j - 1] in " \t":
                j -= 1
            name_end = j
            while j > 0 and (text[j - 1].isalnum() or text[j - 1] in "_."):
                j -= 1
            name_start = j
            name = text[name_start:name_end]
            # The signature is followed by `{`, `=>`, `;`, or `:`
            # (init list). For our purposes: this is a method/ctor.
            after = text[close:].lstrip()
            if after.startswith("{") or after.startswith("=>") or after.startswith(";") or after.startswith(":"):
                # Anything before the name on this line is the return type.
                # Find start-of-line for name_start.
                line_start = text.rfind("\n", 0, name_start) + 1
                ret_type_raw = text[line_start:name_start].strip()
                # Drop modifiers from the return type
                ret_type = re.sub(
                    r"^(static|final|const|late|@override|@\w+\s*)+",
                    "", ret_type_raw,
                ).strip()
                if name and not name.startswith("_") and name not in {"if", "for", "while", "switch", "return", "throw", "new", "case"}:
                    out.append((ret_type, name, params))
            i = close
        else:
            i += 1
    return out


def _dart_class_body_declarations(body: str) -> str:
    """Extract just the declaration heads from a class body, with method
    bodies elided.

    Dart uses `{` for both block bodies AND named-param lists like
    `({required this.x})`. A naive brace-tracker conflates them.
    Track parenthesis depth — `{` only opens a method body when paren
    depth is 0. When we hit a method body open, skip ahead to the
    matching `}` and replace the body with `;` so the declaration head
    survives unaltered.
    """
    out: list[str] = []
    paren = 0
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "(":
            paren += 1
            out.append(ch)
            i += 1
        elif ch == ")":
            paren -= 1
            out.append(ch)
            i += 1
        elif ch == "{" and paren == 0:
            # This is a method/constructor body. Skip to matching '}'.
            depth = 1
            j = i + 1
            while j < len(body) and depth > 0:
                c = body[j]
                if c == "{": depth += 1
                elif c == "}": depth -= 1
                j += 1
            out.append(";")  # terminate the declaration head
            i = j
        elif ch == "=" and i + 1 < len(body) and body[i + 1] == ">":
            # `=>` arrow body — skip until ';' or '}'
            j = i + 2
            while j < len(body) and body[j] not in ";}":
                j += 1
            out.append(";")
            if j < len(body) and body[j] == "}":
                # Don't consume the closing class brace
                i = j
            else:
                i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def dart_extract(file: Path) -> list[Symbol]:
    """Extract public Dart symbols. Public = doesn't start with `_`.

    Approach: brace-track. For each top-level `class X { ... }`, walk
    the body and only consider lines at brace-depth 0 of the class body.
    That excludes everything inside method bodies (which is where the
    `if(...)` / `throw X(...)` false-positives lived).
    """
    try:
        source = file.read_text(encoding="utf-8")
    except OSError:
        return []

    cleaned = _strip_dart_comments(source)
    symbols: list[Symbol] = []

    # Top-level classes / enums
    seen_classes: set[str] = set()
    for m in DART_CLASS_RE.finditer(cleaned):
        name = m.group(1)
        if name.startswith("_") or name in seen_classes:
            continue
        seen_classes.add(name)

        header_match = re.search(
            rf"^(?:abstract\s+)?(?:class|enum)\s+{re.escape(name)}\b[^{{]*",
            cleaned, re.MULTILINE,
        )
        header = header_match.group(0).strip() if header_match else f"class {name}"
        symbols.append(Symbol(
            name=name, kind="class",
            signature=_normalize_signature(header),
            line=cleaned.count("\n", 0, m.start()) + 1,
        ))

        body_lines, _ = _extract_class_body_lines(cleaned, name)
        if not body_lines:
            continue
        body_text = "\n".join(body_lines)
        # Elide method bodies so signatures survive intact.
        top_text = _dart_class_body_declarations(body_text)

        seen_methods: set[str] = set()

        # Use the balanced-paren walker — handles nested records like
        # `({String sku, int quantity})` that simple regex can't.
        for ret, mname, params in _walk_dart_declarations(top_text):
            if mname == name or mname == f"{name}":
                # Constructor (return type empty or matches class name).
                sig = _normalize_signature(f"{name}({params})")
                if sig in seen_methods:
                    continue
                seen_methods.add(sig)
                symbols.append(Symbol(
                    name=f"{name}.{name}",
                    kind="method",
                    signature=sig,
                    parent=name,
                ))
            elif "." in mname and mname.startswith(name + "."):
                # Named constructor like `Foo.fromX(...)`
                sig = _normalize_signature(f"{mname}({params})")
                if sig in seen_methods:
                    continue
                seen_methods.add(sig)
                symbols.append(Symbol(
                    name=f"{name}.{mname}",
                    kind="method",
                    signature=sig,
                    parent=name,
                ))
            else:
                if mname.startswith("_"):
                    continue
                sig = _normalize_signature(f"{ret} {mname}({params})")
                if sig in seen_methods:
                    continue
                seen_methods.add(sig)
                symbols.append(Symbol(
                    name=f"{name}.{mname}",
                    kind="method",
                    signature=sig,
                    parent=name,
                ))

        # Fields. Skip `operator` (that's a method declaration) and
        # any name we already captured as a method.
        seen_method_names = {s.name.split(".", 1)[1] for s in symbols
                              if s.kind == "method" and "." in s.name and s.parent == name}
        for fm in DART_FIELD_RE.finditer(top_text):
            ftype, fname = fm.group(1), fm.group(2)
            if (fname.startswith("_") or fname == "operator"
                    or fname in seen_method_names):
                continue
            symbols.append(Symbol(
                name=f"{name}.{fname}",
                kind="field",
                signature=_normalize_signature(f"{ftype} {fname}"),
                parent=name,
            ))

    # Top-level functions (outside any class body). Walk source and
    # only consider lines at depth 0.
    depth = 0
    for line_idx, line in enumerate(cleaned.split("\n")):
        if depth == 0:
            for fm in DART_TOP_FUNC_RE.finditer(line):
                ret, fname, params = fm.group(1).strip(), fm.group(2), fm.group(3)
                if (fname.startswith("_") or fname in seen_classes or
                        fname in {"if", "for", "while", "switch", "return"}):
                    continue
                symbols.append(Symbol(
                    name=fname, kind="function",
                    signature=_normalize_signature(f"{ret} {fname}({params})"),
                    line=line_idx + 1,
                ))
        for ch in line:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1

    return symbols


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def diff_symbols(expected: list[Symbol], got: list[Symbol]) -> list[Diff]:
    """Compute a structural diff between two symbol lists.

    Diff kinds:
      - missing_symbol  — expected has S, got does not
      - extra_symbol    — got has S, expected does not (informational)
      - signature_mismatch — same name, different signature
    """
    expected_by = {s.name: s for s in expected}
    got_by = {s.name: s for s in got}
    diffs: list[Diff] = []
    for name, exp in expected_by.items():
        if name not in got_by:
            diffs.append(Diff(
                kind="missing_symbol",
                symbol=name,
                expected=exp.signature,
                got=None,
                detail=f"expected {exp.kind} `{name}` not found",
            ))
            continue
        gv = got_by[name]
        if exp.signature != gv.signature:
            diffs.append(Diff(
                kind="signature_mismatch",
                symbol=name,
                expected=exp.signature,
                got=gv.signature,
            ))
    for name, gv in got_by.items():
        if name not in expected_by:
            diffs.append(Diff(
                kind="extra_symbol",
                symbol=name,
                got=gv.signature,
            ))
    return diffs


def is_additive(old: list[Symbol], new: list[Symbol]) -> bool:
    """True if `new` is a strict superset of `old` (only adds; doesn't
    rename or change signatures)."""
    diffs = diff_symbols(old, new)
    for d in diffs:
        if d.kind in ("missing_symbol", "signature_mismatch"):
            return False
    return True


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

VERIFIERS: dict[str, Verifier] = {
    "python_ast": Verifier(
        name="python_ast",
        language="python",
        file_extensions=[".py"],
        fence="python",
        extract=python_extract,
    ),
    "dart_regex": Verifier(
        name="dart_regex",
        language="dart",
        file_extensions=[".dart"],
        fence="dart",
        extract=dart_extract,
    ),
}


def get_verifier_for_file(file: Path) -> Optional[Verifier]:
    ext = file.suffix
    for v in VERIFIERS.values():
        if ext in v.file_extensions:
            return v
    return None


def get_verifier_for_fence(fence: str) -> Optional[Verifier]:
    for v in VERIFIERS.values():
        if v.fence == fence:
            return v
    return None


# ---------------------------------------------------------------------------
# Contract-fence extraction (Q6 default authorship path)
# ---------------------------------------------------------------------------

# Matches dart-contract / python-contract / cpp-contract fences inside
# Opus-emitted specs. The captured text is parsed by the per-language
# verifier as if it were source.
CONTRACT_FENCE_RE = re.compile(
    r"```(?P<fence>\w+)-contract\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)

# Match `### path/to/file.ext` headers in a spec (per-file sections)
SECTION_HEADER_RE = re.compile(
    r"^### ([\w/\.\-]+\.\w+)\s*$", re.MULTILINE,
)


def extract_public_api_from_spec(spec_text: str) -> dict[str, list[dict]]:
    """Parse `*-contract` fenced blocks inside per-file sections.

    Returns `{file_path: [Symbol.to_dict(), ...]}`. Each section is
    parsed by the verifier matching the fence language. If a section
    has no contract fence, it's skipped (typelink layer is opt-in
    per-file).
    """
    sections: dict[str, str] = {}
    matches = list(SECTION_HEADER_RE.finditer(spec_text))
    if not matches:
        return {}
    for i, m in enumerate(matches):
        path = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        sections[path] = spec_text[start:end]

    public_api: dict[str, list[dict]] = {}
    for path, section in sections.items():
        cm = CONTRACT_FENCE_RE.search(section)
        if not cm:
            continue
        fence_name = cm.group("fence")          # "dart", "python", "cpp", ...
        body = cm.group("body")
        verifier = get_verifier_for_fence(fence_name)
        if verifier is None:
            continue  # no extractor for this language yet
        # Write body to a temp file so the verifier can parse it.
        import tempfile
        suffix = verifier.file_extensions[0] if verifier.file_extensions else ".txt"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, encoding="utf-8", delete=False,
        ) as tmp:
            tmp.write(body)
            tmp_path = Path(tmp.name)
        try:
            symbols = verifier.extract(tmp_path)
            if symbols:
                public_api[path] = [s.to_dict() for s in symbols]
        finally:
            try: tmp_path.unlink()
            except OSError: pass
    return public_api
