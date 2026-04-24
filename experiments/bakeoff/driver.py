#!/usr/bin/env python3
"""
Bakeoff V1 driver.

Orchestrates a turn-based conversation between a Product Owner agent
(knows the full ground truth) and an Engineer agent (implements what
PO directs).  Two conditions:

    baseline: engineer has read_file, write_file, respond_to_po
    loom:     engineer ALSO has loom_extract / list / spec / link / check / query

Both agents run on qwen3.5:latest via Ollama.  Same model, same shape,
minus the Loom tools in the baseline.

Usage:
    python driver.py --condition {baseline|loom} --run-id <int> [--max-iters 25]

Writes a per-run JSONL log to runs/<run_id>/events.jsonl plus a
summary at runs/<run_id>/summary.json.  See PROTOCOL.md for the
metric schema.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BAKEOFF_DIR = Path(__file__).resolve().parent
LOOM_ROOT = BAKEOFF_DIR.parent.parent
GROUND_TRUTH = BAKEOFF_DIR / "ground_truth"
PROMPTS = BAKEOFF_DIR / "prompts"
RUNS_DIR = BAKEOFF_DIR / "runs"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("BAKEOFF_MODEL", "qwen3.5:latest")

# Stop-condition defaults (match PROTOCOL.md).
MAX_ITERATIONS = 25
TOKEN_BUDGET = 500_000
# No-progress fires only if the last N iterations had the SAME pass count
# AND we're not trivially at zero (so the engineer hasn't even started).
# Larger window = more patience with cross-req dependencies.
NO_PROGRESS_WINDOW = 5

# Keeps each agent-inner-loop from looping forever calling tools.
MAX_TOOL_ROUNDS_PER_TURN = 8

TOOL_BLOCK_RE = re.compile(r"```tool\s*\n(.*?)\n```", re.DOTALL)


# ============================================================
# Ollama HTTP
# ============================================================

def call_ollama(
    messages: list[dict],
    system: str,
    timeout: int = 180,
) -> dict:
    """Single /api/chat call.  Returns {content, elapsed, in, out}."""
    payload = json.dumps({
        "model": MODEL,
        "stream": False,
        "think": False,
        "messages": [{"role": "system", "content": system}] + messages,
        "options": {"temperature": 0.2, "num_predict": 3000},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", errors="replace"))
    elapsed = time.perf_counter() - t0
    msg = body.get("message", {}) or {}
    return {
        "content": msg.get("content", ""),
        "elapsed": round(elapsed, 2),
        "input_tokens": body.get("prompt_eval_count", 0),
        "output_tokens": body.get("eval_count", 0),
    }


# ============================================================
# Workspace
# ============================================================

def make_workspace(run_id: int) -> Path:
    """Create a fresh workspace with an empty task_queue.py + hidden tests."""
    ws = Path(tempfile.mkdtemp(prefix=f"bakeoff_{run_id}_"))
    (ws / "task_queue.py").write_text("", encoding="utf-8")
    # Copy the hidden ground-truth tests into place.
    shutil.copytree(GROUND_TRUTH / "tests", ws / "tests")
    return ws


def cleanup_workspace(ws: Path) -> None:
    shutil.rmtree(ws, ignore_errors=True)


# ============================================================
# Pytest runner
# ============================================================

def run_tests(workspace: Path) -> dict:
    """Returns {passed: int, total: int, per_test: {name: status}, collection_error: str|None}.

    Uses pytest -v (verbose) which emits one `test::path STATUS` line per
    test. NOT -q, whose format puts STATUS first and breaks the parser.

    Also captures collection errors (import failures, syntax errors)
    which produce rc != 0 AND zero collected tests — without this, the
    PO is told "0/0 passing" with no clue WHY.
    """
    res = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=line", "--no-header"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (res.stdout or "") + "\n" + (res.stderr or "")
    per_test: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if "::" not in line:
            continue
        m = re.search(r"(tests/[^\s]+::[A-Za-z_][\w:]+)\s+(PASSED|FAILED|ERROR)", line)
        if m:
            per_test[m.group(1)] = m.group(2)
    passed = sum(1 for v in per_test.values() if v == "PASSED")
    total = len(per_test)

    # Collection / import failure: rc != 0 but no tests parsed. Extract
    # the first informative error line (ImportError, ModuleNotFoundError,
    # SyntaxError, or the pytest ERROR marker).
    collection_error: str | None = None
    if total == 0 and res.returncode != 0:
        error_lines = []
        for line in out.splitlines():
            if any(tok in line for tok in
                   ("ImportError", "ModuleNotFoundError", "SyntaxError",
                    "AttributeError", "ERROR collecting",
                    "errors during collection", "ERRORS")):
                error_lines.append(line.strip())
        collection_error = "\n".join(error_lines[:6]) or "pytest exited with rc != 0 but no tests collected"

    return {
        "passed": passed,
        "total": total,
        "per_test": per_test,
        "rc": res.returncode,
        "collection_error": collection_error,
    }


# ============================================================
# Tool handlers (engineer side)
# ============================================================

class ToolError(Exception):
    pass


def _check_safe_path(path: str) -> None:
    """Reject anything outside the workspace root or under tests/."""
    p = Path(path)
    if p.is_absolute():
        raise ToolError(f"absolute paths not allowed: {path}")
    parts = p.parts
    if parts and parts[0] == "tests":
        raise ToolError("access to tests/ is denied — this is the hidden oracle")
    if ".." in parts:
        raise ToolError("parent-dir navigation not allowed")


def handle_read_file(workspace: Path, args: dict) -> dict:
    path = args.get("path", "")
    _check_safe_path(path)
    f = workspace / path
    if not f.exists():
        return {"ok": False, "error": f"file not found: {path}"}
    return {"ok": True, "content": f.read_text(encoding="utf-8")}


def handle_write_file(workspace: Path, args: dict) -> dict:
    path = args.get("path", "")
    content = args.get("content", "")
    _check_safe_path(path)
    f = workspace / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return {"ok": True, "bytes_written": len(content.encode("utf-8"))}


def handle_respond_to_po(workspace: Path, args: dict) -> dict:
    # Sentinel value — the turn loop watches for this.
    return {"ok": True, "_end_turn": True, "message": args.get("message", "")}


# ---- Loom tools ----

def _loom_cmd() -> list[str]:
    return [sys.executable, str(LOOM_ROOT / "scripts" / "loom")]


def _run_loom(
    store_project: str, store_dir: Path,
    args: list[str], stdin_text: str | None = None,
) -> dict:
    """Invoke loom CLI against a project-specific store.

    We override HOME so the loom store writes to store_dir/.openclaw/loom
    instead of the user's real store (keeps runs hermetic).
    """
    env = os.environ.copy()
    env["HOME"] = str(store_dir)
    env["USERPROFILE"] = str(store_dir)  # Windows
    env["PYTHONIOENCODING"] = "utf-8"
    env["LOOM_PROJECT"] = store_project
    result = subprocess.run(
        _loom_cmd() + args,
        input=stdin_text,
        cwd=store_dir,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    return {
        "rc": result.returncode,
        "stdout": (result.stdout or "").strip(),
        "stderr": (result.stderr or "").strip(),
    }


def handle_loom_extract(ctx: dict, args: dict) -> dict:
    domain = args.get("domain", "behavior")
    text = args.get("text", "").strip()
    rationale = args.get("rationale", "")
    if not text:
        return {"ok": False, "error": "text is required"}
    stdin = f"REQUIREMENT: {domain} | {text}\n"
    cmd = ["extract"]
    if rationale:
        cmd += ["--rationale", rationale]
    r = _run_loom(ctx["project"], ctx["loom_home"], cmd, stdin_text=stdin)
    # Pull REQ-id out of stdout
    req_id = None
    for line in r["stdout"].splitlines():
        m = re.search(r"(REQ-[a-f0-9]+)", line)
        if m:
            req_id = m.group(1)
            break
    return {"ok": r["rc"] == 0, "req_id": req_id, "raw": r["stdout"]}


def handle_loom_list(ctx: dict, args: dict) -> dict:
    r = _run_loom(ctx["project"], ctx["loom_home"], ["list", "--json"])
    try:
        data = json.loads(r["stdout"])
        return {"ok": True, "requirements": [
            {"id": x["id"], "domain": x["domain"], "text": x.get("text", x.get("value", ""))}
            for x in data
        ]}
    except Exception as e:
        return {"ok": False, "error": f"parse failure: {e}", "raw": r["stdout"][:400]}


def handle_loom_spec(ctx: dict, args: dict) -> dict:
    req_id = args.get("req_id", "").strip()
    desc = args.get("description", "").strip()
    criteria = args.get("criteria") or []
    if not req_id or not desc:
        return {"ok": False, "error": "req_id and description required"}
    cmd = ["spec", req_id, "-d", desc]
    for c in criteria:
        cmd += ["-c", c]
    r = _run_loom(ctx["project"], ctx["loom_home"], cmd)
    spec_id = None
    m = re.search(r"(SPEC-[a-f0-9]+)", r["stdout"])
    if m:
        spec_id = m.group(1)
    return {"ok": r["rc"] == 0, "spec_id": spec_id, "raw": r["stdout"]}


def handle_loom_link(ctx: dict, args: dict) -> dict:
    file = args.get("file", "").strip()
    req_id = args.get("req_id", "").strip()
    if not file or not req_id:
        return {"ok": False, "error": "file and req_id required"}
    cmd = ["link", file, "--req", req_id]
    r = _run_loom(ctx["project"], ctx["loom_home"], cmd)
    return {"ok": r["rc"] == 0, "raw": r["stdout"]}


def handle_loom_check(ctx: dict, args: dict) -> dict:
    file = args.get("file", "").strip()
    if not file:
        return {"ok": False, "error": "file required"}
    r = _run_loom(ctx["project"], ctx["loom_home"], ["check", file, "--json"])
    try:
        return {"ok": True, **json.loads(r["stdout"])}
    except Exception:
        return {"ok": True, "raw": r["stdout"][:400]}


def handle_loom_query(ctx: dict, args: dict) -> dict:
    q = args.get("text", "").strip()
    if not q:
        return {"ok": False, "error": "text required"}
    r = _run_loom(ctx["project"], ctx["loom_home"], ["query", q, "--json"])
    try:
        return {"ok": True, "results": json.loads(r["stdout"])}
    except Exception:
        return {"ok": True, "raw": r["stdout"][:400]}


BASELINE_TOOLS = {
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "respond_to_po": handle_respond_to_po,
}
LOOM_TOOLS = {
    "loom_extract": handle_loom_extract,
    "loom_list": handle_loom_list,
    "loom_spec": handle_loom_spec,
    "loom_link": handle_loom_link,
    "loom_check": handle_loom_check,
    "loom_query": handle_loom_query,
}


# ============================================================
# Prompt builders
# ============================================================

def build_po_system_prompt() -> str:
    template = (PROMPTS / "product_owner.md").read_text(encoding="utf-8")
    readme = (GROUND_TRUTH / "README.md").read_text(encoding="utf-8")
    return template.replace("{ground_truth_readme}", readme)


def build_engineer_system_prompt(condition: str) -> str:
    name = "engineer_loom.md" if condition == "loom" else "engineer_baseline.md"
    return (PROMPTS / name).read_text(encoding="utf-8")


# ============================================================
# Agent-turn loop (engineer)
# ============================================================

def parse_tool_calls(content: str) -> list[dict]:
    """Extract ```tool JSON blocks."""
    calls = []
    for m in TOOL_BLOCK_RE.finditer(content):
        try:
            calls.append(json.loads(m.group(1)))
        except json.JSONDecodeError:
            continue
    return calls


def engineer_turn(
    workspace: Path,
    history: list[dict],
    system: str,
    tools: dict,
    loom_ctx: dict | None,
    logger,
) -> tuple[str, int, int, int]:
    """Run the engineer's turn.  Tool-call inner loop until respond_to_po.

    Returns: (message_to_po, input_tokens, output_tokens, tool_calls_count).
    """
    in_tok = out_tok = tool_calls = 0
    message_to_po = ""
    round_idx = 0

    while round_idx < MAX_TOOL_ROUNDS_PER_TURN:
        round_idx += 1
        resp = call_ollama(history, system)
        in_tok += resp["input_tokens"]
        out_tok += resp["output_tokens"]
        assistant_content = resp["content"]
        history.append({"role": "assistant", "content": assistant_content})
        logger.event("eng_raw", {"round": round_idx, "content": assistant_content[:2000]})

        calls = parse_tool_calls(assistant_content)
        if not calls:
            # No tool calls at all — nudge the engineer to produce a respond_to_po.
            history.append({
                "role": "user",
                "content": (
                    "You must end every turn with exactly one `respond_to_po` "
                    "tool call in a ```tool block. Try again."
                ),
            })
            continue

        tool_results = []
        end_turn = False
        for call in calls:
            name = call.get("name", "")
            args = call.get("args", {}) or {}
            tool_calls += 1
            try:
                if name in BASELINE_TOOLS:
                    result = BASELINE_TOOLS[name](workspace, args)
                elif loom_ctx and name in LOOM_TOOLS:
                    result = LOOM_TOOLS[name](loom_ctx, args)
                    if loom_ctx.get("metrics") is not None:
                        loom_ctx["metrics"].loom_tool_calls[name] = \
                            loom_ctx["metrics"].loom_tool_calls.get(name, 0) + 1
                else:
                    result = {"ok": False, "error": f"unknown or unavailable tool: {name}"}
            except ToolError as e:
                result = {"ok": False, "error": str(e)}
            except Exception as e:
                result = {"ok": False, "error": f"tool crashed: {type(e).__name__}: {e}"}
            logger.event("tool_call", {"name": name, "args_keys": list(args.keys()), "ok": result.get("ok")})
            if result.get("_end_turn"):
                message_to_po = result.get("message", "")
                end_turn = True
                break
            tool_results.append({"tool": name, "result": result})

        if end_turn:
            return message_to_po, in_tok, out_tok, tool_calls

        # Feed tool results back to the engineer
        feedback = "Tool results:\n" + "\n".join(
            f"- {tr['tool']}: {json.dumps(tr['result'])[:500]}"
            for tr in tool_results
        )
        history.append({"role": "user", "content": feedback})

    # Ran out of rounds without respond_to_po
    return (
        "(engineer exceeded tool-call rounds without ending turn)",
        in_tok, out_tok, tool_calls,
    )


# ============================================================
# Metrics + logging
# ============================================================

@dataclass
class Metrics:
    run_id: int
    condition: str
    model: str
    started_at: float = field(default_factory=time.time)
    iterations: int = 0
    po_tokens_in: int = 0
    po_tokens_out: int = 0
    eng_tokens_in: int = 0
    eng_tokens_out: int = 0
    tool_calls: int = 0
    pass_trace: list[int] = field(default_factory=list)
    total_tests: int = 0
    regression_count: int = 0
    last_per_test: dict = field(default_factory=dict)
    iterations_to_80pct: int | None = None
    stop_reason: str = ""
    loom_tool_calls: dict[str, int] = field(default_factory=dict)

    def record_tests(self, results: dict) -> None:
        self.pass_trace.append(results["passed"])
        self.total_tests = results["total"]
        # Count regressions: tests that were PASSED in last_per_test but FAILED now.
        if self.last_per_test:
            for name, status in self.last_per_test.items():
                now = results["per_test"].get(name, "MISSING")
                if status == "PASSED" and now in ("FAILED", "ERROR", "MISSING"):
                    self.regression_count += 1
        self.last_per_test = dict(results["per_test"])
        pct = (results["passed"] / results["total"]) if results["total"] else 0.0
        if self.iterations_to_80pct is None and pct >= 0.8:
            self.iterations_to_80pct = self.iterations

    def final(self) -> dict:
        return {
            "run_id": self.run_id,
            "condition": self.condition,
            "model": self.model,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 1),
            "iterations": self.iterations,
            "stop_reason": self.stop_reason,
            "final_passed": self.pass_trace[-1] if self.pass_trace else 0,
            "final_total": self.total_tests,
            "final_pass_rate": (
                self.pass_trace[-1] / self.total_tests
                if self.pass_trace and self.total_tests else 0.0
            ),
            "iterations_to_80pct": self.iterations_to_80pct,
            "po_tokens_in": self.po_tokens_in,
            "po_tokens_out": self.po_tokens_out,
            "eng_tokens_in": self.eng_tokens_in,
            "eng_tokens_out": self.eng_tokens_out,
            "total_tokens": (
                self.po_tokens_in + self.po_tokens_out
                + self.eng_tokens_in + self.eng_tokens_out
            ),
            "tool_calls": self.tool_calls,
            "regression_count": self.regression_count,
            "pass_trace": self.pass_trace,
            "loom_tool_calls": dict(self.loom_tool_calls),
        }


class EventLogger:
    def __init__(self, run_dir: Path):
        run_dir.mkdir(parents=True, exist_ok=True)
        self.path = run_dir / "events.jsonl"
        self.f = self.path.open("a", encoding="utf-8")

    def event(self, kind: str, data: dict) -> None:
        self.f.write(json.dumps({"kind": kind, "t": time.time(), **data}) + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


# ============================================================
# Main run loop
# ============================================================

def run_experiment(condition: str, run_id: int, max_iters: int = MAX_ITERATIONS) -> dict:
    assert condition in ("baseline", "loom")
    run_dir = RUNS_DIR / f"{condition}_{run_id:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = EventLogger(run_dir)

    workspace = make_workspace(run_id)
    logger.event("start", {"condition": condition, "workspace": str(workspace)})

    # Per-run hermetic Loom "home" so the CLI writes to a tempdir, not ~/.openclaw/loom.
    loom_home = Path(tempfile.mkdtemp(prefix=f"bakeoff_loomhome_{run_id}_"))
    loom_project = f"bakeoff_{condition}_{run_id}"
    metrics = Metrics(run_id=run_id, condition=condition, model=MODEL)
    loom_ctx = (
        {"project": loom_project, "loom_home": loom_home, "metrics": metrics}
        if condition == "loom" else None
    )
    po_system = build_po_system_prompt()
    eng_system = build_engineer_system_prompt(condition)

    po_history: list[dict] = []
    eng_history: list[dict] = []

    # Kick-off: PO speaks first with no prior conversation.
    po_history.append({"role": "user", "content": "Begin. Give the engineer the first directive."})

    last_results: dict | None = None
    progress_window: list[int] = []

    try:
        while metrics.iterations < max_iters:
            metrics.iterations += 1
            it = metrics.iterations
            logger.event("iteration_start", {"iteration": it})

            # --- PO turn ---
            if last_results is not None:
                delta_msg = _format_test_results(last_results, metrics.last_per_test_prev)
                po_history.append({"role": "user", "content": f"Engineer responded.\n\nCurrent test state:\n{delta_msg}"})

            po_resp = call_ollama(po_history, po_system)
            metrics.po_tokens_in += po_resp["input_tokens"]
            metrics.po_tokens_out += po_resp["output_tokens"]
            po_msg = po_resp["content"].strip()
            po_history.append({"role": "assistant", "content": po_msg})
            logger.event("po_message", {"iteration": it, "content": po_msg[:2000]})

            if "DONE:" in po_msg.upper():
                metrics.stop_reason = "po_signaled_done"
                break

            # --- Engineer turn ---
            eng_history.append({"role": "user", "content": po_msg})
            eng_msg, eng_in, eng_out, tcount = engineer_turn(
                workspace, eng_history, eng_system,
                BASELINE_TOOLS, loom_ctx, logger,
            )
            metrics.eng_tokens_in += eng_in
            metrics.eng_tokens_out += eng_out
            metrics.tool_calls += tcount
            logger.event("eng_message_to_po", {"iteration": it, "content": eng_msg[:2000]})

            # --- Run tests ---
            metrics.last_per_test_prev = dict(metrics.last_per_test)  # type: ignore
            results = run_tests(workspace)
            metrics.record_tests(results)
            logger.event("tests", {"iteration": it, "passed": results["passed"], "total": results["total"]})

            # Hand engineer's message + terse test summary to PO for next iter.
            last_results = results

            # Stop conditions
            if results["total"] > 0 and results["passed"] == results["total"]:
                metrics.stop_reason = "all_tests_pass"
                break
            if metrics.po_tokens_in + metrics.po_tokens_out + metrics.eng_tokens_in + metrics.eng_tokens_out >= TOKEN_BUDGET:
                metrics.stop_reason = "token_budget"
                break
            progress_window.append(results["passed"])
            if len(progress_window) > NO_PROGRESS_WINDOW:
                progress_window.pop(0)
            if len(progress_window) == NO_PROGRESS_WINDOW and len(set(progress_window)) == 1 and results["passed"] < results["total"]:
                metrics.stop_reason = "no_progress"
                break
        else:
            metrics.stop_reason = "max_iterations"
    finally:
        summary = metrics.final()
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
        logger.event("end", summary)
        logger.close()
        cleanup_workspace(workspace)
        shutil.rmtree(loom_home, ignore_errors=True)

    return summary


def _format_test_results(current: dict, previous: dict | None) -> str:
    """Results summary for the PO, grouped by requirement-class.

    Our ground-truth tests are grouped by test class (TestAdd, TestPeek,
    ...) which maps to REQ-1..REQ-6. Per-class breakdown helps the PO
    decide whether a requirement is "done enough" to move past (some
    tests cross-cut reqs — e.g. test_add_increases_length needs __len__).
    """
    prev = previous or {}

    # Collection-error path: pytest couldn't even load the tests. Surface
    # the error prominently so the PO can route the engineer to fix it,
    # rather than guessing why 0 tests are passing.
    if current.get("collection_error"):
        return (
            "PYTEST COULD NOT COLLECT TESTS (module import or syntax error).\n"
            "The implementation file may have the wrong class name, a missing\n"
            "`__init__`, or a syntax error. Typical cause: the class is named\n"
            "something other than `TaskQueue`, or a referenced attribute "
            "wasn't initialized.\n\n"
            "Error excerpt:\n"
            + "\n".join("  " + line for line in current["collection_error"].splitlines()[:6])
        )

    lines = [f"{current['passed']} / {current['total']} tests passing overall."]

    # Group by class name
    by_class: dict[str, list[tuple[str, str]]] = {}
    for name, status in current["per_test"].items():
        # "tests/test_task_queue.py::TestAdd::test_method"
        try:
            _, cls, method = name.rsplit("::", 2)
        except ValueError:
            cls, method = "?", name
        by_class.setdefault(cls, []).append((method, status))

    # Ordered report per class (REQ-area)
    for cls in sorted(by_class):
        tests = by_class[cls]
        p = sum(1 for _, s in tests if s == "PASSED")
        t = len(tests)
        failing = [m for m, s in tests if s != "PASSED"]
        mark = "OK" if p == t else f"{p}/{t}"
        detail = (
            "" if p == t
            else "  failing: " + ", ".join(failing[:3])
        )
        lines.append(f"  [{cls}] {mark}{detail}")

    # Newly passing / regressions since last iter
    newly_passing = []
    newly_failing = []
    for name, status in current["per_test"].items():
        before = prev.get(name)
        if before != "PASSED" and status == "PASSED":
            newly_passing.append(name.rsplit("::", 1)[-1])
        elif before == "PASSED" and status in ("FAILED", "ERROR"):
            newly_failing.append(name.rsplit("::", 1)[-1])
    if newly_passing:
        lines.append("Newly passing: " + ", ".join(newly_passing))
    if newly_failing:
        lines.append("REGRESSIONS: " + ", ".join(newly_failing))
    return "\n".join(lines)


# ============================================================
# CLI
# ============================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Bakeoff V1 driver")
    p.add_argument("--condition", choices=["baseline", "loom"], required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--max-iters", type=int, default=MAX_ITERATIONS)
    args = p.parse_args()

    summary = run_experiment(args.condition, args.run_id, max_iters=args.max_iters)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
