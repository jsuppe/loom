#!/usr/bin/env python3
"""
Phase C — Flutter counter multi-widget benchmark.

Tests whether the asymmetric pipeline transfers to Flutter (widget
tree, async pumps, BuildContext state) on top of the validated
pure-Dart-test path. 3 implementation files (model, widget, app);
no barrel re-export — each file is imported directly by the hidden
test.

Default executor: qwen2.5-coder:32b (matches dart-inventory escalation;
Flutter widget code requires more code-specialized capability than
qwen3.5:latest tends to deliver).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"
BENCHMARK_DIR = BAKEOFF_DIR / "benchmarks" / "flutter-counter" / "ground_truth"
HIDDEN_TEST = BENCHMARK_DIR / "tests" / "counter_test.dart"
README = BENCHMARK_DIR / "README.md"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom.store import LoomStore  # noqa
from loom import services  # noqa


PROJECT = "phC_flutter_counter_oneshot_auto"

# Topological order: model (no deps) → widget (uses model) → app (uses widget).
TARGET_FILES = [
    "lib/counter_model.dart",
    "lib/counter_widget.dart",
    "lib/counter_app.dart",
]

PUBSPEC = """name: counter_app
description: Multi-widget Flutter counter benchmark for Loom Phase C.
publish_to: none
environment:
  sdk: '>=3.4.0 <4.0.0'
  flutter: '>=3.10.0'
dependencies:
  flutter:
    sdk: flutter
dev_dependencies:
  flutter_test:
    sdk: flutter
"""

# Per-task gating tests verify the file at least imports + exposes
# basic surface area before the chain advances.
GATING_TESTS = {
    "lib/counter_model.dart": '''
import 'package:flutter_test/flutter_test.dart';
import 'package:counter_app/counter_model.dart';

void main() {
  test('CounterModel constructs with default initial 0', () {
    final m = CounterModel();
    expect(m.value, 0);
  });
  test('initial out of bounds raises ArgumentError', () {
    expect(() => CounterModel(initial: 999, max: 10),
        throwsA(isA<ArgumentError>()));
  });
}
''',
    "lib/counter_widget.dart": '''
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:counter_app/counter_widget.dart';

void main() {
  testWidgets('CounterWidget renders initial value', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(body: CounterWidget(initial: 3)),
    ));
    expect(find.text('3'), findsOneWidget);
  });
}
''',
    "lib/counter_app.dart": '''
import 'package:flutter_test/flutter_test.dart';
import 'package:counter_app/counter_app.dart';

void main() {
  testWidgets('CounterApp renders default title', (tester) async {
    await tester.pumpWidget(const CounterApp());
    expect(find.text('Counter'), findsWidgets);
  });
}
''',
}

GATING_TEST_TARGETS = {
    tf: f"test/_gate_{tf.replace('/', '_').replace('.dart', '')}.dart"
    for tf in TARGET_FILES
}


PLANNER_SYSTEM = """\
You are a senior Flutter architect writing an implementation
specification for a 3-file Flutter counter library named
`counter_app`. The downstream executor is a small local model
(qwen2.5-coder:32b by default) that will write each file in a
single replace-mode pass. Your spec must be self-contained,
exhaustive about Dart/Flutter idioms, and explicit about which
symbols live in which file.

The library is split across 3 implementation files (no barrel —
the hidden tests import each lib directly):

  lib/counter_model.dart   — pure-Dart bounds + history
  lib/counter_widget.dart  — StatefulWidget + SnackBar interaction
  lib/counter_app.dart     — top-level MaterialApp wrapper

Cross-file commitments to fix early in your spec:

  - `CounterModel` is pure-Dart (no `flutter` import). Fields:
    `int _value` (private), `final int min`, `final int max`,
    `final List<int> _history`. Constructor:
    `CounterModel({int initial = 0, this.min = -100, this.max = 100})`.
    Validates `min <= initial <= max` else throws `ArgumentError`.
    Records `initial` to `_history` on construction.
    Getters: `int get value`, `List<int> get history` (returns
    `List<int>.unmodifiable(_history)`).
    Methods:
      - `increment()` — at max throws `StateError`; else `_value += 1`
        and appends to `_history`.
      - `decrement()` — symmetric, throws at min.
      - `reset()` — sets to 0, appends 0 to history.

  - `CounterWidget extends StatefulWidget`. Constructor takes
    `int initial = 0, int min = -100, int max = 100, super.key`.
    State holds a `CounterModel` initialized in `initState` with
    `widget.initial`, `widget.min`, `widget.max`.
    Renders a `Column(mainAxisSize: MainAxisSize.min, children: ...)`
    containing:
      - `Text('${_model.value}', key: const Key('counter-value'),
         style: Theme.of(context).textTheme.headlineMedium)`
      - A `Row(mainAxisAlignment: MainAxisAlignment.center, children: [
         TextButton(key: Key('btn-dec'), ...),
         TextButton(key: Key('btn-reset'), ...),
         TextButton(key: Key('btn-inc'), ...),
        ])`
    Increment/decrement wrap the model call in `try/catch` on
    `StateError`. On catch, show a SnackBar via
    `ScaffoldMessenger.of(context).showSnackBar(...)` with key
    `Key('snack-inc')` / `Key('snack-dec')`. Reset always succeeds.
    Use `setState(() { ... })` for state updates.

  - `CounterApp extends StatelessWidget`. Constructor takes
    `int initial = 0, int min = -100, int max = 100,
     String title = 'Counter', super.key`.
    Returns a `MaterialApp(title: title, theme: ThemeData(useMaterial3: true),
     home: Scaffold(appBar: AppBar(title: Text(title)),
     body: Center(child: CounterWidget(initial: initial, min: min, max: max))))`.

Critical Flutter specifics for the executor:
  - `import 'package:flutter/material.dart';` for Material widgets
  - `ScaffoldMessenger.of(context).showSnackBar(SnackBar(...))` —
    NOT `Scaffold.of(context)` (deprecated)
  - `Theme.of(context).textTheme.headlineMedium` not `headline4`
  - `super.key` shorthand in const constructors
  - `Key('...')` widget keys live on `key:` named param

For each file, give:
  - imports needed (with full package paths)
  - public class signatures with full constructor params
  - field declarations (typed, defaults where applicable)
  - method bodies described concretely (not pseudocode)

Output ONE ```text``` code block containing the spec. Inside,
organize as 3 sections each labeled exactly `### lib/<path>.dart`,
in the listed order.
"""


def call_opus(prompt: str, model: str = "opus") -> dict:
    args = [
        "claude", "-p",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", PLANNER_SYSTEM,
    ]
    t0 = time.time()
    proc = subprocess.run(
        args, input=prompt,
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p rc={proc.returncode}\n"
                           f"stderr: {proc.stderr[-500:]}")
    data = json.loads(proc.stdout)
    return {
        "content": data.get("result", ""),
        "duration_ms": data.get("duration_ms", int(elapsed * 1000)),
        "cost_usd": data.get("total_cost_usd") or data.get("cost_usd", 0),
    }


def extract_spec(opus_response: str) -> str:
    text = opus_response.strip()
    m = re.match(
        r"^```(?:text|markdown)\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def split_spec_by_file(spec_text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    pattern = re.compile(r"^### (lib/\S+\.dart)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(spec_text))
    if not matches:
        return {f: spec_text for f in TARGET_FILES}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_text)
        sections[m.group(1)] = spec_text[start:end].strip()
    for f in TARGET_FILES:
        sections.setdefault(f, spec_text)
    return sections


def parse_flutter_test(stdout: str) -> tuple[int, int]:
    """Parse `flutter test` output for passed and total counts."""
    last_line = ""
    for line in stdout.splitlines():
        if "+" in line and ":" in line:
            last_line = line
    m_pass = re.search(r"\+(\d+)", last_line)
    m_fail = re.search(r"-(\d+)", last_line)
    p = int(m_pass.group(1)) if m_pass else 0
    f = int(m_fail.group(1)) if m_fail else 0
    return p, p + f


def grade(workspace: Path) -> dict:
    """Run the hidden test suite via `flutter test`."""
    grade_dir = Path(tempfile.mkdtemp(prefix="phC_flutter_grade_"))
    shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
    (grade_dir / "test").mkdir(exist_ok=True)
    shutil.copy(HIDDEN_TEST, grade_dir / "test" / "counter_test.dart")
    pub_get = subprocess.run(
        ["flutter", "pub", "get"], cwd=grade_dir,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if pub_get.returncode != 0:
        return {"passed": 0, "total": 17,
                "error": f"flutter pub get failed: {pub_get.stderr[-500:]}",
                "grade_dir": str(grade_dir)}
    proc = subprocess.run(
        ["flutter", "test", "test/counter_test.dart"],
        cwd=grade_dir, capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    p, total = parse_flutter_test(proc.stdout)
    if total == 0:
        total = 17
    return {
        "passed": p, "total": total,
        "pass_rate": p / total if total else 0,
        "stdout_tail": proc.stdout[-2500:],
        "grade_dir": str(grade_dir),
    }


def setup_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="phC_flutter_"))
    (ws / "lib").mkdir()
    (ws / "test").mkdir()
    (ws / "pubspec.yaml").write_text(PUBSPEC, encoding="utf-8")
    (ws / ".loom-config.json").write_text(
        json.dumps({"test_runner": "flutter_test", "model": "qwen2.5-coder:32b"},
                   indent=2),
        encoding="utf-8",
    )
    for tf in TARGET_FILES:
        (ws / tf).write_text("", encoding="utf-8")
    for tf, gate_path in GATING_TEST_TARGETS.items():
        (ws / gate_path).write_text(GATING_TESTS[tf], encoding="utf-8")
    pub = subprocess.run(
        ["flutter", "pub", "get"], cwd=ws,
        capture_output=True, text=True, timeout=300,
        encoding="utf-8", errors="replace",
        shell=(sys.platform == "win32"),
    )
    if pub.returncode != 0:
        raise RuntimeError(f"flutter pub get failed in workspace: {pub.stderr[-500:]}")
    return ws


def run_one(run_id: str = "1") -> dict:
    t0 = time.time()
    workspace = setup_workspace()
    print(f"[setup] workspace: {workspace}")

    store_dir = Path.home() / ".openclaw" / "loom" / PROJECT
    if store_dir.exists():
        shutil.rmtree(store_dir)
    store = LoomStore(project=PROJECT)

    # Step 1: Opus authors the spec.
    cached_path = os.environ.get("PHC_INV_CANONICAL_SPEC", "").strip()
    if cached_path and Path(cached_path).exists():
        opus_t0 = time.time()
        raw_response = Path(cached_path).read_text(encoding="utf-8")
        opus_elapsed = time.time() - opus_t0
        opus_resp = {"content": raw_response,
                     "duration_ms": int(opus_elapsed * 1000),
                     "cost_usd": 0.0}
        print(f"[opus] cached spec from {cached_path}  raw_chars={len(raw_response)}")
    else:
        readme = README.read_text(encoding="utf-8")
        planner_prompt = (
            f"Below is the README for a 3-file Flutter counter library "
            f"named `counter_app`. Write a complete implementation spec, "
            f"organized as 3 `### lib/<path>.dart` sections so a downstream "
            f"executor can produce each file in a single replace pass. "
            f"Output ONLY a ```text``` block.\n\n"
            f"---README---\n{readme}\n---END README---"
        )
        opus_t0 = time.time()
        opus_resp = call_opus(planner_prompt)
        opus_elapsed = time.time() - opus_t0
        print(f"[opus] {opus_elapsed:.1f}s  cost=${opus_resp['cost_usd']:.4f}")

    spec_text = extract_spec(opus_resp["content"])
    sections = split_spec_by_file(spec_text)
    print(f"[opus] spec_chars={len(spec_text)}  sections={len(sections)}")

    # Step 2: Loom seeding
    req = services.extract(
        store, domain="behavior",
        value="Implement the flutter-counter 3-file library as specified.",
        rationale="Phase C flutter-counter benchmark — multi-widget Flutter "
                  "with StatefulWidget + SnackBar + MaterialApp.",
    )
    spec = services.spec_add(store, req["req_id"], spec_text)

    task_ids = []
    for i, tf in enumerate(TARGET_FILES):
        depends = [task_ids[i - 1]] if task_ids else []
        result = services.task_add(
            store,
            parent_spec=spec["spec_id"],
            title=f"Implement {tf} per the section labeled `### {tf}` in the spec",
            files_to_modify=[tf],
            test_to_write=GATING_TEST_TARGETS[tf],
            context_reqs=[req["req_id"]],
            context_specs=[spec["spec_id"]],
            context_files=[tf],
            depends_on=depends,
            size_budget_files=1,
            size_budget_loc=300,
            created_by="opus_planner_flutter_counter",
        )
        task_ids.append(result["id"])

    # Step 3: loom_exec drains the queue using the flutter_test runner.
    exec_t0 = time.time()
    exec_proc = subprocess.run(
        [sys.executable, str(LOOM_DIR / "scripts" / "loom_exec"),
         "--next", "--loop",
         "--model", os.environ.get("PHC_EXEC_MODEL", "qwen2.5-coder:32b"),
         "-p", PROJECT, "--target-dir", str(workspace),
         ],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=1800,
    )
    exec_elapsed = time.time() - exec_t0
    print(f"[exec] {exec_elapsed:.1f}s rc={exec_proc.returncode}")
    print("\n".join(exec_proc.stdout.splitlines()[-30:]))

    # Step 4: hidden grading
    g = grade(workspace)
    print(f"[grade] pass={g['passed']}/{g['total']}")

    file_sizes = {}
    for tf in TARGET_FILES:
        p = workspace / tf
        if p.exists():
            file_sizes[tf] = len(p.read_text(encoding="utf-8"))

    summary = {
        "phase": "C_flutter_counter_oneshot_auto",
        "run_id": run_id,
        "benchmark": "flutter-counter",
        "planner": "opus(claude -p)",
        "executor": os.environ.get("PHC_EXEC_MODEL", "qwen2.5-coder:32b"),
        "passed": g["passed"], "total": g["total"],
        "pass_rate": g["pass_rate"],
        "opus_duration_s": round(opus_elapsed, 1),
        "opus_cost_usd": opus_resp["cost_usd"],
        "spec_chars": len(spec_text),
        "exec_duration_s": round(exec_elapsed, 1),
        "exec_rc": exec_proc.returncode,
        "wall_s": round(time.time() - t0, 1),
        "workspace": str(workspace),
        "grade_dir": g["grade_dir"],
        "file_sizes": file_sizes,
        "spec_sections_found": list(sections.keys()),
        "exec_stdout_tail": "\n".join(exec_proc.stdout.splitlines()[-50:]),
        "grade_stdout_tail": g.get("stdout_tail", ""),
    }
    out_path = OUT_DIR / f"phC_flutter_run{run_id}_summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSUMMARY: pass={g['passed']}/{g['total']}  "
          f"opus=${opus_resp['cost_usd']:.4f}+{opus_elapsed:.1f}s  "
          f"qwen={exec_elapsed:.1f}s  wall={summary['wall_s']}s")
    print(f"wrote: {out_path}")
    return summary


if __name__ == "__main__":
    rid = sys.argv[1] if len(sys.argv) > 1 else "smoke"
    run_one(rid)
