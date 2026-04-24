#!/usr/bin/env python3
"""
Bakeoff V2 driver — `claude -p` backend.

Orchestrates two Claude Code subagent roles (PO, Engineer) over a
turn-based build conversation against a fixed ground truth. Both sides
invoke `claude -p` (headless mode, Max-covered) with
`--no-session-persistence` so every call is truly independent.

Differences from the V1 driver (`../driver.py`):
  - Instead of talking to Ollama over HTTP, shells out to `claude -p`.
  - Engineer's tool use (Read/Write/Bash) is handled natively by
    Claude Code inside the subprocess. The driver does NOT parse tool
    blocks; it just feeds the engineer a prompt and collects its final
    text reply.
  - `--model` flag lets us set the model per call (haiku/sonnet/opus).
  - Runs on Max, not pay-as-you-go API billing.

Usage:
    python driver.py --condition {p1_sym,p2_mixed,p3_delegate} \
                     --run-id N \
                     --po-model sonnet --eng-model sonnet \
                     --loom {eng|po|none} \
                     --benchmark python-queue

Writes per-run log + summary to
    ../runs-v2/<condition>_<tag>_<run_id>/
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
from dataclasses import dataclass, field
from pathlib import Path

# ----- paths -----
V2_DIR = Path(__file__).resolve().parent
BAKEOFF_DIR = V2_DIR.parent
GROUND_TRUTH_ROOT = BAKEOFF_DIR / "ground_truth"
RUNS_ROOT = BAKEOFF_DIR / "runs-v2"
LOOM_SCRIPT = BAKEOFF_DIR.parent.parent / "scripts" / "loom"

# ----- stop conditions -----
MAX_ITERATIONS = 25
TOKEN_BUDGET = 500_000         # across both agents combined per run
NO_PROGRESS_WINDOW = 5
PER_TURN_TIMEOUT_S = 300       # claude -p can be slow on opus


# ============================================================
# claude -p wrapper
# ============================================================

def call_claude_p(
    prompt: str,
    system_append: str,
    *,
    model: str,
    add_dirs: list[Path | str] | None = None,
    timeout: int = PER_TURN_TIMEOUT_S,
    allowed_tools: list[str] | None = None,
) -> dict:
    """One `claude -p` call. Returns dict with result, tokens, duration, etc.

    On failure: returns {"error": str} so callers can classify.
    """
    args = [
        "claude", "-p",
        "--no-session-persistence",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", system_append,
    ]
    if add_dirs:
        args.append("--add-dir")
        args.extend(str(d) for d in add_dirs)
    if allowed_tools:
        args.append("--allowed-tools")
        args.extend(allowed_tools)

    try:
        r = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {"error": f"timeout after {timeout}s"}

    if r.returncode != 0:
        return {
            "error": f"claude -p exit={r.returncode}",
            "stderr": (r.stderr or "")[:1000],
            "stdout": (r.stdout or "")[:1000],
        }
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"json parse: {e}", "stdout": (r.stdout or "")[:1000]}

    usage = data.get("usage") or {}
    return {
        "content": data.get("result", ""),
        "duration_ms": data.get("duration_ms", 0),
        "num_turns": data.get("num_turns", 0),
        "cost_usd": data.get("total_cost_usd", 0),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "session_id": data.get("session_id", ""),
        "stop_reason": data.get("stop_reason", ""),
        "is_error": data.get("is_error", False),
    }


# ============================================================
# Workspace + tests
# ============================================================

def make_workspace(run_id: int, condition: str, benchmark: str) -> tuple[Path, Path]:
    """Return (engineer_workspace, test_grounds) tempdirs.

    Engineer sees only the workspace (no tests). Orchestrator runs
    pytest in test_grounds, which contains a copy of the engineer's
    file + the hidden tests.
    """
    tag = f"{condition}_{run_id:03d}"
    eng = Path(tempfile.mkdtemp(prefix=f"v2_{tag}_eng_"))
    grounds = Path(tempfile.mkdtemp(prefix=f"v2_{tag}_test_"))

    bench_dir = GROUND_TRUTH_ROOT if benchmark == "python-queue" else (
        BAKEOFF_DIR / "benchmarks" / benchmark / "ground_truth"
    )
    if not bench_dir.exists():
        raise FileNotFoundError(f"benchmark ground_truth not found: {bench_dir}")

    # Seed the engineer workspace with an empty target file.
    # For python-queue: task_queue.py
    target_file = "task_queue.py"  # TODO: read from benchmark manifest
    (eng / target_file).write_text("# Engineer writes here.\n", encoding="utf-8")

    # Copy the hidden tests into the test grounds.
    tests_src = bench_dir / "tests"
    shutil.copytree(tests_src, grounds / "tests")

    return eng, grounds


def run_tests(test_grounds: Path) -> dict:
    """Run pytest in the grounds; return {passed, total, per_test, collection_error}."""
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=line", "--no-header"],
        cwd=test_grounds,
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    per_test: dict[str, str] = {}
    for line in out.splitlines():
        m = re.search(r"(tests/[^\s]+::[A-Za-z_][\w:]+)\s+(PASSED|FAILED|ERROR)", line)
        if m:
            per_test[m.group(1)] = m.group(2)
    passed = sum(1 for v in per_test.values() if v == "PASSED")
    total = len(per_test)
    collection_error = None
    if total == 0 and r.returncode != 0:
        error_lines = [
            line.strip() for line in out.splitlines()
            if any(tok in line for tok in
                   ("ImportError", "ModuleNotFoundError", "SyntaxError",
                    "AttributeError", "ERROR collecting", "ERRORS"))
        ]
        collection_error = "\n".join(error_lines[:6]) or "pytest exited nonzero with 0 tests"
    return {
        "passed": passed, "total": total,
        "per_test": per_test, "collection_error": collection_error,
    }


# ============================================================
# Agent system prompts
# ============================================================

PO_SYSTEM_PROMPT = """You are the Product Owner for a small Python library build. You know the full spec; the engineer does NOT and relies on your incremental directives. This is a turn-based conversation.

## Ground truth you hold (engineer never sees this document directly)

{ground_truth_spec}

Tests are hidden from the engineer. After each engineer turn the test suite runs; you're told which classes pass/fail and can decide what to say next.

## Your role each turn

- Turn 1: brief overview of the product + reveal ONE requirement (REQ-1). Ask the engineer to implement just that piece.
- Later turns: look at the test class breakdown and the engineer's reply, decide: move to next requirement, clarify, or correct a regression.
- Some tests cross-cut requirements (e.g. `test_add_increases_length` needs `__len__` from REQ-6). Don't block on perfection — move forward when the engineer has made a reasonable pass at what you asked for.
- Keep each message short (1-4 sentences).
- When all 6 reqs are implemented and tests green, say exactly: `DONE: all requirements implemented.`

## Hard rules

- NEVER paste test source or predict test names. Describe behavior.
- NEVER reveal later requirements before it's their turn.
- Output ONLY the message you want the engineer to see. No meta-commentary, no "Here's what I'll say:", no preamble."""


ENG_SYSTEM_BASELINE = """You are the Engineer implementing a Python library. A Product Owner messages you one directive at a time. Implement exactly what they ask.

## Workspace

Your working directory is `{workspace}`. The only file you should write is `task_queue.py` inside that directory.

## CONSTRAINTS

- Write ONLY to `{workspace}/task_queue.py`. Use the Write tool with the absolute path.
- After writing, Read the file to verify it stuck.
- Do NOT try to discover test files. They live elsewhere and you can't access them.
- Do NOT use any Loom tools. None available in this condition.
- Don't implement more than the PO asked for in this turn.

## Output format

After implementing, end your reply with a brief (1-3 sentence) message to the PO summarizing what you did. That message is all the PO sees.
"""


ENG_SYSTEM_LOOM = """You are the Engineer implementing a Python library. A Product Owner messages you one directive at a time.

You have access to **Loom**, a requirements traceability tool, via the bash tool:

    python3 {loom_script} -p {loom_project} <subcommand> [args]

Useful subcommands:

- Capture a requirement (pipe text via stdin):
    echo "REQUIREMENT: behavior | <text>" | python3 {loom_script} -p {loom_project} extract --rationale "<why>"
- List captured requirements:
    python3 {loom_script} -p {loom_project} list --json
- Link your implementation to a requirement (run from the workspace):
    python3 {loom_script} -p {loom_project} link task_queue.py --req REQ-xxx
- Check what reqs a file is linked to:
    python3 {loom_script} -p {loom_project} check {workspace}/task_queue.py

Use Loom to capture requirements as the PO describes them, and link your code. Don't re-capture the same requirement twice.

## Workspace

Working directory: `{workspace}`. Only file to edit: `{workspace}/task_queue.py`.

## CONSTRAINTS

- Write ONLY to `{workspace}/task_queue.py`. Absolute path. Verify via Read after.
- Do NOT try to discover test files.
- Keep implementation focused on what the PO asked for this turn.

## Output format

End your reply with a brief (1-3 sentence) message to the PO summarizing what you did. That's all the PO sees.
"""


def load_ground_truth_spec(benchmark: str) -> str:
    """Load the README the PO quotes from."""
    if benchmark == "python-queue":
        return (GROUND_TRUTH_ROOT / "README.md").read_text(encoding="utf-8")
    path = BAKEOFF_DIR / "benchmarks" / benchmark / "ground_truth" / "README.md"
    return path.read_text(encoding="utf-8")


# ============================================================
# Conversation orchestration
# ============================================================

def format_test_results(current: dict, previous: dict | None) -> str:
    """PO-facing summary. Same format as V1 driver."""
    prev = previous or {}
    if current.get("collection_error"):
        return (
            "PYTEST COULD NOT COLLECT TESTS (import/syntax error).\n"
            "The engineer's task_queue.py likely has the wrong class name "
            "or a broken import. Error excerpt:\n"
            + "\n".join("  " + ln for ln in current["collection_error"].splitlines()[:5])
        )
    lines = [f"{current['passed']} / {current['total']} passing."]
    by_class: dict[str, list[tuple[str, str]]] = {}
    for name, status in current["per_test"].items():
        try:
            _, cls, m = name.rsplit("::", 2)
        except ValueError:
            cls, m = "?", name
        by_class.setdefault(cls, []).append((m, status))
    for cls in sorted(by_class):
        tests = by_class[cls]
        p = sum(1 for _, s in tests if s == "PASSED")
        t = len(tests)
        failing = [m for m, s in tests if s != "PASSED"]
        mark = "OK" if p == t else f"{p}/{t}"
        detail = "" if p == t else "  failing: " + ", ".join(failing[:3])
        lines.append(f"  [{cls}] {mark}{detail}")
    # Regressions/newly passing
    newly_pass, newly_fail = [], []
    for name, status in current["per_test"].items():
        before = prev.get(name)
        if before != "PASSED" and status == "PASSED":
            newly_pass.append(name.rsplit("::", 1)[-1])
        elif before == "PASSED" and status in ("FAILED", "ERROR"):
            newly_fail.append(name.rsplit("::", 1)[-1])
    if newly_pass:
        lines.append("Newly passing: " + ", ".join(newly_pass))
    if newly_fail:
        lines.append("REGRESSIONS: " + ", ".join(newly_fail))
    return "\n".join(lines)


def build_po_prompt(
    history: list[dict],
    last_test_results: dict | None,
    previous_per_test: dict | None,
) -> str:
    parts = []
    if not history:
        parts.append("Begin. Give the engineer the first directive (reveal REQ-1 only).")
        return "\n".join(parts)

    # Render conversation history as plain text
    parts.append("## Conversation so far\n")
    for h in history:
        parts.append(f"**{h['role']}**: {h['content']}")
        parts.append("")
    parts.append("## Current test state after the engineer's last turn\n")
    parts.append(format_test_results(last_test_results, previous_per_test))
    parts.append("")
    parts.append("Now produce your next directive for the engineer. Output the message only.")
    return "\n".join(parts)


def build_engineer_prompt(history: list[dict], po_message: str) -> str:
    parts = []
    if history:
        parts.append("## Conversation so far\n")
        for h in history:
            parts.append(f"**{h['role']}**: {h['content']}")
            parts.append("")
    parts.append("## PO's new directive\n")
    parts.append(po_message)
    parts.append("")
    parts.append("Implement what the PO asked for. Write to the workspace file, verify via Read, then end with your reply to the PO.")
    return "\n".join(parts)


# ============================================================
# Metrics
# ============================================================

@dataclass
class Metrics:
    run_id: int
    condition: str
    po_model: str
    eng_model: str
    benchmark: str
    loom_mode: str   # "eng", "po", "none", "delegate"
    started_at: float = field(default_factory=time.time)
    iterations: int = 0
    po_in: int = 0
    po_out: int = 0
    eng_in: int = 0
    eng_out: int = 0
    po_duration_ms: int = 0
    eng_duration_ms: int = 0
    po_cost: float = 0.0
    eng_cost: float = 0.0
    pass_trace: list[int] = field(default_factory=list)
    total_tests: int = 0
    regression_count: int = 0
    last_per_test: dict = field(default_factory=dict)
    iters_to_80pct: int | None = None
    stop_reason: str = ""
    errors: list[str] = field(default_factory=list)

    def record_tests(self, results: dict) -> None:
        self.pass_trace.append(results["passed"])
        self.total_tests = results["total"]
        # Regressions: tests PASSED last iter but not now.
        if self.last_per_test:
            for name, s in self.last_per_test.items():
                now = results["per_test"].get(name, "MISSING")
                if s == "PASSED" and now in ("FAILED", "ERROR", "MISSING"):
                    self.regression_count += 1
        self.last_per_test = dict(results["per_test"])
        pct = results["passed"] / results["total"] if results["total"] else 0.0
        if self.iters_to_80pct is None and pct >= 0.8:
            self.iters_to_80pct = self.iterations

    def final(self) -> dict:
        return {
            "run_id": self.run_id,
            "condition": self.condition,
            "po_model": self.po_model,
            "eng_model": self.eng_model,
            "benchmark": self.benchmark,
            "loom_mode": self.loom_mode,
            "started_at": self.started_at,
            "duration_s": round(time.time() - self.started_at, 1),
            "iterations": self.iterations,
            "stop_reason": self.stop_reason,
            "final_passed": self.pass_trace[-1] if self.pass_trace else 0,
            "final_total": self.total_tests,
            "final_pass_rate": (self.pass_trace[-1] / self.total_tests) if self.pass_trace and self.total_tests else 0.0,
            "iterations_to_80pct": self.iters_to_80pct,
            "po_in": self.po_in, "po_out": self.po_out,
            "eng_in": self.eng_in, "eng_out": self.eng_out,
            "po_duration_ms": self.po_duration_ms,
            "eng_duration_ms": self.eng_duration_ms,
            "po_cost_usd": round(self.po_cost, 4),
            "eng_cost_usd": round(self.eng_cost, 4),
            "total_tokens": self.po_in + self.po_out + self.eng_in + self.eng_out,
            "regression_count": self.regression_count,
            "pass_trace": self.pass_trace,
            "errors": self.errors,
        }


class EventLogger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = path.open("a", encoding="utf-8")

    def event(self, kind: str, **data) -> None:
        self.f.write(json.dumps({"kind": kind, "t": time.time(), **data}) + "\n")
        self.f.flush()

    def close(self) -> None:
        self.f.close()


# ============================================================
# Main run
# ============================================================

def run_experiment(
    condition: str,
    run_id: int,
    po_model: str,
    eng_model: str,
    loom_mode: str,
    benchmark: str,
    max_iters: int = MAX_ITERATIONS,
) -> dict:
    # Output dirs
    run_tag = (
        f"{condition}_"
        f"{po_model}po-{eng_model}eng-{loom_mode}L-{benchmark}_"
        f"{run_id:03d}"
    )
    run_dir = RUNS_ROOT / run_tag
    run_dir.mkdir(parents=True, exist_ok=True)
    logger = EventLogger(run_dir / "events.jsonl")
    logger.event("start",
        condition=condition, run_id=run_id, benchmark=benchmark,
        po_model=po_model, eng_model=eng_model, loom_mode=loom_mode,
    )

    # Workspaces
    eng_ws, test_grounds = make_workspace(run_id, run_tag, benchmark)
    logger.event("workspace", engineer=str(eng_ws), tests=str(test_grounds))

    # Loom per-run store (if Loom involved anywhere)
    loom_project = f"bakeoff-v2-{run_tag}"
    loom_home = Path(tempfile.mkdtemp(prefix=f"loomhome_{run_tag}_"))

    # System prompts
    gt_spec = load_ground_truth_spec(benchmark)
    po_system = PO_SYSTEM_PROMPT.replace("{ground_truth_spec}", gt_spec)

    if loom_mode == "eng":
        eng_system = ENG_SYSTEM_LOOM.format(
            workspace=eng_ws, loom_script=LOOM_SCRIPT, loom_project=loom_project,
        )
    else:
        eng_system = ENG_SYSTEM_BASELINE.format(workspace=eng_ws)

    metrics = Metrics(
        run_id=run_id, condition=condition, po_model=po_model,
        eng_model=eng_model, benchmark=benchmark, loom_mode=loom_mode,
    )

    history: list[dict] = []
    last_test: dict | None = None
    previous_per_test: dict | None = None
    progress_window: list[int] = []

    try:
        while metrics.iterations < max_iters:
            metrics.iterations += 1
            it = metrics.iterations
            logger.event("iteration_start", iteration=it)

            # --- PO turn ---
            po_prompt = build_po_prompt(history, last_test, previous_per_test)
            po_r = call_claude_p(
                po_prompt, po_system, model=po_model,
                add_dirs=None,  # PO doesn't edit files; no tools
            )
            if "error" in po_r:
                metrics.errors.append(f"iter{it} po: {po_r['error']}")
                metrics.stop_reason = f"po_call_error:{po_r['error'][:60]}"
                break
            po_msg = (po_r["content"] or "").strip()
            metrics.po_in += po_r["input_tokens"]
            metrics.po_out += po_r["output_tokens"]
            metrics.po_duration_ms += po_r["duration_ms"]
            metrics.po_cost += po_r["cost_usd"]
            history.append({"role": "PO", "content": po_msg})
            logger.event("po_message", iteration=it, content=po_msg[:3000],
                         tokens_in=po_r["input_tokens"], tokens_out=po_r["output_tokens"],
                         duration_ms=po_r["duration_ms"])

            if "DONE:" in po_msg.upper():
                metrics.stop_reason = "po_signaled_done"
                break

            # --- Engineer turn ---
            eng_prompt = build_engineer_prompt(history[:-1], po_msg)
            # Engineer needs access to workspace. For Loom condition,
            # also add_dir for Loom store home and scripts dir.
            add_dirs = [eng_ws]
            env_extra: dict[str, str] = {}
            if loom_mode == "eng":
                add_dirs.extend([loom_home, LOOM_SCRIPT.parent])
                # The loom CLI reads HOME for ~/.openclaw/loom/<project>
                env_extra["HOME"] = str(loom_home)
                env_extra["USERPROFILE"] = str(loom_home)
                env_extra["LOOM_PROJECT"] = loom_project
                # Note: subprocess env passthrough not supported by claude -p
                # directly. See issue note below — using default HOME for now.

            eng_r = call_claude_p(
                eng_prompt, eng_system, model=eng_model,
                add_dirs=add_dirs,
            )
            if "error" in eng_r:
                metrics.errors.append(f"iter{it} eng: {eng_r['error']}")
                metrics.stop_reason = f"eng_call_error:{eng_r['error'][:60]}"
                break
            eng_msg = (eng_r["content"] or "").strip()
            metrics.eng_in += eng_r["input_tokens"]
            metrics.eng_out += eng_r["output_tokens"]
            metrics.eng_duration_ms += eng_r["duration_ms"]
            metrics.eng_cost += eng_r["cost_usd"]
            history.append({"role": "Engineer", "content": eng_msg})
            logger.event("eng_message", iteration=it, content=eng_msg[:3000],
                         tokens_in=eng_r["input_tokens"], tokens_out=eng_r["output_tokens"],
                         duration_ms=eng_r["duration_ms"], num_turns=eng_r["num_turns"])

            # --- Apply engineer's workspace write + test ---
            src_file = eng_ws / "task_queue.py"
            if src_file.exists():
                shutil.copy2(src_file, test_grounds / "task_queue.py")
            previous_per_test = dict(metrics.last_per_test)
            results = run_tests(test_grounds)
            metrics.record_tests(results)
            last_test = results
            logger.event("tests", iteration=it,
                         passed=results["passed"], total=results["total"],
                         collection_error=results.get("collection_error"))

            # Stop conditions
            if results["total"] > 0 and results["passed"] == results["total"]:
                metrics.stop_reason = "all_tests_pass"
                break
            tot_tokens = metrics.po_in + metrics.po_out + metrics.eng_in + metrics.eng_out
            if tot_tokens >= TOKEN_BUDGET:
                metrics.stop_reason = "token_budget"
                break
            progress_window.append(results["passed"])
            if len(progress_window) > NO_PROGRESS_WINDOW:
                progress_window.pop(0)
            if (len(progress_window) == NO_PROGRESS_WINDOW
                and len(set(progress_window)) == 1
                and results["passed"] < results["total"]):
                metrics.stop_reason = "no_progress"
                break
        else:
            metrics.stop_reason = "max_iterations"
    finally:
        summary = metrics.final()
        (run_dir / "summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
        logger.event("end", **summary)
        logger.close()
        # Clean up workspaces; keep loom store for inspection
        shutil.rmtree(eng_ws, ignore_errors=True)
        shutil.rmtree(test_grounds, ignore_errors=True)

    return summary


# ============================================================
# CLI
# ============================================================

def main() -> int:
    p = argparse.ArgumentParser(description="Bakeoff V2 driver (claude -p)")
    p.add_argument("--condition", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--po-model", default="sonnet",
                   choices=["haiku", "sonnet", "opus"])
    p.add_argument("--eng-model", default="sonnet",
                   choices=["haiku", "sonnet", "opus"])
    p.add_argument("--loom", default="none",
                   choices=["none", "eng", "po", "delegate"],
                   help="Where Loom is available")
    p.add_argument("--benchmark", default="python-queue")
    p.add_argument("--max-iters", type=int, default=MAX_ITERATIONS)
    args = p.parse_args()

    summary = run_experiment(
        condition=args.condition,
        run_id=args.run_id,
        po_model=args.po_model,
        eng_model=args.eng_model,
        loom_mode=args.loom,
        benchmark=args.benchmark,
        max_iters=args.max_iters,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
