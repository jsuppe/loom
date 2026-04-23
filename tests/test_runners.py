"""Tests for src/runners.py — pluggable test-runner registry."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import runners


class TestRegistry:
    def test_builtin_runners_registered(self):
        expected = {"pytest", "flutter_test", "dart_test", "vitest"}
        assert expected.issubset(set(runners.RUNNERS.keys()))

    def test_get_runner_defaults_to_pytest(self):
        assert runners.get_runner(None).name == "pytest"
        assert runners.get_runner("").name == "pytest"
        assert runners.get_runner("nonsense").name == "pytest"

    def test_runner_shape(self):
        for name, r in runners.RUNNERS.items():
            assert r.name == name
            assert r.apply_mode in ("append", "replace")
            assert callable(r.build_command)
            assert callable(r.parse)
            assert callable(r.skeleton)

    def test_pytest_is_append_others_are_replace(self):
        """Only Python can use append mode (last-def wins)."""
        assert runners.RUNNERS["pytest"].apply_mode == "append"
        assert runners.RUNNERS["flutter_test"].apply_mode == "replace"
        assert runners.RUNNERS["dart_test"].apply_mode == "replace"
        assert runners.RUNNERS["vitest"].apply_mode == "replace"


class TestPytestRunner:
    def test_command_shape(self, tmp_path):
        cmd = runners.RUNNERS["pytest"].build_command(
            "tests/test_foo.py::TestFoo", tmp_path,
        )
        assert cmd[0] == sys.executable
        assert "pytest" in " ".join(cmd)
        assert "tests/test_foo.py::TestFoo" in cmd

    def test_parse_all_pass(self):
        stdout = (
            "collected 3 items\n"
            "tests/foo.py::TestX::test_a PASSED\n"
            "tests/foo.py::TestX::test_b PASSED\n"
            "tests/foo.py::TestX::test_c PASSED\n"
            "=== 3 passed in 0.5s ===\n"
        )
        p, t, _ = runners.RUNNERS["pytest"].parse(stdout, "", 0)
        assert p == 3 and t == 3

    def test_parse_mixed(self):
        stdout = (
            "tests/foo.py::TestX::test_a PASSED\n"
            "tests/foo.py::TestX::test_b FAILED\n"
            "tests/foo.py::TestX::test_c PASSED\n"
        )
        p, t, _ = runners.RUNNERS["pytest"].parse(stdout, "", 1)
        assert p == 2 and t == 3


class TestFlutterRunner:
    """Flutter uses the Dart test reporter output format."""

    def test_command_shape(self, tmp_path):
        cmd = runners.RUNNERS["flutter_test"].build_command(
            "test/local_session_test.dart::LocalSession", tmp_path,
        )
        assert cmd[0] == "flutter"
        assert "test" in cmd
        assert "test/local_session_test.dart" in cmd
        # Name filter should use --plain-name
        assert "--plain-name" in cmd
        assert "LocalSession" in cmd

    def test_command_without_name(self, tmp_path):
        cmd = runners.RUNNERS["flutter_test"].build_command(
            "test/foo_test.dart", tmp_path,
        )
        assert "--plain-name" not in cmd

    def test_parse_mixed_dart_output(self):
        # Real dart test reporter output captured from `dart test` run.
        stdout = (
            "00:00 +0: loading test/sample_test.dart\n"
            "00:00 +0: MyGroup passes one\n"
            "00:00 +1: MyGroup passes two\n"
            "00:00 +2: MyGroup fails\n"
            "00:00 +2 -1: MyGroup fails [E]\n"
            "  Expected: <2>\n"
            "    Actual: <1>\n"
            "00:00 +2 -1: Some tests failed.\n"
        )
        p, t, _ = runners.RUNNERS["flutter_test"].parse(stdout, "", 1)
        assert p == 2 and t == 3

    def test_parse_all_pass_dart(self):
        stdout = (
            "00:00 +0: loading test/foo.dart\n"
            "00:00 +3: All tests passed!\n"
        )
        p, t, _ = runners.RUNNERS["flutter_test"].parse(stdout, "", 0)
        assert p == 3 and t == 3

    def test_parse_compile_error_falls_back_to_rc(self):
        stdout = "Failed to compile"
        p, t, _ = runners.RUNNERS["flutter_test"].parse(stdout, "", 1)
        # No summary line — we fall back to rc-based "one failure"
        assert p == 0 and t == 1


class TestVitestRunner:
    def test_command_shape(self, tmp_path):
        cmd = runners.RUNNERS["vitest"].build_command(
            "foo.test.ts::MyGroup", tmp_path,
        )
        assert "vitest" in cmd
        assert "run" in cmd
        assert "foo.test.ts" in cmd
        assert "-t" in cmd
        assert "MyGroup" in cmd

    def test_parse_mixed(self):
        # Real vitest output from the probe run (ANSI stripped).
        stdout = (
            " FAIL  sample.test.ts > MyGroup > fails\n"
            " Test Files  1 failed (1)\n"
            "      Tests  1 failed | 2 passed (3)\n"
        )
        p, t, _ = runners.RUNNERS["vitest"].parse(stdout, "", 1)
        assert p == 2 and t == 3

    def test_parse_all_pass(self):
        stdout = (
            " Test Files  1 passed (1)\n"
            "      Tests  5 passed (5)\n"
        )
        p, t, _ = runners.RUNNERS["vitest"].parse(stdout, "", 0)
        assert p == 5 and t == 5

    def test_parse_strips_ansi(self):
        """ANSI color codes shouldn't break the parser."""
        stdout = (
            "\x1b[31m Test Files \x1b[0m 1 failed\x1b[90m (1)\x1b[0m\n"
            "\x1b[31m      Tests \x1b[0m \x1b[31m1 failed\x1b[0m"
            "\x1b[2m | \x1b[22m\x1b[32m2 passed\x1b[0m\x1b[90m (3)\x1b[0m\n"
        )
        p, t, _ = runners.RUNNERS["vitest"].parse(stdout, "", 1)
        assert p == 2 and t == 3


class TestSkeletons:
    def test_pytest_skeleton_has_failing_placeholder(self):
        content = runners.RUNNERS["pytest"].skeleton("TestFoo")
        assert "class TestFoo" in content
        assert "pytest.fail" in content
        assert "import pytest" in content

    def test_dart_skeleton_has_failing_placeholder(self):
        content = runners.RUNNERS["flutter_test"].skeleton("MyGroup")
        assert "group('MyGroup'" in content
        assert "fail(" in content
        assert "package:test/test.dart" in content

    def test_vitest_skeleton_has_failing_placeholder(self):
        content = runners.RUNNERS["vitest"].skeleton("MyDescribe")
        assert "describe('MyDescribe'" in content
        assert "expect.fail" in content
        assert "from 'vitest'" in content


class TestSplitTarget:
    """Utility: split "path::name" into (path, name)."""

    def test_with_name(self):
        from runners import _split_target
        assert _split_target("a/b.py::Foo") == ("a/b.py", "Foo")

    def test_without_name(self):
        from runners import _split_target
        assert _split_target("a/b.py") == ("a/b.py", "")
