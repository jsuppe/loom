"""
Hardest-task comparator: behavior-preserving refactor of gaps().

Starting state: services.gaps() handles 4 gap types as a single function.
Task: split the detection logic into 4 module-level private helpers
(_detect_missing_criteria, _detect_missing_elaboration, _detect_orphan_impl,
_detect_drift), each independently callable, with gaps() becoming a thin
orchestrator.

Tests 29 conditions: 20 behavior (no-regression) + 9 structural (helpers
exist, return the right type in isolation, and preserve the uniform shape).
This is a much harder test than the previous two because:
  - It's a REFACTOR, not an addition
  - The model must deeply understand the existing function
  - The output spans multiple definitions, not a single function
  - Behavior must be preserved EXACTLY
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
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")


REFACTOR_SPEC = """\
## Refactor specification

The existing services.gaps() function has grown to handle 4 gap types
(missing_criteria, missing_elaboration, orphan_impl, drift). Split the
detection logic into 4 module-level private helpers so each type can be
tested and extended in isolation:

    _detect_missing_criteria(store) -> list[dict]
    _detect_missing_elaboration(store) -> list[dict]
    _detect_orphan_impl(store) -> list[dict]
    _detect_drift(store) -> list[dict]

Each helper:
  - Is a MODULE-LEVEL function (underscore-prefixed, so private by convention).
  - Takes a single `store: LoomStore` argument.
  - Returns a list of gap dicts of its own type, no other types, no priority
    metadata required in the returned dicts (priority ordering is applied
    by the orchestrator gaps()).
  - Follows the uniform 5-field shape: type / entity_id / description /
    blocks / suggested_action.
  - Must produce the same gaps the current implementation produces (the
    same entity_ids, the same description text, the same blocks, the same
    suggested_action) - refactor only, no semantic changes.

gaps(store, types=None, limit=None) becomes a thin orchestrator:
  - Calls each helper.
  - Applies priority ordering (same as today: drift=2, missing_criteria=3,
    missing_elaboration=5, orphan_impl=6; ties by entity_id).
  - Applies types filter and limit.
  - Returns the combined result.

## Preservation requirements

- All 20 existing behavioral cases must still pass (no regression):
    missing_criteria surfaces, missing_elaboration surfaces, orphan_impl
    surfaces, drift surfaces, tie-break by entity_id, type filter, limit,
    superseded-req exclusion, priority ordering, uniform shape, etc.
- The public signature of gaps() must not change.
- Helpers must be callable in isolation (accessible as services._detect_*)
  and return only their own type's gaps.

## Anti-patterns to avoid

- Do NOT make the helpers call gaps() and filter by type - that's a fake
  split. Each helper must do its own detection work.
- Do NOT leave the old detection logic inline inside gaps() alongside the
  helpers; gaps() must delegate to the helpers.
- Do NOT introduce new gap types or change any existing behavior.
"""


TASK = """Read the current src/services.py. It contains a gaps() function that
handles 4 gap types inline. Refactor per the specification above.

Output requirements:
- Reply with ONE Python code block: ```python ... ```
- The block must contain: all 4 helper functions AND a replacement gaps()
  orchestrator, together.
- Your output will be APPENDED to src/services.py. Python's
  last-definition-wins means your new functions will shadow any that share
  the same name. Your block should NOT include existing helpers it depends
  on that are already defined in services.py (those stay as-is).
- Do NOT include prose or markdown headings outside the code block.

Begin your response with ```python and end with ``` (nothing after)."""


def build_prompt(services_py: str, store_py: str) -> str:
    return (
        "You are performing a behavior-preserving refactor on an existing Python module.\n\n"
        "=== LOOM CONTEXT ===\n\n"
        f"{REFACTOR_SPEC}\n\n"
        "=== Current src/services.py (read the gaps() function carefully) ===\n"
        "```python\n"
        f"{services_py}\n"
        "```\n\n"
        "=== src/store.py (dataclasses + LoomStore API reference) ===\n"
        "```python\n"
        f"{store_py}\n"
        "```\n\n"
        "=== TASK ===\n"
        f"{TASK}\n"
    )


def call_ollama(model: str, prompt: str, timeout: int = 900) -> dict:
    payload = json.dumps({
        "model": model,
        "stream": False,
        "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 10000},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    elapsed = time.perf_counter() - t0
    msg = body.get("message", {}) or {}
    return {
        "content": msg.get("content", ""),
        "elapsed_s": round(elapsed, 2),
        "eval_count": body.get("eval_count", 0),
        "prompt_eval_count": body.get("prompt_eval_count", 0),
    }


CODE_BLOCK_RE = re.compile(r"```python\s*\n(.*?)\n```", re.DOTALL)
GENERIC_BLOCK_RE = re.compile(r"```\s*\n(.*?)\n```", re.DOTALL)


def extract_code(content: str) -> str | None:
    m = CODE_BLOCK_RE.search(content)
    if m:
        return m.group(1).rstrip() + "\n"
    m = GENERIC_BLOCK_RE.search(content)
    if m:
        return m.group(1).rstrip() + "\n"
    return None


def run_grading(scratch: Path) -> tuple[int, int, int, int, str]:
    """Returns (passed, total, behavior_passed, structure_passed, tail)."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest",
         "experiments/gaps/test_gaps_refactor.py", "-v", "--tb=line"],
        cwd=scratch,
        capture_output=True,
        text=True,
        timeout=120,
    )
    combined = (res.stdout or "") + "\n" + (res.stderr or "")
    passed = combined.count(" PASSED")
    failed = combined.count(" FAILED")
    errored = combined.count(" ERROR")
    total = passed + failed + errored
    if total == 0:
        total = 29
        passed = 0

    # Separate behavior vs structure by test name prefix.
    behavior_passed = 0
    structure_passed = 0
    for line in combined.splitlines():
        if " PASSED" not in line:
            continue
        if "test_helper_" in line or "test_helpers_" in line:
            structure_passed += 1
        else:
            behavior_passed += 1

    tail = "\n".join(combined.splitlines()[-20:])
    return passed, total, behavior_passed, structure_passed, tail


def run_one_trial(model: str, keep_scratch: bool) -> dict:
    services_py = (REPO / "src" / "services.py").read_text(encoding="utf-8")
    store_py = (REPO / "src" / "store.py").read_text(encoding="utf-8")

    prompt = build_prompt(services_py, store_py)
    llm = call_ollama(model, prompt)
    code = extract_code(llm["content"])

    if code is None:
        return {
            "model": model,
            "passed": 0, "total": 29,
            "behavior_passed": 0, "structure_passed": 0,
            "extracted": False,
            "elapsed_s": llm["elapsed_s"],
            "input_tokens": llm["prompt_eval_count"],
            "output_tokens": llm["eval_count"],
            "error": "no code block",
            "content_preview": llm["content"][:400],
        }

    scratch = Path(tempfile.mkdtemp(prefix="ollama_gaps_ref_"))
    try:
        shutil.copytree(REPO / "src", scratch / "src")
        shutil.copytree(REPO / "tests", scratch / "tests")
        (scratch / "experiments" / "gaps").mkdir(parents=True)
        shutil.copy(
            REPO / "experiments" / "gaps" / "test_gaps_refactor.py",
            scratch / "experiments" / "gaps" / "test_gaps_refactor.py",
        )

        services_target = scratch / "src" / "services.py"
        services_target.write_text(
            services_target.read_text(encoding="utf-8") + "\n\n" + code,
            encoding="utf-8",
        )

        passed, total, behavior_passed, structure_passed, tail = run_grading(scratch)
        return {
            "model": model,
            "passed": passed,
            "total": total,
            "behavior_passed": behavior_passed,
            "structure_passed": structure_passed,
            "extracted": True,
            "elapsed_s": llm["elapsed_s"],
            "input_tokens": llm["prompt_eval_count"],
            "output_tokens": llm["eval_count"],
            "scratch_dir": str(scratch) if keep_scratch else None,
            "tail": tail,
        }
    finally:
        if not keep_scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:latest")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--keep-scratch", action="store_true")
    args = parser.parse_args()

    print(f"Model:  {args.model}")
    print(f"Trials: {args.trials}")
    print()

    results = []
    for i in range(1, args.trials + 1):
        print(f"=== Trial {i} ===")
        r = run_one_trial(args.model, args.keep_scratch)
        results.append(r)
        print(f"  passed:   {r['passed']}/{r['total']}  "
              f"(behavior {r['behavior_passed']}/20, structure {r['structure_passed']}/9)")
        print(f"  latency:  {r['elapsed_s']:.1f}s")
        print(f"  tokens:   in={r['input_tokens']}  out={r['output_tokens']}")
        if r.get("error"):
            print(f"  error:    {r['error']}")
        if r.get("scratch_dir"):
            print(f"  scratch:  {r['scratch_dir']}")
        print()

    print("=== Summary ===")
    successes = sum(1 for r in results if r["passed"] == r["total"])
    mean_passed = sum(r["passed"] for r in results) / len(results)
    mean_beh = sum(r["behavior_passed"] for r in results) / len(results)
    mean_struct = sum(r["structure_passed"] for r in results) / len(results)
    mean_latency = sum(r["elapsed_s"] for r in results) / len(results)
    mean_out = sum(r["output_tokens"] for r in results) / len(results)
    print(f"Perfect runs:  {successes}/{args.trials}")
    print(f"Mean passed:   {mean_passed:.1f}/29")
    print(f"  behavior:    {mean_beh:.1f}/20")
    print(f"  structure:   {mean_struct:.1f}/9")
    print(f"Mean latency:  {mean_latency:.1f}s")
    print(f"Mean out tok:  {mean_out:.0f}")

    outpath = REPO / "benchmarks" / f"ollama_gaps_ref_{args.model.replace(':', '_').replace('/', '_')}.json"
    outpath.write_text(json.dumps({"model": args.model, "results": results}, indent=2))
    print(f"\nFull results: {outpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
