#!/usr/bin/env python3
"""
Phase Y — generalized rule-precedence harness with scenario registry.

Generalizes phT to take --scenario S1_js | S2_py | S3_py. Same cell
shape (R_baseline / R_repeated / R_imperative / R_precedence_inline
/ R_meta_preamble / R_sanity_pro / R_imperative_pro), but the
underlying scenario assets (rule text, rationales, target file,
grading test, language) come from _scenarios.SCENARIOS.

Built to test the cross-scenario generalization of the Sonnet
imperative-poison finding. If R_imperative also fails on Python
S2/S3, the imperative-poison is a Sonnet model property. If it
fails only on JS S1, it's scenario-specific.

Usage:
    python phY_rule_precedence_smoke.py <scenario> sweep [N]
    python phY_rule_precedence_smoke.py <scenario> <cell> [run_id]

    PHY_EXEC_MODEL=claude-sonnet-4-6 python phY_rule_precedence_smoke.py S2_py R_imperative 1

Output filenames embed scenario_id and (for non-Qwen) model:
    phY_<scenario_id>_[<model>_]<cell>_run<id>_summary.json
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
import urllib.error
import urllib.request
from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"
OUT_DIR = BAKEOFF_DIR / "runs-v2"

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

sys.path.insert(0, str(LOOM_DIR / "src"))
sys.path.insert(0, str(BAKEOFF_DIR / "v2_driver"))

from _scenarios import SCENARIOS, CELL_CONFIG, META_PREAMBLE  # noqa: E402

# Optional JS semantic indexer — imported lazily.
_JS_INDEXER = None


# ---------------------------------------------------------------------------
# Ollama call (verbatim from phT)
# ---------------------------------------------------------------------------

OLLAMA_URL = "http://localhost:11434/api/generate"


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    keep_alive = os.environ.get("LOOM_OLLAMA_KEEP_ALIVE", "30m")
    # Lock sampling parameters for near-determinism. temperature=0 alone
    # is not sufficient because top_p (default 0.9) and top_k (default 40)
    # interact with greedy-sampling tie-breaks. Setting top_k=1 with
    # temperature=0 produces pure greedy decoding. seed is set for any
    # remaining stochastic operations (e.g., CUDA reduction order).
    # repeat_penalty=1.0 disables the default penalty so it doesn't shift
    # logits.
    sampling = {
        "temperature": float(os.environ.get("PHY_TEMPERATURE", "0.0")),
        "top_p": 1.0,
        "top_k": 1,
        "seed": int(os.environ.get("PHY_SEED", "42")),
        "repeat_penalty": 1.0,
    }
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "keep_alive": keep_alive,
        "options": sampling,
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                  headers={"Content-Type": "application/json"})
    backoffs = [5, 15]
    last_err: Exception | None = None
    t0 = time.time()
    for attempt in range(len(backoffs) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "response": data.get("response", ""),
                "elapsed_s": time.time() - t0,
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
                "sampling_options": sampling,
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
    raise RuntimeError(f"ollama call failed after retries: {last_err}")


# ---------------------------------------------------------------------------
# Claude CLI shell-out (verbatim from phT)
# ---------------------------------------------------------------------------

_CLAUDE_SYSTEM_PROMPT = (
    "You are a helpful coding assistant. When the user asks for code, "
    "reply with the requested code in a fenced code block and nothing "
    "outside it."
)


def call_claude(model: str, prompt: str, timeout: int = 600) -> dict:
    clean_cwd = tempfile.mkdtemp(prefix="phY_claude_cwd_")
    args = [
        "claude", "-p", "--no-session-persistence",
        "--output-format", "json", "--model", model,
        "--tools", "",
        "--system-prompt", _CLAUDE_SYSTEM_PROMPT,
    ]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    try:
        proc = subprocess.run(
            args, input=prompt, cwd=clean_cwd,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=env, timeout=timeout,
            shell=(sys.platform == "win32"),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"claude CLI timed out after {timeout}s")
    elapsed = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"claude CLI rc={proc.returncode}: {(proc.stderr or '')[-300:]}"
        )
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"claude CLI non-JSON output: {(proc.stdout or '')[-300:]}"
        )
    usage = d.get("usage", {}) or {}
    in_tokens = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    return {
        "response": d.get("result", ""),
        "elapsed_s": elapsed,
        "input_tokens": in_tokens,
        "output_tokens": usage.get("output_tokens", 0),
    }


def _call_model(model: str, prompt: str, timeout: int = 600) -> dict:
    if model.startswith("claude") or model in ("haiku", "sonnet", "opus"):
        return call_claude(model, prompt, timeout=timeout)
    return call_ollama(model, prompt, timeout=timeout)


# ---------------------------------------------------------------------------
# Scenario-aware workspace + grading
# ---------------------------------------------------------------------------

def setup_workspace(scenario: dict) -> Path:
    ws = Path(tempfile.mkdtemp(prefix=f"phY_{scenario['id'].lower()}_"))
    ref = scenario["scenario_dir"] / "reference"
    if scenario["workspace_layout"] == "flat":
        for src in ref.glob("*"):
            if src.is_file():
                shutil.copy(src, ws / src.name)
    elif scenario["workspace_layout"] == "tree":
        shutil.copytree(ref, ws, dirs_exist_ok=True)
        # Copy hidden test under tests/ so pytest can find it.
        (ws / "tests").mkdir(exist_ok=True)
        shutil.copy(scenario["scenario_dir"] / "tests" / scenario["test_file"],
                    ws / "tests" / scenario["test_file"])
        # Conftest so pytest finds the package
        (ws / "conftest.py").write_text(
            "import sys, pathlib\n"
            "sys.path.insert(0, str(pathlib.Path(__file__).parent))\n",
            encoding="utf-8",
        )
    else:
        raise ValueError(f"unknown workspace_layout: {scenario['workspace_layout']}")
    return ws


def grade_workspace(workspace: Path, scenario: dict) -> dict:
    grade_dir = Path(tempfile.mkdtemp(prefix=f"phY_grade_{scenario['id'].lower()}_"))
    target_rel = scenario["target_file"]

    if scenario["language"] == "javascript":
        # JS: copy modified target, test, and any package files.
        (grade_dir / Path(target_rel).parent).mkdir(parents=True, exist_ok=True)
        shutil.copy(workspace / target_rel, grade_dir / target_rel)
        shutil.copy(scenario["scenario_dir"] / "tests" / scenario["test_file"],
                    grade_dir / scenario["test_file"])
        for pkg_file in scenario.get("package_files", []):
            src = scenario["scenario_dir"] / "reference" / pkg_file
            if src.exists():
                shutil.copy(src, grade_dir / pkg_file)
        run_proc = subprocess.run(
            ["node", str(grade_dir / scenario["test_file"])],
            cwd=grade_dir, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        out = run_proc.stdout + run_proc.stderr
        m = re.search(r"SUMMARY:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
        if m:
            passed = int(m.group(1)); failed = int(m.group(2))
            return {"passed": passed, "total": passed + failed,
                    "compile_failed": False, "stdout_tail": out[-1500:]}
        return {"passed": 0, "total": 2, "compile_failed": True,
                "stdout_tail": out[-1500:]}

    elif scenario["language"] == "python":
        # Python: copy whole workspace tree (with modified target) into grade_dir.
        shutil.copytree(workspace, grade_dir, dirs_exist_ok=True)
        run_proc = subprocess.run(
            [sys.executable, "-m", "pytest",
             str(grade_dir / "tests" / scenario["test_file"]),
             "-v", "--tb=short", "--no-header"],
            cwd=grade_dir, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
        )
        out = run_proc.stdout + run_proc.stderr
        # parse pytest's "N passed, M failed" tail
        passed = failed = errors = 0
        m = re.search(r"(\d+)\s+passed", out)
        if m: passed = int(m.group(1))
        m = re.search(r"(\d+)\s+failed", out)
        if m: failed = int(m.group(1))
        m = re.search(r"(\d+)\s+error", out)
        if m: errors = int(m.group(1))
        total = passed + failed + errors
        compile_failed = (total == 0) or (errors > 0 and passed == 0)
        return {"passed": passed, "total": total if total else 2,
                "compile_failed": compile_failed,
                "stdout_tail": out[-1500:]}

    else:
        raise ValueError(f"unknown language: {scenario['language']}")


def get_semantic_context(workspace: Path, scenario: dict) -> str:
    # Methodology-sprint change (2026-05-11): semantic context block
    # disabled for ALL scenarios to equalize S1_js with S2_py and S3_py.
    # Previously S1 received a JsIndexer-derived semantic block while
    # S2/S3 received nothing, partially confounding cross-scenario
    # comparisons. Set PHY_RESTORE_JS_SEMANTIC=1 to opt back into the
    # old behavior for replication.
    if os.environ.get("PHY_RESTORE_JS_SEMANTIC") == "1":
        if scenario.get("use_semantic_indexer") != "js":
            return ""
        from loom import indexers
        from loom.indexers_js import JsIndexer
        for prev in list(indexers.registered()):
            indexers.unregister(prev)
        idx = JsIndexer(root=workspace)
        indexers.register(idx)
        try:
            block = idx.context_for(workspace / scenario["target_file"])
        finally:
            indexers.unregister(idx)
            idx.shutdown()
        return block
    return ""


# ---------------------------------------------------------------------------
# Prompt + extraction
# ---------------------------------------------------------------------------

def build_prompt(scenario: dict, cell_name: str, target_content: str,
                 semantic_block: str) -> str:
    cell = CELL_CONFIG[cell_name]
    rule = scenario["rules"][cell["rule"]]
    rationale = scenario["rationales"][cell["rationale"]]
    parts: list[str] = []

    # Layer C: meta preamble before everything else.
    if cell["preamble"]:
        parts.append(META_PREAMBLE.rstrip())
        parts.append("")

    parts.append(f"# Task: {scenario['task']}\n")
    parts.append(f"Files to modify: {scenario['target_file']}")
    parts.append(f"Grading test: tests/{scenario['test_file']}")
    parts.append(f"Size budget: <= 1 file, <= {scenario['size_budget_loc']} LoC\n")

    parts.append("## Requirements\n")
    parts.append("### REQ-001 [behavior]")
    parts.append(f"Value: {rule}")
    parts.append(f"Rationale: {rationale}")
    if cell["repeat_after"]:
        parts.append(f"Value (re-asserted): {rule}")
    parts.append("")

    if semantic_block:
        parts.append("## Semantic context\n")
        parts.append(f"```{scenario['code_fence']}")
        parts.append(semantic_block.rstrip())
        parts.append("```\n")

    parts.append("## Source context\n")
    parts.append(f"### {scenario['target_file']}")
    parts.append(f"```{scenario['code_fence']}")
    parts.append(target_content)
    parts.append("```\n")

    parts.append("## Output contract")
    parts.append(
        f"Reply with ONE {scenario['language'].title()} code block "
        f"(```{scenario['code_fence']} ... ```) containing the "
        f"**entire new file content** for `{scenario['target_file']}`. "
        f"You MUST include all existing code you want to keep — this "
        f"file will be OVERWRITTEN with your output. Do not include "
        f"prose outside the code block."
    )
    return "\n".join(parts)


def extract_code(scenario: dict, response: str) -> str | None:
    fences = [scenario["code_fence"]] + scenario.get("alt_fences", [])
    for fence in fences:
        m = re.search(rf"```{re.escape(fence)}\s*\n(.*?)\n```",
                       response, re.DOTALL)
        if m:
            return m.group(1).strip()
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------------------
# Top-level run
# ---------------------------------------------------------------------------

def run_one(scenario_id: str, cell: str, run_id: str) -> dict:
    if scenario_id not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario_id} (available: {list(SCENARIOS.keys())})")
    if cell not in CELL_CONFIG:
        raise ValueError(f"unknown cell: {cell}")
    scenario = SCENARIOS[scenario_id]

    t0 = time.time()
    workspace = setup_workspace(scenario)
    print(f"[setup] scenario={scenario_id} cell={cell} run={run_id}")

    target_path = workspace / scenario["target_file"]
    target_content = target_path.read_text(encoding="utf-8")
    semantic_block = get_semantic_context(workspace, scenario)
    prompt = build_prompt(scenario, cell, target_content, semantic_block)
    cfg = CELL_CONFIG[cell]
    rule_chars = len(scenario["rules"][cfg["rule"]])
    rationale_chars = len(scenario["rationales"][cfg["rationale"]])
    print(f"[prompt] {len(prompt)} chars  rule={rule_chars}  "
          f"rationale={rationale_chars}  preamble={cfg['preamble']}")

    model = os.environ.get("PHY_EXEC_MODEL", "qwen2.5-coder:32b")
    cell_slug = cell.replace("+", "_").replace("-", "_")
    if model.startswith("qwen2.5-coder"):
        model_suffix = ""
    else:
        model_suffix = "_" + model.replace(":", "_").replace("/", "_")
    out_path = OUT_DIR / f"phY_{scenario_id}{model_suffix}_{cell_slug}_run{run_id}_summary.json"

    try:
        llm = _call_model(model, prompt)
    except Exception as e:
        err = {"phase": "Y_rule_precedence", "scenario": scenario_id,
               "cell": cell, "run_id": run_id, "passed": 0, "total": 2,
               "error": f"model call failed ({model}): {e}",
               "wall_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(err, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} ERROR: {e}")
        return err
    print(f"[llm] {llm['elapsed_s']:.1f}s in={llm['input_tokens']} "
          f"out={llm['output_tokens']}")

    code = extract_code(scenario, llm["response"])
    if code is None:
        no_code = {"phase": "Y_rule_precedence", "scenario": scenario_id,
                   "cell": cell, "run_id": run_id, "passed": 0, "total": 2,
                   "compile_failed": True, "no_code_extracted": True,
                   "input_tokens": llm["input_tokens"],
                   "output_tokens": llm["output_tokens"], "model": model,
                   "wall_s": round(time.time() - t0, 1)}
        out_path.write_text(json.dumps(no_code, indent=2), encoding="utf-8")
        print(f"SUMMARY: {cell} no_code_extracted")
        return no_code

    target_path.write_text(code, encoding="utf-8")
    g = grade_workspace(workspace, scenario)
    # Methodology-sprint addition (2026-05-11): detect no-op responses
    # where the model returned the file (essentially) unchanged. Used
    # to disambiguate "model followed contrarian rule" from "model
    # preserved existing implementation" on S1 (where the reference
    # already complies). Uses a normalized comparison (strip whitespace
    # and blank lines) rather than byte-equality so trivial formatting
    # differences don't hide genuine no-ops.
    def _normalize(s: str) -> str:
        return "\n".join(line.strip() for line in s.splitlines() if line.strip())
    no_op_flag = _normalize(code) == _normalize(target_content)
    print(f"[grade] pass={g['passed']}/{g['total']}  compile_failed={g.get('compile_failed', False)}  no_op={no_op_flag}")
    summary = {
        "phase": "Y_rule_precedence",
        "scenario": scenario_id,
        "cell": cell,
        "run_id": run_id,
        "passed": g["passed"],
        "total": g["total"],
        "pass_rate": g["passed"] / g["total"] if g["total"] else 0.0,
        "compile_failed": g.get("compile_failed", False),
        "no_op": no_op_flag,
        "rule_chars": rule_chars,
        "rationale_chars": rationale_chars,
        "has_preamble": bool(cfg["preamble"]),
        "rule_repeated_after": bool(cfg["repeat_after"]),
        "input_tokens": llm["input_tokens"],
        "output_tokens": llm["output_tokens"],
        "sampling_options": llm.get("sampling_options"),
        "model": model,
        "language": scenario["language"],
        "llm_elapsed_s": round(llm["elapsed_s"], 1),
        "wall_s": round(time.time() - t0, 1),
        "grade_stdout_tail": g["stdout_tail"],
        "llm_response_full": llm["response"],
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"SUMMARY: {cell} pass={g['passed']}/{g['total']} wall={summary['wall_s']}s")
    return summary


def run_sweep(scenario_id: str, n_per_cell: int) -> None:
    cells = list(CELL_CONFIG.keys())
    sweep_t0 = time.time()
    for cell in cells:
        for i in range(1, n_per_cell + 1):
            run_one(scenario_id, cell, str(i))
    print(f"sweep complete in {time.time() - sweep_t0:.1f}s")


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print("usage:")
        print("  phY_rule_precedence_smoke.py <scenario> sweep [N]")
        print("  phY_rule_precedence_smoke.py <scenario> <cell> [run_id]")
        print(f"  scenarios: {', '.join(SCENARIOS.keys())}")
        print(f"  cells: {', '.join(CELL_CONFIG.keys())}")
        return 1
    scenario_id = argv[1]
    if argv[2] == "sweep":
        n = int(argv[3]) if len(argv) > 3 else 10
        run_sweep(scenario_id, n)
        return 0
    cell = argv[2]
    run_id = argv[3] if len(argv) > 3 else "smoke"
    if cell not in CELL_CONFIG:
        print(f"unknown cell: {cell}", file=sys.stderr)
        return 1
    run_one(scenario_id, cell, run_id)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
