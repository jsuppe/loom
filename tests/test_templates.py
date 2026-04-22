"""Tests for src/templates.py — discovery, manifest parse, render."""

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import templates as tpl


def _write_template(root: Path, name: str, manifest: str, files: dict[str, str]):
    """Helper: create a template directory with a manifest + file tree."""
    td = root / name
    td.mkdir(parents=True)
    (td / "manifest.yaml").write_text(manifest, encoding="utf-8")
    files_dir = td / "files"
    files_dir.mkdir()
    for rel, content in files.items():
        dest = files_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    return td


class TestDiscovery:
    def test_list_includes_shipped(self):
        # python-minimal is shipped in the repo
        names = {t.name for t in tpl.list_templates()}
        assert "python-minimal" in names

    def test_list_requires_manifest(self, monkeypatch):
        """A directory under templates/ without manifest.yaml is ignored."""
        with tempfile.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            # Make a fake user template WITHOUT a manifest
            (user_path / "broken").mkdir()
            (user_path / "broken" / "files").mkdir()
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            names = {t.name for t in tpl.list_templates()}
            assert "broken" not in names

    def test_user_template_overrides_shipped(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            # Shadow the shipped python-minimal
            _write_template(
                user_path, "python-minimal",
                manifest="name: python-minimal\ndescription: custom override\n",
                files={"hello.txt": "hi"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("python-minimal")
            assert "override" in t.description

    def test_load_unknown_raises(self):
        with pytest.raises(LookupError):
            tpl.load_template("does-not-exist")


class TestManifest:
    def test_variables_parsed(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            _write_template(
                user_path, "v-test",
                manifest=textwrap.dedent("""
                    name: v-test
                    description: has vars
                    variables:
                      - name: a
                        prompt: say a
                        default: one
                      - name: b
                    """).strip() + "\n",
                files={"f.txt": "{{ a }} {{ b }}"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("v-test")
            assert [v.name for v in t.variables] == ["a", "b"]
            assert t.variables[0].default == "one"
            assert t.variables[1].default is None

    def test_required_variables_filters_out_defaults_and_provided(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            _write_template(
                user_path, "reqs",
                manifest=textwrap.dedent("""
                    name: reqs
                    variables:
                      - {name: a, default: x}
                      - {name: b}
                      - {name: c}
                    """).strip() + "\n",
                files={"f.txt": "noop"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("reqs")
            missing = tpl.required_variables(t, {"c": "hello"})
            assert [v.name for v in missing] == ["b"]


class TestRender:
    def test_basic_substitution(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "sub",
                manifest="name: sub\nvariables:\n  - {name: app_name}\n",
                files={"README.md": "# {{ app_name }}\n"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("sub")
            result = tpl.render_template(t, target, {"app_name": "coolapp"})
            content = (Path(target) / "README.md").read_text(encoding="utf-8")
            assert content == "# coolapp\n"
            assert "README.md" in result["written"]
            assert result["skipped"] == []

    def test_substitution_in_file_and_dir_names(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "names",
                manifest="name: names\nvariables:\n  - {name: pkg}\n",
                files={"src/{{ pkg }}/__init__.py": "'''{{ pkg }}'''\n"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("names")
            tpl.render_template(t, target, {"pkg": "myapp"})
            rendered = Path(target) / "src" / "myapp" / "__init__.py"
            assert rendered.exists()
            assert rendered.read_text(encoding="utf-8") == "'''myapp'''\n"

    def test_defaults_used_when_var_absent(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "def",
                manifest="name: def\nvariables:\n  - {name: who, default: world}\n",
                files={"greeting.txt": "hello {{ who }}"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("def")
            tpl.render_template(t, target, {})
            assert (Path(target) / "greeting.txt").read_text(encoding="utf-8") == "hello world"

    def test_unknown_placeholder_left_intact(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "unk",
                manifest="name: unk\n",
                files={"f.txt": "{{ not_declared }}"},
            )
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("unk")
            tpl.render_template(t, target, {})
            assert (Path(target) / "f.txt").read_text(encoding="utf-8") == "{{ not_declared }}"

    def test_refuses_to_overwrite_by_default(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "ovr",
                manifest="name: ovr\n",
                files={"existing.txt": "from-template"},
            )
            target_path = Path(target)
            (target_path / "existing.txt").write_text("user-edit", encoding="utf-8")
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("ovr")
            result = tpl.render_template(t, target, {})
            # User's content preserved
            assert (target_path / "existing.txt").read_text(encoding="utf-8") == "user-edit"
            assert "existing.txt" in result["skipped"]
            assert result["written"] == []

    def test_overwrite_true_replaces_existing(self, monkeypatch):
        with tempfile.TemporaryDirectory() as user_root, \
             tempfile.TemporaryDirectory() as target:
            user_path = Path(user_root)
            _write_template(
                user_path, "ovr2",
                manifest="name: ovr2\n",
                files={"existing.txt": "from-template"},
            )
            (Path(target) / "existing.txt").write_text("user-edit", encoding="utf-8")
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("ovr2")
            result = tpl.render_template(t, target, {}, overwrite=True)
            assert (Path(target) / "existing.txt").read_text(encoding="utf-8") == "from-template"
            assert "existing.txt" in result["written"]


class TestShippedPythonMinimal:
    """Smoke-test the shipped starter against a temp dir."""

    def test_renders_cleanly(self):
        t = tpl.load_template("python-minimal")
        with tempfile.TemporaryDirectory() as target:
            result = tpl.render_template(
                t, target,
                {"app_name": "demoapp", "description": "test",
                 "author": "jon", "python_version": "3.10"},
            )
            assert result["skipped"] == []
            # Package directory should have the rendered name
            pkg_init = Path(target) / "src" / "demoapp" / "__init__.py"
            assert pkg_init.exists()
            assert "demoapp" in pkg_init.read_text(encoding="utf-8")
            # pyproject references the variables
            pyproj = (Path(target) / "pyproject.toml").read_text(encoding="utf-8")
            assert 'name = "demoapp"' in pyproj
            assert 'requires-python = ">=3.10"' in pyproj
