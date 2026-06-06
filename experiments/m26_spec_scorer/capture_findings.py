"""M26 — capture the 6 pilot findings into the loom store, then print the
generated REQ IDs for inclusion in FINDINGS.md.

Run once. Findings are captured as kind=finding, deriving from REQ-3896db58
(methodology pattern) and REQ-6dec889f (the M26 architecture req).
"""
from __future__ import annotations

import sys
from pathlib import Path

from loom.store import LoomStore
from loom.services import extract


FINDINGS = [
    {
        "domain": "operational",
        "value": (
            "M26 pilot finding F1 — `loom decompose` silently falls back to "
            "the local qwen model when ANTHROPIC_API_KEY is not exported in "
            "the Python process environment. The fallback is not warned. "
            "Observed: shell `[ -n $ANTHROPIC_API_KEY ]` returned true via "
            "quoting accident; Python's os.environ.get returned None; "
            "decompose output reported model=ollama:qwen2.5-coder:32b "
            "without any indicator. The asymmetric pipeline (Opus decomposes, "
            "qwen executes) silently degenerated to qwen-only. Mitigation in "
            "v2: warn loudly when falling back from anthropic to ollama, or "
            "require --model explicitly when ANTHROPIC_API_KEY is missing."
        ),
        "rationale": (
            "Surfaced during M26 dogfooding pilot. The headline thesis 'small "
            "model executes what a frontier model decomposes' is undertested "
            "for users without API keys. A silent fallback means users may "
            "think they are using the asymmetric pipeline when they are not, "
            "and may attribute task failures to qwen-execution when the "
            "decomposition itself was qwen-quality."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
    {
        "domain": "architecture",
        "value": (
            "M26 pilot finding F2 — qwen2.5-coder:32b decomposing a "
            "loom-self spec emitted `files_to_modify: src/cli.py` when the "
            "actual location since M9 has been `src/loom/cli.py`. Two of "
            "six tasks in the raw decompose output had wrong paths. The "
            "decomposer was given the SPEC text but not repository layout "
            "context, so it relied on training-data priors for project "
            "structure. Mitigation in v2: ground the decomposer with a "
            "repo-tree summary, or run a post-decompose path-existence "
            "check that rejects non-existent parent directories."
        ),
        "rationale": (
            "Confirms M22c finding REQ-7e2d6518 (model file-path "
            "hallucination from training-data layout priors) generalizes "
            "from Dart to the decomposer use case. The asymmetric pipeline "
            "assumes the decomposer knows where files live; without "
            "explicit grounding it does not."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
    {
        "domain": "architecture",
        "value": (
            "M26 pilot finding F3 — `loom decompose` produced two tasks "
            "that would have modified pre-registration-locked files "
            "(tests/data/spec_scoring_calibration.json and "
            "tests/test_spec_scoring.py). No mechanism told the decomposer "
            "those files were locked. Without filtering, loom_exec would "
            "have overwritten the calibration set, silently invalidating "
            "the M26 experiment. Mitigation in v2: Specification dataclass "
            "should support a `protected_files` field, or `loom decompose` "
            "should refuse to emit tasks targeting files that already "
            "exist and are referenced as test data."
        ),
        "rationale": (
            "Pre-registration only works if the pre-reg artifacts are "
            "actually frozen. The methodology pattern REQ-3896db58 "
            "depends on this; the asymmetric pipeline must honor it. "
            "Discovered when hand-reviewing proposed_tasks.original.yaml "
            "before applying — would have been invisible if --apply had "
            "been used directly."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
    {
        "domain": "architecture",
        "value": (
            "M26 pilot finding F4 — SPEC-85e02906 explicitly named "
            "`src/loom/prompts/spec_score.txt` as an implementation file. "
            "The decomposer emitted no task for it. The omission would "
            "have surfaced as a runtime error when the scorer module "
            "tried to load the prompt template. Suggests the decomposer "
            "parses spec text for code-shaped artifacts but not for "
            "non-code assets named alongside them. Mitigation in v2: "
            "parse spec description for filename-shaped tokens "
            "(extension regex), ensure each gets a task."
        ),
        "rationale": (
            "Complements F2: the decomposer's repo-layout blind spot "
            "extends to non-Python assets. The asymmetric pipeline needs "
            "an awareness layer that surfaces every file the SPEC "
            "implies needs to exist, regardless of extension."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
    {
        "domain": "architecture",
        "value": (
            "M26 pilot finding F5 — `loom_exec`'s assembled prompt "
            "(per --dry-run on the prompt-file task) hard-codes 'Reply "
            "with ONE python code block' and 'The model output is APPENDED "
            "to the end of the target file' regardless of file extension. "
            "For task 1 (authoring src/loom/prompts/spec_score.txt), this "
            "would have instructed qwen to produce Python code, then "
            "appended that code to a .txt file. Garbage guaranteed. "
            "Mitigation in v2: per-extension output-contract block — "
            "python fence for .py, text-block for .txt/.md, json fence "
            "for .json — and replace-mode default for non-Python files."
        ),
        "rationale": (
            "The asymmetric pipeline's executor prompt was authored "
            "assuming Python-only targets (the Phase D pyschema "
            "benchmark). Extending to multi-runtime via "
            "runners.py covers the test side; the prompt template was "
            "never updated for the produce side."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
    {
        "domain": "architecture",
        "value": (
            "M26 pilot finding F6 — `loom decompose` used a single "
            "`test_to_write` (the full TestSpecScoring grading test) "
            "for all five tasks. The grading test imports "
            "services.score_specification at module load; tasks 1-4 do "
            "not produce that symbol. Therefore tasks 1-4 cannot pass "
            "their grading test until task 5 (the implementation) lands "
            "— at which point all four prior tasks become redundant. "
            "loom_exec would reject each early task as 'test failed'. "
            "Mitigation in v2: decomposer must scope `test_to_write` per "
            "task — smoke tests for early tasks (does the file exist? "
            "does the symbol import?), full grading reserved for the "
            "final integration task."
        ),
        "rationale": (
            "Reveals a structural mismatch between α-mode "
            "(eval-as-grading-test, one big test) and the atomic-task "
            "decomposition pattern (≤80 LoC each). The two are "
            "incompatible without per-task grading. The methodology "
            "pattern REQ-3896db58's pre-registration is preserved by "
            "the final-task grading, but the executor wastes attempts "
            "on tasks it cannot pass."
        ),
        "kind": "finding",
        "status": "confirmed",
    },
]


def main() -> int:
    store = LoomStore(
        project="loom",
        data_dir=Path.home() / ".openclaw" / "loom" / "loom",
    )

    parent_ids = ["REQ-3896db58", "REQ-6dec889f", "REQ-7df25683"]
    captured: list[str] = []

    for fx in FINDINGS:
        try:
            result = extract(
                store=store,
                domain=fx["domain"],
                value=fx["value"],
                rationale=fx["rationale"],
                kind=fx["kind"],
                rationale_links=parent_ids,
                status=fx.get("status"),
            )
        except Exception as exc:  # pragma: no cover — surfacing only
            print(f"FAILED to capture finding: {exc}", file=sys.stderr)
            print(f"  text head: {fx['value'][:80]}", file=sys.stderr)
            continue
        rid = result.get("req_id") if isinstance(result, dict) else str(result)
        captured.append(rid)
        head = fx["value"][:70].replace("\n", " ")
        print(f"  {rid}  {head}...")

    print()
    print(f"Captured {len(captured)} finding(s).")
    print("REQ IDs (paste into FINDINGS.md):")
    for rid in captured:
        print(f"  - {rid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
