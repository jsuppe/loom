"""
Loom executor — run a Task against a local Ollama model.

Default model: qwen3.5:latest (validated in experiments/gaps/FINDINGS.md).
Override with $LOOM_EXECUTOR_MODEL.

MVP scope (matches what the benchmarks validated):
  - Single-turn prompt to Ollama
  - Assumes the model outputs a ```python``` code block to APPEND to the
    first file in task.files_to_modify (the benchmark pattern). Multi-file
    diff application is a future extension.
  - Stop-token and test-result classifier drives the reject/escalate path.

Usage:
    loom_exec <TASK-id>                 # run one task
    loom_exec --next                    # claim and run the next ready task
    loom_exec --next --loop             # drain the ready queue
    loom_exec --dry-run <TASK-id>       # print prompt, don't call Ollama

Environment:
    LOOM_EXECUTOR_MODEL   Default: qwen3.5:latest
    OLLAMA_URL            Default: http://localhost:11434
    LOOM_PROJECT          Override project detection (store name)
    LOOM_TARGET_DIR       Override target repo root (where code is read/written).
                          Default: current working directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 on stdout/stderr so emoji etc. don't crash on Windows cp1252.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from loom.store import LoomStore  # noqa: E402
from loom import services  # noqa: E402
from loom import runners  # noqa: E402
from loom import config as loom_config  # noqa: E402


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
FALLBACK_EXECUTOR_MODEL = "qwen3.5:latest"

# Directories that should never be copied into the scratch grading dir —
# either because they're huge, irrelevant, or they'd break pytest discovery.
SCRATCH_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", ".venv", "venv", ".pytest_cache",
    "node_modules", "*.pyc", ".tox", "dist", "build", ".mypy_cache",
    ".claude", ".worktrees",
)


def resolve_target_dir(arg_value: str | None) -> Path:
    """Where is the target repo's source rooted? Separate from the Loom store."""
    if arg_value:
        return Path(arg_value).expanduser().resolve()
    if env := os.environ.get("LOOM_TARGET_DIR"):
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()

GENERIC_BLOCK_RE = re.compile(r"```\s*\n(.*?)\n```", re.DOTALL)
STOP_TOKEN_RE = re.compile(r"\b(TASK_REJECT|NEED_CONTEXT|DONE)\s*:\s*([^\n]+)", re.IGNORECASE)


def _fenced_block_re(fence: str) -> re.Pattern[str]:
    return re.compile(rf"```{re.escape(fence)}\s*\n(.*?)\n```", re.DOTALL)


def get_project_name() -> str:
    if env := os.environ.get("LOOM_PROJECT"):
        return env
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return "default"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    """Single-turn Ollama chat. Returns content + token counts + elapsed.

    Keeps the model resident via `keep_alive` (default 30m, override
    with $LOOM_OLLAMA_KEEP_ALIVE) so chained executor calls don't pay
    cold-load latency between tasks. Retries transient 5xx / connection
    errors twice with 5s/15s backoff to ride through Ollama mid-load
    races (model eviction, VRAM contention).
    """
    keep_alive = os.environ.get("LOOM_OLLAMA_KEEP_ALIVE", "30m")
    payload = json.dumps({
        "model": model,
        "stream": False,
        "think": False,
        "keep_alive": keep_alive,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 6000},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    backoffs = [5, 15]
    last_err: Exception | None = None
    for attempt in range(len(backoffs) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode())
            elapsed = time.perf_counter() - t0
            msg = body.get("message", {}) or {}
            return {
                "content": msg.get("content", ""),
                "elapsed_s": round(elapsed, 2),
                "input_tokens": body.get("prompt_eval_count", 0),
                "output_tokens": body.get("eval_count", 0),
            }
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (500, 502, 503, 504) or attempt == len(backoffs):
                raise
        except urllib.error.URLError as e:
            last_err = e
            if attempt == len(backoffs):
                raise
        time.sleep(backoffs[attempt])
    raise RuntimeError(f"Ollama call failed after retries: {last_err}")


def extract_code(content: str, fence: str = "python") -> str | None:
    """Pull the code block out of the LLM response.

    Prefers a fenced block tagged with ``fence`` (``python``, ``dart``,
    ``typescript``, ``javascript``); falls back to any fenced block.
    """
    m = _fenced_block_re(fence).search(content)
    if m:
        return m.group(1).rstrip() + "\n"
    # javascript and typescript are interchangeable in practice — many
    # small models emit ```js even for TS files.
    if fence == "typescript":
        m = _fenced_block_re("javascript").search(content) or _fenced_block_re("js").search(content) or _fenced_block_re("ts").search(content)
        if m:
            return m.group(1).rstrip() + "\n"
    m = GENERIC_BLOCK_RE.search(content)
    if m:
        return m.group(1).rstrip() + "\n"
    return None


def classify_response(content: str, fence: str = "python") -> tuple[str, str]:
    """Return (kind, detail) where kind is one of:
        done, task_reject, need_context, no_code, unknown
    """
    stop_match = STOP_TOKEN_RE.search(content)
    if stop_match:
        kind = stop_match.group(1).lower()
        detail = stop_match.group(2).strip()
        if kind == "task_reject":
            return "task_reject", detail
        if kind == "need_context":
            return "need_context", detail
        if kind == "done":
            # Still need to verify code was produced + tests pass.
            pass

    if not extract_code(content, fence=fence):
        return "no_code", "response contained no code block"

    return "done", "code block extracted"


def _log_path(store: LoomStore) -> Path:
    return store.data_dir / ".exec-log.jsonl"


def _log_run(store: LoomStore, record: dict) -> None:
    path = _log_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")


def apply_code(
    task: dict,
    code: str,
    target_dir: Path,
    apply_mode: str = "append",
) -> Path:
    """Write the model's code to the first file_to_modify.

    apply_mode:
        "append"  — append to existing file (Python last-definition-wins).
        "replace" — overwrite the entire file (required for Dart/TS/etc.
                    where classes and exports can't be redefined).
    """
    if not task["files_to_modify"]:
        raise ValueError("task has no files_to_modify")
    target = Path(task["files_to_modify"][0])
    if not target.is_absolute():
        target = target_dir / target
    target.parent.mkdir(parents=True, exist_ok=True)
    if apply_mode == "replace":
        target.write_text(code, encoding="utf-8")
    else:
        existing = target.read_text(encoding="utf-8") if target.exists() else ""
        target.write_text(existing + "\n\n" + code, encoding="utf-8")
    return target


def static_check(
    runner: "runners.Runner",
    scratch_dir: Path,
    target_file: str,
) -> tuple[bool, str]:
    """Per-language static-analysis pass on the just-written file.

    Returns (ok, error_tail). Runs between apply_code and grading when
    LOOM_EXEC_STATIC_CHECK=1 is set in the env. The intent is to catch
    deterministic structural errors (missing required getter, stripped
    `const`, unbalanced types) cheaply, before the grader spends a
    full compile cycle on the same diagnosis.

    Per fence:
      - dart:    `dart analyze --fatal-warnings <target>`
      - python:  `ast.parse` on the source (syntax only)
      - c++/cpp: `g++ -fsyntax-only -std=c++20 -I include <target>`
      - others:  skip (returns (True, "skipped"))

    A missing toolchain (no `dart` on PATH, no `g++`) returns ok=True
    with a "skipped" reason rather than failing the task, so the
    static-check feature is graceful when it can't run.
    """
    target = scratch_dir / target_file
    if not target.exists():
        return False, f"target file does not exist: {target}"

    fence = runner.fence
    if fence == "dart":
        try:
            res = subprocess.run(
                ["dart", "analyze", "--fatal-warnings", str(target)],
                cwd=scratch_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
                shell=(sys.platform == "win32"),
            )
            if res.returncode == 0:
                return True, ""
            return False, (res.stdout + res.stderr)[-1500:]
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return True, f"dart not available; skipping: {e}"

    if fence == "python":
        import ast
        try:
            ast.parse(target.read_text(encoding="utf-8"))
            return True, ""
        except SyntaxError as e:
            return False, f"python syntax error: {e}"

    if fence in ("c++", "cpp"):
        try:
            res = subprocess.run(
                ["g++", "-fsyntax-only", "-std=c++20", "-I", "include", str(target)],
                cwd=scratch_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=60,
                shell=(sys.platform == "win32"),
            )
            if res.returncode == 0:
                return True, ""
            return False, res.stderr[-1500:]
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            return True, f"g++ unavailable; skipping: {e}"

    return True, f"no static check for fence={fence}; skipping"


def run_grading(
    test_target: str, cwd: Path, runner: runners.Runner,
) -> tuple[int, int, str]:
    """Dispatch grading through the registered runner.

    Returns (passed, total, tail). The runner owns command shape and
    result parsing — we just subprocess + hand off the raw output.
    """
    cmd = runner.build_command(test_target, cwd)
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=180,
            # Windows cp1252 crashes on non-Latin-1 bytes from npx/dart; force
            # utf-8 and replace undecodable bytes so the parse step sees text.
            encoding="utf-8",
            errors="replace",
            # Native launchers (dart.bat, npx.cmd) need shell=True on Windows.
            shell=(sys.platform == "win32"),
        )
    except FileNotFoundError as e:
        # The runner's binary isn't on PATH. Surface as a failed run so
        # the caller's test_fail path kicks in.
        tail = f"grading command failed to launch: {e}\ncmd: {' '.join(cmd)}"
        return 0, 1, tail
    return runner.parse(res.stdout, res.stderr, res.returncode)


def execute_task(
    store: LoomStore,
    task_id: str,
    model: str,
    target_dir: Path,
    dry_run: bool = False,
    runner: runners.Runner | None = None,
) -> dict:
    """Run one task through claim -> prompt -> apply -> grade -> complete/reject."""
    t0 = time.perf_counter()
    task = services.task_get(store, task_id)
    if runner is None:
        runner = runners.get_runner("pytest")  # last-resort default
    print(f"[exec] task {task_id}  status={task['status']}  "
          f"title={task['title']!r}")
    print(f"[exec] target_dir: {target_dir}  runner: {runner.name} ({runner.apply_mode})")

    prompt = services.task_build_prompt(
        store, task_id, target_dir=target_dir, runner=runner,
    )
    print(f"[exec] prompt: {len(prompt)} chars")

    if dry_run:
        print("--- PROMPT (dry-run) ---")
        print(prompt)
        print("--- END PROMPT ---")
        return {"task_id": task_id, "dry_run": True}

    # Claim (transitions pending -> claimed).
    if task["status"] == "pending":
        services.task_claim(store, task_id, claimed_by=model)
        print(f"[exec] claimed by {model}")
    elif task["status"] != "claimed" or task["claimed_by"] != model:
        return {
            "task_id": task_id,
            "error": f"task is in status={task['status']!r}, cannot execute",
        }

    # Scratch dir: copy the target repo so we can apply + grade without
    # polluting the working tree. On success we promote the modified file
    # back; on failure we throw the scratch away.
    scratch = Path(tempfile.mkdtemp(prefix="loom_exec_"))
    try:
        # copytree refuses an existing dest; remove the one mkdtemp made.
        scratch.rmdir()
        shutil.copytree(target_dir, scratch, ignore=SCRATCH_IGNORE)

        # Call the model.
        print(f"[exec] calling {model}...")
        try:
            llm = call_ollama(model, prompt)
        except Exception as e:
            reason = f"ollama call failed: {e}"
            services.task_reject(store, task_id, reason, escalate=True)
            return {"task_id": task_id, "outcome": "llm_error", "reason": reason}

        print(f"[exec] model: {llm['elapsed_s']:.1f}s  "
              f"in={llm['input_tokens']}  out={llm['output_tokens']}")

        kind, detail = classify_response(llm["content"], fence=runner.fence)
        if kind == "task_reject":
            services.task_reject(store, task_id, f"TASK_REJECT: {detail}", escalate=False)
            _log_run(store, {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id, "model": model, "outcome": "task_reject",
                "reason": detail, "elapsed_s": round(time.perf_counter() - t0, 2),
                "input_tokens": llm["input_tokens"], "output_tokens": llm["output_tokens"],
            })
            return {"task_id": task_id, "outcome": "task_reject", "reason": detail}

        if kind == "need_context":
            services.task_reject(store, task_id, f"NEED_CONTEXT: {detail}", escalate=True)
            _log_run(store, {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id, "model": model, "outcome": "need_context",
                "reason": detail, "elapsed_s": round(time.perf_counter() - t0, 2),
                "input_tokens": llm["input_tokens"], "output_tokens": llm["output_tokens"],
            })
            return {"task_id": task_id, "outcome": "need_context", "reason": detail}

        if kind == "no_code":
            services.task_reject(store, task_id, "no code block in response", escalate=True)
            _log_run(store, {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id, "model": model, "outcome": "no_code",
                "elapsed_s": round(time.perf_counter() - t0, 2),
                "input_tokens": llm["input_tokens"], "output_tokens": llm["output_tokens"],
            })
            return {"task_id": task_id, "outcome": "no_code"}

        # Apply code to scratch copy of the target.
        scratch_target = scratch / Path(task["files_to_modify"][0])
        code = extract_code(llm["content"], fence=runner.fence)
        scratch_target.parent.mkdir(parents=True, exist_ok=True)
        if runner.apply_mode == "replace":
            scratch_target.write_text(code, encoding="utf-8")
        else:
            existing = scratch_target.read_text(encoding="utf-8") if scratch_target.exists() else ""
            scratch_target.write_text(existing + "\n\n" + code, encoding="utf-8")

        # Optional language-aware static check before grading. Catches
        # deterministic structural errors (missing required getter,
        # stripped `const`, unbalanced types) cheaply, with a clearer
        # error tail than waiting for the grader to fail at file load.
        # Off by default; opt in via LOOM_EXEC_STATIC_CHECK=1.
        if os.environ.get("LOOM_EXEC_STATIC_CHECK", "0") == "1":
            sc_ok, sc_tail = static_check(
                runner, scratch, task["files_to_modify"][0])
            if not sc_ok:
                print(f"[exec] static_check: FAIL")
                print(f"[exec] static_check tail: {sc_tail[:300]}")
                services.task_reject(
                    store, task_id, f"static_check fail:\n{sc_tail}",
                    escalate=True)
                _log_run(store, {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "task_id": task_id, "model": model,
                    "outcome": "static_fail",
                    "tail": sc_tail[-500:],
                    "elapsed_s": round(time.perf_counter() - t0, 2),
                    "input_tokens": llm["input_tokens"],
                    "output_tokens": llm["output_tokens"],
                })
                return {
                    "task_id": task_id, "outcome": "static_fail",
                    "tail": sc_tail,
                }
            print(f"[exec] static_check: ok")

        # Grade in scratch.
        passed, total, tail = run_grading(task["test_to_write"], cwd=scratch, runner=runner)
        print(f"[exec] grading: {passed}/{total}")

        if total > 0 and passed == total:
            # Promote scratch changes back to the real working tree.
            real_target = target_dir / task["files_to_modify"][0]
            real_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(scratch_target, real_target)
            services.task_complete(store, task_id)
            _log_run(store, {
                "ts": datetime.now(timezone.utc).isoformat(),
                "task_id": task_id, "model": model, "outcome": "complete",
                "passed": passed, "total": total,
                "elapsed_s": round(time.perf_counter() - t0, 2),
                "input_tokens": llm["input_tokens"], "output_tokens": llm["output_tokens"],
            })
            return {
                "task_id": task_id, "outcome": "complete",
                "passed": passed, "total": total,
                "modified_file": str(real_target),
            }

        # Test failures -> escalate so human/Opus can look.
        reason = f"test fail: {passed}/{total}\n{tail}"
        services.task_reject(store, task_id, reason, escalate=True)
        _log_run(store, {
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id, "model": model, "outcome": "test_fail",
            "passed": passed, "total": total,
            "elapsed_s": round(time.perf_counter() - t0, 2),
            "input_tokens": llm["input_tokens"], "output_tokens": llm["output_tokens"],
        })
        return {
            "task_id": task_id, "outcome": "test_fail",
            "passed": passed, "total": total, "tail": tail,
        }

    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="loom_exec",
        description="Loom executor",
    )
    parser.add_argument("task_id", nargs="?", help="Task id to execute")
    parser.add_argument("--next", action="store_true",
                        help="Auto-pick the next ready task from the queue")
    parser.add_argument("--loop", action="store_true",
                        help="With --next: drain the queue (stop on empty/failure)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print assembled prompt without calling the model")
    parser.add_argument(
        "--model", default=None,
        help="Ollama model. Precedence: --model > $LOOM_EXECUTOR_MODEL > "
             ".loom-config.json > qwen3.5:latest.",
    )
    parser.add_argument("-p", "--project", default=None, help="Project name (store)")
    parser.add_argument(
        "--target-dir", default=None,
        help="Target repo root — where source files are read and written. "
             "Defaults to $LOOM_TARGET_DIR, else the current working directory.",
    )
    args = parser.parse_args()

    target_dir = resolve_target_dir(args.target_dir)
    if not target_dir.is_dir():
        print(f"[exec] target-dir does not exist: {target_dir}", file=sys.stderr)
        return 2

    # Load the per-target config (empty dict if none). Precedence for every
    # setting: CLI flag > env var > config file > built-in default.
    from loom import config as _config
    cfg = _config.load_config(target_dir)

    project = _config.resolve(
        "project",
        cli=args.project,
        env_var="LOOM_PROJECT",
        config=cfg,
        default=None,
    ) or get_project_name()

    model = _config.resolve(
        "executor_model",
        cli=args.model,
        env_var="LOOM_EXECUTOR_MODEL",
        config=cfg,
        default=FALLBACK_EXECUTOR_MODEL,
    )

    # Pick the test runner for this target. Unknown values fall back to
    # pytest with a warning so the tool never silently mis-runs tests.
    runner_name = cfg.get("test_runner") or "pytest"
    if runner_name not in runners.RUNNERS:
        print(f"[exec] unknown test_runner {runner_name!r} in config — "
              f"falling back to pytest", file=sys.stderr)
    runner = runners.get_runner(runner_name)

    store = LoomStore(project)

    if args.next:
        while True:
            ready = services.task_list(store, ready_only=True)
            if not ready:
                print("[exec] no ready tasks")
                break
            task_id = ready[0]["id"]
            result = execute_task(store, task_id, model, target_dir,
                                  dry_run=args.dry_run, runner=runner)
            print(f"[exec] result: {json.dumps(result)}")
            if not args.loop:
                break
            if result.get("outcome") in {"task_reject", "need_context", "no_code",
                                          "test_fail", "llm_error"}:
                # Don't drain further after a failure — operator should look.
                break
        return 0

    if not args.task_id:
        parser.error("task_id required (or use --next)")

    result = execute_task(store, args.task_id, model, target_dir,
                          dry_run=args.dry_run, runner=runner)
    print(f"[exec] result: {json.dumps(result)}")
    return 0 if result.get("outcome") in {"complete", None} else 1


if __name__ == "__main__":
    sys.exit(main())
