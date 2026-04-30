"""Tests for src/templates.py — discovery, manifest parse, render."""

import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from loom import templates as tpl


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


class TestConfigOverrides:
    """Templates can declare config_overrides in manifest.yaml."""

    def test_manifest_without_overrides_yields_empty_dict(self, monkeypatch):
        import tempfile as _tmp
        with _tmp.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            (user_path / "plain").mkdir()
            (user_path / "plain" / "manifest.yaml").write_text(
                "name: plain\n", encoding="utf-8",
            )
            (user_path / "plain" / "files").mkdir()
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("plain")
            assert t.config_overrides == {}

    def test_manifest_overrides_loaded(self, monkeypatch):
        import tempfile as _tmp
        with _tmp.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            (user_path / "dartish").mkdir()
            (user_path / "dartish" / "manifest.yaml").write_text(
                "name: dartish\n"
                "config_overrides:\n"
                "  test_runner: dart_test\n"
                "  language: dart\n"
                "  test_dir: test\n",
                encoding="utf-8",
            )
            (user_path / "dartish" / "files").mkdir()
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("dartish")
            assert t.config_overrides == {
                "test_runner": "dart_test",
                "language": "dart",
                "test_dir": "test",
            }

    def test_malformed_overrides_ignored(self, monkeypatch):
        """If config_overrides is a list/string instead of a dict, we treat
        it as empty rather than crashing."""
        import tempfile as _tmp
        with _tmp.TemporaryDirectory() as user_root:
            user_path = Path(user_root)
            (user_path / "bad").mkdir()
            (user_path / "bad" / "manifest.yaml").write_text(
                "name: bad\n"
                "config_overrides:\n"
                "  - not_a_dict\n",
                encoding="utf-8",
            )
            (user_path / "bad" / "files").mkdir()
            monkeypatch.setattr(tpl, "user_templates_dir", lambda: user_path)
            t = tpl.load_template("bad")
            assert t.config_overrides == {}


class TestShippedNonPythonStarters:
    """One test per new starter: renders cleanly and declares the right runner."""

    def _render(self, name, vars_):
        t = tpl.load_template(name)
        target = tempfile.mkdtemp()
        result = tpl.render_template(t, target, vars_)
        return t, Path(target), result

    def test_dart_minimal_renders(self):
        t, target, result = self._render(
            "dart-minimal",
            {"app_name": "mydart", "description": "x",
             "author": "a", "sdk_constraint": "^3.0.0"},
        )
        assert t.config_overrides["test_runner"] == "dart_test"
        assert t.config_overrides["language"] == "dart"
        assert t.config_overrides["test_dir"] == "test"
        assert (target / "pubspec.yaml").exists()
        assert "name: mydart" in (target / "pubspec.yaml").read_text(encoding="utf-8")
        lib = (target / "lib" / "mydart.dart").read_text(encoding="utf-8")
        assert "library mydart" in lib
        test_content = (target / "test" / "smoke_test.dart").read_text(encoding="utf-8")
        assert "package:mydart/mydart.dart" in test_content

    def test_flutter_minimal_renders(self):
        t, target, result = self._render(
            "flutter-minimal",
            {"app_name": "myflutter", "description": "x",
             "author": "a", "sdk_constraint": "^3.0.0"},
        )
        assert t.config_overrides["test_runner"] == "flutter_test"
        assert t.config_overrides["language"] == "dart"
        assert t.config_overrides["test_dir"] == "test"
        assert (target / "pubspec.yaml").exists()
        assert "flutter:\n    sdk: flutter" in (target / "pubspec.yaml").read_text(encoding="utf-8")
        main_dart = (target / "lib" / "main.dart").read_text(encoding="utf-8")
        assert "'myflutter'" in main_dart
        widget_test = (target / "test" / "widget_test.dart").read_text(encoding="utf-8")
        assert "package:myflutter/main.dart" in widget_test

    def test_typescript_minimal_renders(self):
        t, target, result = self._render(
            "typescript-minimal",
            {"app_name": "myts", "description": "x",
             "author": "a", "node_engine": ">=20"},
        )
        assert t.config_overrides["test_runner"] == "vitest"
        assert t.config_overrides["language"] == "typescript"
        assert t.config_overrides["test_dir"] == "tests"
        pkg = (target / "package.json").read_text(encoding="utf-8")
        assert '"name": "myts"' in pkg
        assert "vitest" in pkg
        assert (target / "tsconfig.json").exists()
        idx = (target / "src" / "index.ts").read_text(encoding="utf-8")
        assert "myts" in idx

    def test_all_new_starters_in_list(self):
        names = {t.name for t in tpl.list_templates()}
        assert {"python-minimal", "dart-minimal", "flutter-minimal",
                "typescript-minimal"}.issubset(names)
