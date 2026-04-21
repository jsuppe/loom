"""
Harder-task comparator: extend existing gaps() with drift detection.

Starting state: src/services.py has a working gaps() covering missing_criteria,
missing_elaboration, and orphan_impl.  Model must READ and MODIFY the existing
function to add a 4th gap type (drift) without regressing the original three.

Grade target: experiments/gaps/test_gaps_extend.py has 20 tests (14 from the
baseline + 6 drift-specific). Passing all 20 proves the model preserved the
existing behavior AND correctly added the new type.

This is single-turn code-generation over a more complex starting context.
Tougher than ollama_gaps.py, where the file contents provided no gaps() to
read — here the model must interpret an existing function and extend it.

Usage:
    python benchmarks/ollama_gaps_extend.py --model qwen3.5:latest --trials 3
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


CONTEXT_EXTENSION = """\
## Extension to SPEC-gaps-1: drift detection

The `gaps()` function already surfaces three types: `missing_criteria`,
`missing_elaboration`, `orphan_impl`. Add a fourth type:

    drift — A superseded requirement that still has at least one linked
            implementation. The implementation may also point at live reqs
            (it need NOT be an orphan_impl); what matters is that the
            superseded req's id appears in some Implementation's `satisfies`
            list.

Priority: 2 (surfaces before missing_criteria which is priority 3).

Gap record fields for drift:
    type             = "drift"
    entity_id        = the superseded req's id (NOT the impl's)
    description      = human-readable, e.g. "REQ-xyz is superseded but still has linked implementations"
    blocks           = list of impl ids that link to the superseded req (may be [])
    suggested_action = a single runnable command, e.g. "loom link <file> --req <new_req_id>"

Important: emit exactly ONE drift gap per superseded req (dedupe by req.id,
even if multiple impls point at it).

The priority table is now:

| Priority | Type                  |
|----------|-----------------------|
| 1        | unresolved_conflict   | (future task; still reserve slot)
| 2        | drift                 | ← NEW
| 3        | missing_criteria      |
| 4        | missing_spec          | (future task; still reserve slot)
| 5        | missing_elaboration   |
| 6        | orphan_impl           |

## Preservation requirements

- All 14 existing grading tests for gaps() must still pass (no regression).
- The existing 3 gap types' behavior must be unchanged.
- The uniform shape `{type, entity_id, description, blocks, suggested_action}`
  applies to drift just like the others.
- Sort key remains `(priority, entity_id)`.
- `types` filter and `limit` cap both apply to drift.
"""


TASK = """The current `services.gaps()` function in src/services.py already handles three gap types: missing_criteria, missing_elaboration, orphan_impl.

Extend it to also detect DRIFT per the specification above.

Output requirements:
- Reply with ONE Python code block: ```python ... ```
- The block must contain a COMPLETE replacement `gaps` function (plus any small helpers if you need them).
- Your output will be appended to src/services.py; Python's last-definition-wins means your new gaps() will shadow the existing one. So include the ENTIRE function body — all 4 gap types.
- Do NOT include any other code from services.py.
- Do NOT include explanations, prose, or markdown headings outside the code block.

Begin your response with ```python and end with ``` (followed by nothing)."""


def build_prompt(services_py: str, store_py: str) -> str:
    return (
        "You are extending an existing Python function in a codebase.\n\n"
        "=== LOOM CONTEXT ===\n\n"
        f"{CONTEXT_EXTENSION}\n\n"
        "=== Current src/services.py (contains the existing gaps() function to extend) ===\n"
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


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    payload = json.dumps({
        "model": model,
        "stream": False,
        "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 6000},
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


def run_grading(scratch: Path) -> tuple[int, int, str]:
    res = subprocess.run(
        [sys.executable, "-m", "pytest",
         "experiments/gaps/test_gaps_extend.py", "-v", "--tb=line"],
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
        total = 20
        passed = 0
    tail = "\n".join(combined.splitlines()[-14:])
    return passed, total, tail


def run_one_trial(model: str, keep_scratch: bool) -> dict:
    services_py = (REPO / "src" / "services.py").read_text(encoding="utf-8")
    store_py = (REPO / "src" / "store.py").read_text(encoding="utf-8")

    prompt = build_prompt(services_py, store_py)
    llm = call_ollama(model, prompt)
    code = extract_code(llm["content"])

    if code is None:
        return {
            "model": model,
            "passed": 0,
            "total": 20,
            "extracted": False,
            "elapsed_s": llm["elapsed_s"],
            "input_tokens": llm["prompt_eval_count"],
            "output_tokens": llm["eval_count"],
            "error": "no code block",
            "content_preview": llm["content"][:400],
        }

    scratch = Path(tempfile.mkdtemp(prefix="ollama_gaps_ext_"))
    try:
        shutil.copytree(REPO / "src", scratch / "src")
        shutil.copytree(REPO / "tests", scratch / "tests")
        (scratch / "experiments" / "gaps").mkdir(parents=True)
        shutil.copy(
            REPO / "experiments" / "gaps" / "test_gaps_extend.py",
            scratch / "experiments" / "gaps" / "test_gaps_extend.py",
        )

        services_target = scratch / "src" / "services.py"
        # Append model output — Python's last-def-wins means a new gaps()
        # definition shadows the one already in services.py.
        services_target.write_text(
            services_target.read_text(encoding="utf-8") + "\n\n" + code,
            encoding="utf-8",
        )

        passed, total, tail = run_grading(scratch)
        return {
            "model": model,
            "passed": passed,
            "total": total,
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
        print(f"  passed:   {r['passed']}/{r['total']}")
        print(f"  latency:  {r['elapsed_s']:.1f}s")
        print(f"  tokens:   in={r['input_tokens']}  out={r['output_tokens']}")
        if r.get("error"):
            print(f"  error: {r['error']}")
        if r.get("scratch_dir"):
            print(f"  scratch: {r['scratch_dir']}")
        print()

    print("=== Summary ===")
    successes = sum(1 for r in results if r["passed"] == r["total"])
    mean_passed = sum(r["passed"] for r in results) / len(results)
    mean_latency = sum(r["elapsed_s"] for r in results) / len(results)
    mean_out = sum(r["output_tokens"] for r in results) / len(results)
    print(f"Perfect runs:  {successes}/{args.trials}")
    print(f"Mean passed:   {mean_passed:.1f}/20")
    print(f"Mean latency:  {mean_latency:.1f}s")
    print(f"Mean out tok:  {mean_out:.0f}")

    outpath = REPO / "benchmarks" / f"ollama_gaps_ext_{args.model.replace(':', '_').replace('/', '_')}.json"
    outpath.write_text(json.dumps({"model": args.model, "results": results}, indent=2))
    print(f"\nFull results: {outpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
