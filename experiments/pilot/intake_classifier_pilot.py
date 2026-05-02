#!/usr/bin/env python3
"""
M11.5 P0 — Intake-classifier precision/recall pilot.

Purpose: validate the prompt + model combo for the requirement-shape
classifier proposed in `docs/DESIGN-rationale-linkage.md` Part 2.
The intake hook (M11.5) auto-captures requirements from chat
messages, so the classifier MUST have high precision (false positives
pollute the store with noise). The bar is precision ≥ 90%; recall is
secondary.

Reads the labeled dataset at
``experiments/pilot/intake_classifier_dataset.json`` (40 utterances,
20 positive + 20 negative), runs each through the classifier prompt
via ``services._call_decomposer_llm``, parses the JSON output, and
scores against the ground-truth labels.

Usage::

    python experiments/pilot/intake_classifier_pilot.py
    LOOM_INTAKE_MODEL=ollama:qwen3.5:latest python experiments/pilot/intake_classifier_pilot.py
    LOOM_INTAKE_MODEL=anthropic:claude-haiku-4-5-20251001 python experiments/pilot/intake_classifier_pilot.py

Default model: anthropic:claude-haiku-4-5-20251001 if ANTHROPIC_API_KEY,
else ollama:qwen3.5:latest.

Output: per-utterance verdict + summary (precision, recall, F1,
median latency). Exits 0 if precision ≥ 0.90, else 1 — gate-friendly.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOOM_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LOOM_DIR / "src"))

from loom import services  # noqa: E402


DATASET = LOOM_DIR / "experiments" / "pilot" / "intake_classifier_dataset.json"


# Verbatim from docs/DESIGN-rationale-linkage.md M11.5 spec.
CLASSIFIER_PROMPT = """\
You are a requirement-detection classifier for a software project.
The user just sent a message in a chat about the project. Decide
whether the message contains a SOFTWARE REQUIREMENT — a statement
about how the system MUST or SHOULD behave, look, or be structured.

NOT requirements:
  - Questions ("can you...", "what does...", "how do I...")
  - Code edits or fixes ("fix the bug", "make this work")
  - Style preferences without behavior implications ("use 4 spaces")
  - Commentary on the agent's work ("looks good", "try again")

ARE requirements:
  - "X must do Y when Z"
  - "We should rate-limit endpoint X"
  - "Users need to see Y before deleting"
  - "Don't ever propagate errors from the retry loop"

Output JSON only, exactly one of:

  {{"is_requirement": false}}

  {{"is_requirement": true,
    "domain": "behavior" | "ui" | "data" | "architecture" | "terminology",
    "value": "<one-sentence requirement statement>",
    "rationale_excerpt": "<verbatim sentence from the message that explains WHY, or empty string if not present>"}}

User message:
\"\"\"
{user_message}
\"\"\"
"""


def default_model() -> str:
    if env := os.environ.get("LOOM_INTAKE_MODEL"):
        return env
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic:claude-haiku-4-5-20251001"
    return "ollama:qwen3.5:latest"


def parse_classifier_output(content: str) -> dict | None:
    """Parse the classifier's JSON. Tolerates a few common deviations:
    leading/trailing prose, ```json fences, etc. Returns None when the
    output truly can't be parsed — the production hook treats that as
    'not a requirement' (silent no-op)."""
    text = content.strip()
    # Strip code fences if present.
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    # Find the last balanced JSON object in the text.
    obj = _last_json_object(text)
    if obj is None:
        return None
    if not isinstance(obj, dict):
        return None
    if not obj.get("is_requirement"):
        return {"is_requirement": False}
    if not obj.get("domain") or not obj.get("value"):
        return None
    return obj


def _last_json_object(text: str) -> object:
    """Return the last top-level JSON object found in ``text``, or
    None on miss. Walks brace depth so we tolerate prose around it."""
    depth = 0
    start = -1
    last_obj_str = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                last_obj_str = text[start:i + 1]
                start = -1
    if not last_obj_str:
        return None
    try:
        return json.loads(last_obj_str)
    except json.JSONDecodeError:
        return None


def classify(model: str, utterance: str, *, timeout: int = 60) -> dict:
    """Call the classifier and return ``{output, latency_ms,
    raw_content, error}``. ``output`` is the parsed dict (or None on
    parse failure)."""
    prompt = CLASSIFIER_PROMPT.format(user_message=utterance)
    t0 = time.time()
    try:
        resp = services._call_decomposer_llm(model, prompt, timeout=timeout)
    except Exception as e:
        return {
            "output": None,
            "latency_ms": int((time.time() - t0) * 1000),
            "raw_content": "",
            "error": str(e),
        }
    return {
        "output": parse_classifier_output(resp.get("content", "")),
        "latency_ms": int((time.time() - t0) * 1000),
        "raw_content": resp.get("content", ""),
        "error": None,
    }


def run_pilot() -> int:
    model = default_model()
    print(f"=== Intake classifier pilot (M11.5 P0) ===")
    print(f"Model:   {model}")
    print(f"Dataset: {DATASET.name}")
    print()

    data = json.loads(DATASET.read_text(encoding="utf-8"))
    utterances = data["utterances"]

    results = []
    print(f"{'#':<5} {'truth':<8} {'pred':<8} {'verdict':<6} "
          f"{'lat ms':<8} {'text'[:60]}")
    print("-" * 100)
    for u in utterances:
        truth = u["is_requirement"]
        out = classify(model, u["text"])
        if out["error"]:
            pred = None
            note = f"error: {out['error'][:40]}"
        elif out["output"] is None:
            pred = None
            note = "parse_failed"
        else:
            pred = bool(out["output"].get("is_requirement"))
            note = ""

        if pred is None:
            verdict = "ERR"
        elif pred == truth:
            verdict = "✓"
        elif pred and not truth:
            verdict = "FP"  # false positive — the worst kind
        else:
            verdict = "FN"  # false negative

        results.append({
            "id": u["id"],
            "truth": truth,
            "pred": pred,
            "verdict": verdict,
            "latency_ms": out["latency_ms"],
            "raw": out["raw_content"][:200],
            "note": note,
            "expected_domain": u.get("expected_domain"),
            "predicted_domain": (out["output"] or {}).get("domain"),
        })
        print(f"{u['id']:<5} {str(truth):<8} {str(pred):<8} "
              f"{verdict:<6} {out['latency_ms']:<8} "
              f"\"{u['text'][:55]}{'...' if len(u['text']) > 55 else ''}\"")

    # ---- Summary stats ----
    tp = sum(1 for r in results if r["verdict"] == "✓" and r["truth"])
    tn = sum(1 for r in results if r["verdict"] == "✓" and not r["truth"])
    fp = sum(1 for r in results if r["verdict"] == "FP")
    fn = sum(1 for r in results if r["verdict"] == "FN")
    err = sum(1 for r in results if r["verdict"] == "ERR")
    n = len(results)

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    f1 = (2 * precision * recall / (precision + recall)
          if (tp + fp) and (tp + fn) else float("nan"))
    accuracy = (tp + tn) / n if n else 0.0

    latencies = sorted(r["latency_ms"] for r in results if r["latency_ms"])
    p50 = latencies[len(latencies) // 2] if latencies else 0
    p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0

    print()
    print("=== Summary ===")
    print(f"N:            {n}  (TP {tp} / FP {fp} / TN {tn} / FN {fn} / ERR {err})")
    print(f"Precision:    {precision:.3f}  (false positives / wrongly-captured)")
    print(f"Recall:       {recall:.3f}  (real reqs / detected)")
    print(f"F1:           {f1:.3f}")
    print(f"Accuracy:     {accuracy:.3f}")
    print(f"Latency p50:  {p50} ms")
    print(f"Latency p95:  {p95} ms")
    print()

    if fp:
        print("=== False positives (the worst failure mode) ===")
        for r in results:
            if r["verdict"] == "FP":
                u = next(x for x in utterances if x["id"] == r["id"])
                print(f"  {r['id']}: \"{u['text']}\"")
                print(f"    pred domain={r['predicted_domain']}")
                print(f"    raw: {r['raw'][:180]}")
        print()

    if fn:
        print("=== False negatives (real reqs missed) ===")
        for r in results:
            if r["verdict"] == "FN":
                u = next(x for x in utterances if x["id"] == r["id"])
                print(f"  {r['id']}: \"{u['text']}\"")
        print()

    # Domain accuracy on true positives.
    tp_with_domain = [
        r for r in results
        if r["verdict"] == "✓" and r["truth"]
        and r["expected_domain"] and r["predicted_domain"]
    ]
    if tp_with_domain:
        domain_match = sum(
            1 for r in tp_with_domain
            if r["predicted_domain"] == r["expected_domain"]
        )
        print(f"Domain accuracy (on true positives): "
              f"{domain_match}/{len(tp_with_domain)} = "
              f"{100*domain_match/len(tp_with_domain):.0f}%")
        print()

    # Persist the full result set for follow-up analysis.
    out_path = LOOM_DIR / "experiments" / "pilot" / f"intake_classifier_results_{model.replace(':', '_').replace('/', '_')}.json"
    out_path.write_text(json.dumps({
        "model": model,
        "summary": {
            "n": n, "tp": tp, "tn": tn, "fp": fp, "fn": fn, "err": err,
            "precision": precision, "recall": recall, "f1": f1,
            "accuracy": accuracy, "p50_ms": p50, "p95_ms": p95,
        },
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"Detailed results written: {out_path}")
    print()

    # Gate.
    if precision >= 0.90:
        print(f"PASS — precision {precision:.3f} ≥ 0.90 gate")
        return 0
    print(f"FAIL — precision {precision:.3f} < 0.90 gate; "
          f"iterate on prompt or model before P1")
    return 1


if __name__ == "__main__":
    sys.exit(run_pilot())
