"""
Loom templates — customizable project scaffolds for ``loom init --template``.

A template is a directory containing:

    manifest.yaml       name, description, variables[]
    files/              the scaffold — copied verbatim (with variable
                        substitution) into the target dir

Templates are discovered in two locations, in order:

    1. ~/.loom/templates/<name>/         (user-authored — wins)
    2. <loom-repo>/templates/<name>/     (shipped with loom)

The shipped templates are references, not the canonical set. Users are
expected to fork them — the whole point of template support is to be
customizable (see feedback_scaffolding memory).

Variable substitution is simple ``{{ key }}`` string replacement — not
Jinja. If you need conditionals or loops, the template pattern is wrong
for your case; write a code generator instead.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ``{{ key }}`` — allow whitespace, require an identifier. No nested
# braces, no conditionals.
VAR_PATTERN = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


@dataclass
class TemplateVariable:
    name: str
    prompt: str | None = None
    default: str | None = None


@dataclass
class Template:
    name: str
    path: Path
    description: str = ""
    variables: list[TemplateVariable] = field(default_factory=list)

    @property
    def files_dir(self) -> Path:
        return self.path / "files"


def user_templates_dir() -> Path:
    return Path.home() / ".loom" / "templates"


def shipped_templates_dir() -> Path:
    # src/templates.py → <loom-repo>/templates
    return Path(__file__).resolve().parent.parent / "templates"


def _load_manifest(template_dir: Path) -> dict[str, Any]:
    """Read manifest.yaml. Returns empty dict if missing/malformed."""
    manifest_path = template_dir / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    try:
        import yaml as _yaml
        raw = _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _manifest_to_template(name: str, template_dir: Path) -> Template:
    manifest = _load_manifest(template_dir)
    variables: list[TemplateVariable] = []
    for v in manifest.get("variables") or []:
        if not isinstance(v, dict) or not v.get("name"):
            continue
        variables.append(TemplateVariable(
            name=str(v["name"]),
            prompt=v.get("prompt"),
            default=(str(v["default"]) if v.get("default") is not None else None),
        ))
    return Template(
        name=name,
        path=template_dir,
        description=str(manifest.get("description", "")),
        variables=variables,
    )


def list_templates() -> list[Template]:
    """Discover all templates; user-authored shadow shipped ones by name."""
    by_name: dict[str, Template] = {}
    # Shipped first so user-authored overrides them.
    for root in (shipped_templates_dir(), user_templates_dir()):
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            if not (entry / "manifest.yaml").exists():
                continue
            by_name[entry.name] = _manifest_to_template(entry.name, entry)
    return list(by_name.values())


def load_template(name: str) -> Template:
    """Return the Template named ``name``.

    Raises LookupError if no template with that name exists in either
    search path. User-authored takes precedence over shipped.
    """
    for root in (user_templates_dir(), shipped_templates_dir()):
        candidate = root / name
        if (candidate / "manifest.yaml").exists():
            return _manifest_to_template(name, candidate)
    raise LookupError(f"template {name!r} not found")


def required_variables(template: Template, provided: dict[str, str]) -> list[TemplateVariable]:
    """Variables declared in the manifest that were not provided and have no default."""
    missing: list[TemplateVariable] = []
    for v in template.variables:
        if v.name in provided:
            continue
        if v.default is not None:
            continue
        missing.append(v)
    return missing


def _substitute(text: str, variables: dict[str, str]) -> str:
    def _sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))  # leave unknown placeholders intact
    return VAR_PATTERN.sub(_sub, text)


def _is_probably_text(path: Path, chunk_size: int = 4096) -> bool:
    """Heuristic: a file is text iff its first chunk decodes as UTF-8 and
    has no NUL bytes. Good enough for scaffolds."""
    try:
        chunk = path.read_bytes()[:chunk_size]
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def render_template(
    template: Template,
    target_dir: Path | str,
    variables: dict[str, str],
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copy template ``files/`` into target_dir, substituting variables.

    Applies ``{{ key }}`` substitution to text files and to file/directory
    *names* (so a file called ``{{ pkg }}.py`` becomes ``myapp.py``).
    Binary files are copied as-is.

    By default refuses to overwrite any existing file in target_dir —
    returns the list of conflicts in ``skipped``. Pass ``overwrite=True``
    to force.

    Returns:
        {
            "written":  [str],   # relative paths of files created
            "skipped":  [str],   # relative paths that already existed
            "variables_applied": {...}  # the substitutions used
        }
    """
    td = Path(target_dir).expanduser().resolve()
    if not td.is_dir():
        raise NotADirectoryError(f"target_dir does not exist: {td}")

    src = template.files_dir
    if not src.is_dir():
        raise FileNotFoundError(
            f"template {template.name!r} has no files/ directory at {src}"
        )

    # Apply substitution on merged vars: explicit + manifest defaults.
    merged: dict[str, str] = {}
    for v in template.variables:
        if v.default is not None:
            merged[v.name] = v.default
    merged.update(variables)

    written: list[str] = []
    skipped: list[str] = []

    for root, dirs, files in os.walk(src):
        root_path = Path(root)
        rel_root = root_path.relative_to(src)
        # Substitute directory names
        rendered_rel = Path(*[_substitute(part, merged) for part in rel_root.parts])
        out_root = td / rendered_rel
        out_root.mkdir(parents=True, exist_ok=True)
        # Keep os.walk from descending into ignored dirs (none for now).
        dirs.sort()

        for fname in sorted(files):
            src_file = root_path / fname
            rendered_name = _substitute(fname, merged)
            dest_file = out_root / rendered_name
            rel_display = str(dest_file.relative_to(td)).replace("\\", "/")

            if dest_file.exists() and not overwrite:
                skipped.append(rel_display)
                continue

            if _is_probably_text(src_file):
                content = src_file.read_text(encoding="utf-8")
                dest_file.write_text(_substitute(content, merged), encoding="utf-8")
            else:
                shutil.copy2(src_file, dest_file)
            written.append(rel_display)

    return {
        "written": written,
        "skipped": skipped,
        "variables_applied": merged,
    }
