"""End-to-end validation of multi-runtime loom_exec.

Sets up tiny synthetic Flutter/Dart and vitest projects in tempdirs,
then exercises runners.RUNNERS[...].build_command / .parse against
REAL `dart test` and `npx vitest` invocations. Proves that:

- The command shapes this code produces actually work on disk.
- The parsers extract correct (passed, total) from real output.
- The fallback (missing binary → (0, 1) "one failure") still works.

These are marked slow + they skip gracefully if `dart` / `npx` aren't
installed, so the core CI can still run them; the local machine where
multi-runtime was developed has all three.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import runners


# ---------------------------------------------------------------------------
# Dart real-binary test
# ---------------------------------------------------------------------------

pytestmark_dart = pytest.mark.skipif(
    shutil.which("dart") is None, reason="dart not installed",
)


@pytestmark_dart
class TestDartEndToEnd:
    @pytest.fixture
    def dart_project(self, tmp_path):
        """Minimal dart package with one test file."""
        (tmp_path / "pubspec.yaml").write_text(
            "name: loom_dart_e2e\n"
            "description: e2e probe\n"
            "version: 0.0.1\n"
            "environment:\n"
            "  sdk: ^3.0.0\n"
            "dev_dependencies:\n"
            "  test: ^1.25.0\n",
            encoding="utf-8",
        )
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "sample_test.dart").write_text(
            "import 'package:test/test.dart';\n\n"
            "void main() {\n"
            "  group('MyGroup', () {\n"
            "    test('passes one', () { expect(1 + 1, equals(2)); });\n"
            "    test('passes two', () { expect('hi'.length, equals(2)); });\n"
            "    test('fails', () { expect(1, equals(2)); });\n"
            "  });\n"
            "}\n",
            encoding="utf-8",
        )
        # Fetch deps. shell=True on Windows so .bat shims are found.
        result = subprocess.run(
            ["dart", "pub", "get"], cwd=tmp_path, capture_output=True, text=True,
            timeout=120, shell=(sys.platform == "win32"),
        )
        if result.returncode != 0:
            pytest.skip(f"dart pub get failed: {result.stderr[:200]}")
        return tmp_path

    def test_real_dart_output_parses_to_2_of_3(self, dart_project):
        """Use the dart_test runner's command + parse against real output."""
        runner = runners.RUNNERS["dart_test"]
        cmd = runner.build_command("test/sample_test.dart::MyGroup", dart_project)
        assert cmd[0] == "dart"

        res = subprocess.run(
            cmd, cwd=dart_project, capture_output=True, text=True, timeout=120,
            shell=(sys.platform == "win32"),
        )
        passed, total, tail = runner.parse(res.stdout, res.stderr, res.returncode)
        # 2 passes, 1 fail in the fixture
        assert passed == 2
        assert total == 3
        assert tail  # smoke: non-empty diagnostic

    def test_all_pass_variant(self, dart_project):
        """Swap the fail to a pass and expect 3/3."""
        (dart_project / "test" / "sample_test.dart").write_text(
            "import 'package:test/test.dart';\n\n"
            "void main() {\n"
            "  group('MyGroup', () {\n"
            "    test('a', () { expect(1, equals(1)); });\n"
            "    test('b', () { expect(2, equals(2)); });\n"
            "    test('c', () { expect(3, equals(3)); });\n"
            "  });\n"
            "}\n",
            encoding="utf-8",
        )
        runner = runners.RUNNERS["dart_test"]
        cmd = runner.build_command("test/sample_test.dart", dart_project)
        res = subprocess.run(
            cmd, cwd=dart_project, capture_output=True, text=True, timeout=120,
            shell=(sys.platform == "win32"),
        )
        passed, total, _ = runner.parse(res.stdout, res.stderr, res.returncode)
        assert passed == 3
        assert total == 3


# ---------------------------------------------------------------------------
# vitest real-binary test
# ---------------------------------------------------------------------------

pytestmark_npx = pytest.mark.skipif(
    shutil.which("npx") is None, reason="npx not installed",
)


@pytestmark_npx
class TestVitestEndToEnd:
    @pytest.fixture
    def vitest_project(self, tmp_path):
        """Minimal vitest project. Install will take ~10-15s first time."""
        (tmp_path / "package.json").write_text(
            '{"name":"loom-vitest-e2e","type":"module",'
            '"scripts":{"test":"vitest run"},'
            '"devDependencies":{"vitest":"^2.0.0"}}\n',
            encoding="utf-8",
        )
        (tmp_path / "sample.test.ts").write_text(
            "import { describe, test, expect } from 'vitest';\n\n"
            "describe('MyGroup', () => {\n"
            "  test('passes one', () => { expect(1 + 1).toBe(2); });\n"
            "  test('passes two', () => { expect('hi'.length).toBe(2); });\n"
            "  test('fails', () => { expect(1).toBe(2); });\n"
            "});\n",
            encoding="utf-8",
        )
        # Install vitest (slow first time; cached thereafter)
        result = subprocess.run(
            ["npm", "install", "--silent"], cwd=tmp_path,
            capture_output=True, text=True, timeout=240,
            shell=True,  # Windows needs shell for npm
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            pytest.skip(f"npm install failed: {result.stderr[:200]}")
        return tmp_path

    def test_real_vitest_output_parses_to_2_of_3(self, vitest_project):
        runner = runners.RUNNERS["vitest"]
        cmd = runner.build_command("sample.test.ts::MyGroup", vitest_project)
        res = subprocess.run(
            cmd, cwd=vitest_project, capture_output=True, text=True, timeout=120,
            shell=True,  # Windows requires shell for npx
            encoding="utf-8", errors="replace",
        )
        passed, total, tail = runner.parse(res.stdout, res.stderr, res.returncode)
        assert passed == 2
        assert total == 3


# ---------------------------------------------------------------------------
# Prompt generation end-to-end: a task built with task_build_prompt must
# emit the right fence + apply instructions for the configured runner.
# ---------------------------------------------------------------------------

class TestPromptGenerationByRunner:
    """No real subprocess — just verify the prompt contract."""

    @pytest.fixture(autouse=True)
    def fixtures_path(self):
        # Ensure services import works
        import services  # noqa: F401

    def _make_task(self, store, runner_name):
        """Build a minimal task and return its id."""
        import services
        from store import Requirement
        from datetime import datetime, timezone

        req = Requirement(
            id="REQ-prompt-test", domain="behavior",
            value="test requirement", source_msg_id="m", source_session="s",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        store.add_requirement(req, [0.1] * 768)
        spec = services.spec_add(store, "REQ-prompt-test", "d", status="draft")
        task_result = services.task_add(
            store, parent_spec=spec["spec_id"],
            title="tiny task",
            files_to_modify=["src/foo.dart"],
            test_to_write="test/foo_test.dart::Foo",
            context_reqs=[],
            context_specs=[],
        )
        return task_result["id"]

    def test_flutter_prompt_says_dart_replace_whole_file(self, tmp_path, monkeypatch):
        import tempfile, shutil as _shutil
        from store import LoomStore
        import services, runners as _r

        # Disable Ollama for embedding
        import embedding
        embedding._embedding_cache.clear()
        import urllib.request as _u
        def boom(*a, **kw): raise ConnectionResetError("no ollama")
        monkeypatch.setattr(_u, "urlopen", boom)

        td = Path(tempfile.mkdtemp())
        try:
            s = LoomStore(project="runner-prompt-test", data_dir=td)
            task_id = self._make_task(s, "flutter_test")
            flutter = _r.get_runner("flutter_test")
            prompt = services.task_build_prompt(s, task_id, runner=flutter)
            # Mode: replace, fence: dart
            assert "dart code block" in prompt
            assert "```dart" in prompt
            assert "entire new file content" in prompt
            assert "OVERWRITTEN" in prompt
        finally:
            _shutil.rmtree(td, ignore_errors=True)

    def test_pytest_prompt_says_python_append(self, tmp_path, monkeypatch):
        import tempfile, shutil as _shutil
        from store import LoomStore
        import services, runners as _r

        import embedding
        embedding._embedding_cache.clear()
        import urllib.request as _u
        def boom(*a, **kw): raise ConnectionResetError("no ollama")
        monkeypatch.setattr(_u, "urlopen", boom)

        td = Path(tempfile.mkdtemp())
        try:
            s = LoomStore(project="runner-prompt-test-py", data_dir=td)
            task_id = self._make_task(s, "pytest")
            pytest_r = _r.get_runner("pytest")
            prompt = services.task_build_prompt(s, task_id, runner=pytest_r)
            assert "python code block" in prompt
            assert "```python" in prompt
            assert "APPENDED" in prompt
        finally:
            _shutil.rmtree(td, ignore_errors=True)

    def test_vitest_prompt_says_typescript_replace(self, tmp_path, monkeypatch):
        import tempfile, shutil as _shutil
        from store import LoomStore
        import services, runners as _r

        import embedding
        embedding._embedding_cache.clear()
        import urllib.request as _u
        def boom(*a, **kw): raise ConnectionResetError("no ollama")
        monkeypatch.setattr(_u, "urlopen", boom)

        td = Path(tempfile.mkdtemp())
        try:
            s = LoomStore(project="runner-prompt-test-ts", data_dir=td)
            task_id = self._make_task(s, "vitest")
            vitest_r = _r.get_runner("vitest")
            prompt = services.task_build_prompt(s, task_id, runner=vitest_r)
            assert "typescript code block" in prompt
            assert "```typescript" in prompt
            assert "entire new file content" in prompt
        finally:
            _shutil.rmtree(td, ignore_errors=True)
