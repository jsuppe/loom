"""
Ollama-based comparator for TASK-gaps-1.

Runs a local LLM via Ollama on the enhanced-condition prompt (spec + sidecar
inlined), extracts the generated `gaps` function from the response, splices
it into a scratch copy of services.py, and runs the canonical grading test.

This is a SINGLE-TURN code generation test — no tool loop, no retries.
That's a tougher bar than the subagent experiments (where Haiku/Opus could
Read/Edit/Bash). If qwen succeeds here it's the strongest form of the thesis:
a ~10B local model produces spec-conformant code from a single prompt.

Usage:
    python benchmarks/ollama_gaps.py --model qwen3.5:latest --trials 3
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


CONTEXT_BUNDLE = """\
## Requirements

### REQ-gaps-1 [behavior]
Value: A `loom gaps` command surfaces outstanding gaps across the project, ordered by what blocks execution progress.
Rationale: Without a single inventory, users re-derive state from `loom incomplete` + `loom doctor` + `loom trace` every session.
Acceptance criteria: Returns all gaps for active (non-superseded) reqs by default; supports --type (repeatable), --json, --limit; exit code 2 if any drift or unresolved_conflict present.

### REQ-gaps-2 [data]
Value: Each gap has a uniform shape: {type, entity_id, description, blocks, suggested_action}.
Rationale: Uniform shape lets agents process gap lists without branching per-field. Matches the contract services.* functions follow.
Acceptance criteria: Every gap has all 5 fields populated (no None). `blocks` is always a list (may be empty). `suggested_action` is a single runnable command string.

### REQ-gaps-3 [behavior]
Value: Gaps are ordered by what they block (execution > planning > docs).
Rationale: When an agent has limited turns, highest-leverage gaps surface first.
Acceptance criteria: Sorted by priority, ties by entity_id ascending.

## Specification

### SPEC-gaps-1
Signature: `services.gaps(store, types=None, limit=None) -> list[dict]`

Gap types, in priority order (most important first - LOWER priority number surfaces FIRST):

| Priority | Type                  | Meaning |
|----------|-----------------------|---------|
| 1        | unresolved_conflict   | (future task; reserve slot) |
| 2        | drift                 | (future task; reserve slot) |
| 3        | missing_criteria      | active req with empty acceptance_criteria |
| 4        | missing_spec          | (future task; reserve slot) |
| 5        | missing_elaboration   | active req with empty elaboration |
| 6        | orphan_impl           | implementation whose every linked req is missing or superseded |

This task implements ONLY: missing_criteria, missing_elaboration, orphan_impl. The other slots are reserved for follow-up tasks - do not emit them.

Uniform gap record shape: `{type, entity_id, description, blocks, suggested_action}`.
- `type`: one of the type names above
- `entity_id`: the REQ-xxx or IMPL-xxx
- `description`: short human-readable summary
- `blocks`: list of entity_ids this gap blocks (may be empty)
- `suggested_action`: a single runnable CLI command string

Filter `types` (if provided): only return gaps whose type is in the list.
`limit` (if provided): cap at N after sorting.

Superseded reqs are silently skipped for missing_criteria / missing_elaboration (they're not actionable gaps). An impl is orphan if EVERY linked req_id is missing or superseded. An impl with at least one live linked req is NOT orphan.

Sort key: `(priority_number_ascending, entity_id_ascending)`. Priority 3 (missing_criteria) surfaces before priority 5 (missing_elaboration) which surfaces before priority 6 (orphan_impl). Ties broken by entity_id lexicographically ascending.

## Sidecar excerpt: `src/services.py`

HARD RULES (the file's invariants you must follow):
1. No print, no sys.exit, no argparse. Services return plain data.
2. LookupError for target-not-found. ValueError for caller-prevented errors.
3. Write services return warnings dicts on partial failure, not raise.
4. Never raise for empty result - return [].
5. Deterministic ordering - every list sorted by stable key.

CHROMADB GOTCHAS:
- Empty lists are rejected by the metadata validator, so dataclasses substitute ["TBD"] in to_dict. When reading metadata back, treat ["TBD"] the same as [] or None - all mean "unset".
- from_dict uses setdefault for newly-added fields; preserve this pattern.

PATTERNS:
- store.get_requirement(id) -> Requirement | None
- store.get_implementation(id) -> Implementation | None
- Iterate all reqs: store.requirements.get(include=["metadatas"]) and walk the parallel ids/metadatas arrays.
- Check superseded: `req.superseded_at is not None`.

IMPLEMENTATION.SATISFIES:
- `[{"req_id": "REQ-abc"}, ...]`. Stored in ChromaDB metadata JSON-serialized under key `satisfies`; parse with `json.loads(meta["satisfies"])`.

COMPLETENESS:
- `Requirement.is_complete()` returns True iff elaboration is truthy AND acceptance_criteria is non-empty (not None, not [], not ["TBD"]).

RELATED SERVICES:
- `services.incomplete(store)` - existing, returns active reqs missing elab/criteria in a different shape. `gaps()` is the uniform-shape replacement; leave incomplete() alone.
"""


TASK = """Implement `services.gaps(store, types=None, limit=None) -> list[dict]` per SPEC-gaps-1 above.

Match the conventions of existing functions in src/services.py (imports, error handling, docstring style, early returns).

Output requirements:
- Reply with ONE Python code block: ```python ... ```
- The block must contain the complete `gaps` function (plus any small module-level helpers you introduce).
- Do NOT include any existing code from services.py. Do NOT include the rest of the file.
- Do NOT include explanations, prose, or markdown headings outside the code block.

Begin your response with ```python and end with ``` (followed by nothing)."""


def build_prompt(services_py: str, store_excerpt: str) -> str:
    return (
        "You are implementing a single function in an existing Python codebase.\n\n"
        "=== PRE-INJECTED LOOM CONTEXT (what the hook would inject for this task) ===\n\n"
        f"{CONTEXT_BUNDLE}\n\n"
        "=== Current src/services.py (full file, for style + imports) ===\n"
        "```python\n"
        f"{services_py}\n"
        "```\n\n"
        "=== Relevant excerpt of src/store.py (dataclasses + LoomStore API) ===\n"
        "```python\n"
        f"{store_excerpt}\n"
        "```\n\n"
        "=== TASK ===\n"
        f"{TASK}\n"
    )


def _extract_store_excerpt(store_py: str) -> str:
    # Trim store.py to dataclasses + the top-level LoomStore class doc +
    # public method signatures. We skip the very long __init__ setup so the
    # prompt stays lean while still exposing what gaps() needs.
    lines = store_py.splitlines()
    out: list[str] = []
    keep = True
    for i, ln in enumerate(lines):
        # Very rough filter: keep everything up to the end of the file.
        # Simpler: just send the whole file - store.py is ~800 lines.
        out.append(ln)
    return "\n".join(out)


def call_ollama(model: str, prompt: str, timeout: int = 600) -> dict:
    payload = json.dumps({
        "model": model,
        "stream": False,
        "think": False,  # disable thinking preamble on thinking models
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0.0, "num_predict": 4000},
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
        "thinking": msg.get("thinking", ""),
        "elapsed_s": round(elapsed, 2),
        "eval_count": body.get("eval_count", 0),
        "prompt_eval_count": body.get("prompt_eval_count", 0),
        "total_duration_ns": body.get("total_duration", 0),
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
    """Run grading test in scratch. Returns (passed, total, tail_of_output)."""
    res = subprocess.run(
        [sys.executable, "-m", "pytest",
         "experiments/gaps/test_gaps_task1.py", "-v", "--tb=line"],
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
        # pytest couldn't collect - probably a SyntaxError or ImportError
        total = 14  # we know there are 14 tests in the canonical grading file
        passed = 0
    tail = "\n".join(combined.splitlines()[-12:])
    return passed, total, tail


def run_one_trial(model: str, keep_scratch: bool) -> dict:
    services_py = (REPO / "src" / "services.py").read_text(encoding="utf-8")
    store_py = (REPO / "src" / "store.py").read_text(encoding="utf-8")
    store_excerpt = _extract_store_excerpt(store_py)

    prompt = build_prompt(services_py, store_excerpt)

    llm = call_ollama(model, prompt)
    code = extract_code(llm["content"])

    if code is None:
        return {
            "model": model,
            "passed": 0,
            "total": 14,
            "extracted": False,
            "elapsed_s": llm["elapsed_s"],
            "input_tokens": llm["prompt_eval_count"],
            "output_tokens": llm["eval_count"],
            "error": "no code block in response",
            "content_preview": llm["content"][:400],
        }

    scratch = Path(tempfile.mkdtemp(prefix="ollama_gaps_"))
    try:
        shutil.copytree(REPO / "src", scratch / "src")
        shutil.copytree(REPO / "tests", scratch / "tests")
        (scratch / "experiments" / "gaps").mkdir(parents=True)
        shutil.copy(
            REPO / "experiments" / "gaps" / "test_gaps_task1.py",
            scratch / "experiments" / "gaps" / "test_gaps_task1.py",
        )

        services_target = scratch / "src" / "services.py"
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
    parser.add_argument("--keep-scratch", action="store_true",
                        help="retain temp dirs for inspection")
    args = parser.parse_args()

    print(f"Model:  {args.model}")
    print(f"Trials: {args.trials}")
    print()

    results = []
    for i in range(1, args.trials + 1):
        print(f"=== Trial {i} ===")
        r = run_one_trial(args.model, args.keep_scratch)
        results.append(r)
        print(f"  passed: {r['passed']}/{r['total']}")
        print(f"  extracted: {r.get('extracted', False)}")
        print(f"  latency: {r['elapsed_s']:.1f}s")
        print(f"  tokens:  in={r['input_tokens']}  out={r['output_tokens']}")
        if r.get("error"):
            print(f"  error: {r['error']}")
            print(f"  preview: {r.get('content_preview', '')[:200]}")
        if r.get("scratch_dir"):
            print(f"  scratch: {r['scratch_dir']}")
        print()

    print("=== Summary ===")
    successes = sum(1 for r in results if r["passed"] == r["total"])
    mean_passed = sum(r["passed"] for r in results) / len(results)
    mean_latency = sum(r["elapsed_s"] for r in results) / len(results)
    mean_in = sum(r["input_tokens"] for r in results) / len(results)
    mean_out = sum(r["output_tokens"] for r in results) / len(results)
    print(f"Perfect runs: {successes}/{args.trials}")
    print(f"Mean passed:  {mean_passed:.1f}/14")
    print(f"Mean latency: {mean_latency:.1f}s")
    print(f"Mean tokens:  in={mean_in:.0f}  out={mean_out:.0f}")

    outpath = REPO / "benchmarks" / f"ollama_gaps_{args.model.replace(':', '_').replace('/', '_')}.json"
    outpath.write_text(json.dumps({"model": args.model, "results": results}, indent=2))
    print(f"\nFull results: {outpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
