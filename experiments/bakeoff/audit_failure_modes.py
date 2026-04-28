#!/usr/bin/env python3
"""
audit_failure_modes.py — categorize every failure across all bakeoff
trials, to answer: of multi-file failures, what fraction are
*typelink-shaped* (cross-file type / signature mismatches that a
typelink primitive would catch)?

Output: a categorized report, both per-phase and aggregate.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from collections import Counter

REPO = Path(__file__).resolve().parent.parent.parent
RUNS = REPO / "experiments" / "bakeoff" / "runs-v2"

# Failure-mode categories. Each is a list of (label, regex) pairs;
# first match wins. Order matters — more specific first.
TYPELINK_PATTERNS = [
    # Missing definitions / linker errors — "you declared but didn't define"
    ("missing_definition_link", r"undefined reference to `(\w+::\w+)"),
    ("missing_definition_link", r"undefined reference to `(\w+)\("),
    # Wrong signature — call site can't find a matching declaration
    ("signature_mismatch", r"no matching function for call to ['\"]?(\w+)"),
    ("signature_mismatch", r"Cannot invoke a non-'const' constructor"),
    ("signature_mismatch", r"Required named parameter '(\w+)' must be provided"),
    ("signature_mismatch", r"No named parameter with the name '(\w+)'"),
    ("signature_mismatch", r"Too few positional arguments: \d+ required, \d+ given"),
    ("signature_mismatch", r"Too many positional arguments"),
    # Symbol not found in producer file
    ("missing_symbol", r"cannot import name '(\w+)' from"),
    ("missing_symbol", r"Couldn't find constructor '(\w+)'"),
    ("missing_symbol", r"The (?:getter|setter|method) '(\w+)' isn't defined"),
    ("missing_symbol", r"Method not found: '(\w+)'"),
    ("missing_symbol", r"Undefined name '(\w+)'"),
    ("missing_symbol", r"isn't a type that can be thrown"),
    ("missing_symbol", r"name '(\w+)' is not defined"),
    ("missing_symbol", r"AttributeError: .* has no attribute '(\w+)'"),
    # Field-init / type-shape problems (Address w/ wrong field shape)
    ("type_shape", r"Field '(\w+)' should be initialized"),
    ("type_shape", r"Field '(\w+)' is not initialized"),
    ("type_shape", r"final field '(\w+)' is not initialized"),
    ("type_shape", r"Final field '(\w+)' is not initialized"),
    ("type_shape", r"Cannot construct .* missing argument"),
    ("type_shape", r"Type '(\w+)' is not a subtype"),
]

INFRA_PATTERNS = [
    ("ollama_500", r"HTTP Error 500"),
    ("ollama_500", r"llama runner has terminated"),
    ("ollama_500", r"ollama call failed"),
    ("compile_timeout", r"Timeout|timeout|timed out"),
    ("driver_keyerror", r"KeyError"),
]

SYNTAX_PATTERNS = [
    ("syntax_error", r"SyntaxError"),
    ("syntax_error", r"unexpected token"),
    ("syntax_error", r"expected ';'"),
    ("syntax_error", r"missing token"),
    ("syntax_error", r"Expected an identifier"),
]

LOGIC_PATTERNS = [
    ("test_logic_fail", r"AssertionError"),
    ("test_logic_fail", r"FAIL t_\w+"),
    ("test_logic_fail", r"Some tests failed"),
]


def load_summary(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_aggregate(d: dict) -> bool:
    return isinstance(d, dict) and isinstance(d.get("results"), list)


def get_phase(name: str) -> str:
    if name.startswith("phA_"): return "A"
    if name.startswith("phB_"): return "B"
    if name.startswith("phC_python_inv"): return "C/python-inv"
    if name.startswith("phC_dart_inv"): return "C/dart-inv"
    if name.startswith("phC_cpp_inv"): return "C/cpp-inv"
    if name.startswith("phC_dart_run"): return "C/dart-orders"
    if name.startswith("phC_cpp_run"): return "C/cpp-orders"
    if name.startswith("phC_flutter"): return "C/flutter"
    if name.startswith("phD_"): return "D"
    if name.startswith("phE_"): return "E"
    if name.startswith("phF_"): return "F"
    if name.startswith("phG_"): return "G"
    return "other"


def get_failure_text(d: dict) -> str:
    """Pull all the diagnostic text out of a trial summary."""
    parts = []
    for key in ("exec_stdout_tail", "grade_stdout_tail", "stdout_tail",
                "tail", "result_preview"):
        v = d.get(key)
        if isinstance(v, str): parts.append(v)
    # file_outcomes might have static_check_tail
    for fo in d.get("file_outcomes", {}).values():
        if isinstance(fo, dict):
            t = fo.get("static_check_tail")
            if t: parts.append(t)
    return "\n".join(parts)


def categorize(text: str) -> str:
    """Return a category label for a failure tail."""
    if not text:
        return "no_diagnostic"
    # Check infra first — it's noise that masks real failures
    for label, pat in INFRA_PATTERNS:
        if re.search(pat, text):
            # If we ALSO see a typelink pattern, prefer it (the
            # underlying failure is typelink, infra was just transient)
            for tlabel, tpat in TYPELINK_PATTERNS:
                if re.search(tpat, text):
                    return tlabel
            return label
    # TypeLink patterns
    for label, pat in TYPELINK_PATTERNS:
        if re.search(pat, text):
            return label
    # Syntax / logic
    for label, pat in SYNTAX_PATTERNS:
        if re.search(pat, text):
            return label
    for label, pat in LOGIC_PATTERNS:
        if re.search(pat, text):
            return label
    return "other"


def is_failed_trial(d: dict) -> bool:
    """A trial counts as failed if pass < total, or compile_failed."""
    if d.get("compile_failed"):
        return True
    p = d.get("passed", d.get("final_passed", 0))
    t = d.get("total", d.get("final_total", 0))
    if t == 0:
        return False  # no test ran; not a "failure" we can categorize
    return p < t


def is_multi_file(name: str, phase: str) -> bool:
    """Is this trial a multi-file benchmark?"""
    return phase in {
        "C/dart-inv", "C/cpp-inv", "C/python-inv",
        "C/dart-orders", "C/flutter",
    }


def collect_failures():
    failures = []  # list of (phase, trial_id, multi_file, category, text_snippet)
    for entry in sorted(RUNS.iterdir()):
        if entry.is_file() and entry.suffix == ".json":
            d = load_summary(entry)
            name = entry.name.replace(".json", "")
        elif entry.is_dir():
            sj = entry / "summary.json"
            if not sj.exists(): continue
            d = load_summary(sj)
            name = entry.name
        else:
            continue
        if not d: continue
        phase = get_phase(name)
        mf = is_multi_file(name, phase)
        if is_aggregate(d):
            # Phase E/G aggregate — has many sub-results
            for i, r in enumerate(d.get("results", [])):
                if r.get("pass"):
                    continue
                # Use verifier_reason as the diagnostic text
                tail = r.get("verifier_reason", "") + "\n" + r.get("error", "") if r.get("error") else r.get("verifier_reason", "")
                cat = categorize(tail or "")
                failures.append({
                    "phase": phase,
                    "trial": f"{name}#{i}",
                    "multi_file": False,  # aggregate trials are single-file
                    "category": cat,
                    "snippet": (tail or "")[:200],
                })
            continue
        if not is_failed_trial(d):
            continue
        text = get_failure_text(d)
        cat = categorize(text)
        snippet = ""
        # Find the first error-looking line for the snippet
        for line in text.split("\n"):
            if "error:" in line.lower() or "undefined reference" in line:
                snippet = line.strip()[:200]
                break
        if not snippet:
            snippet = text[:200].replace("\n", " ")
        failures.append({
            "phase": phase,
            "trial": name,
            "multi_file": mf,
            "category": cat,
            "snippet": snippet,
        })
    return failures


def report(failures: list) -> str:
    lines = []
    lines.append("# Failure-Mode Audit\n")
    lines.append(f"Total failed trials: **{len(failures)}**\n")

    multi = [f for f in failures if f["multi_file"]]
    single = [f for f in failures if not f["multi_file"]]
    lines.append(f"- Multi-file benchmark failures: {len(multi)}")
    lines.append(f"- Single-file benchmark failures: {len(single)}\n")

    # Typelink-shaped: missing_definition_link, signature_mismatch,
    # missing_symbol, type_shape are all typelink-shaped.
    TYPELINK_CATEGORIES = {
        "missing_definition_link", "signature_mismatch",
        "missing_symbol", "type_shape",
    }

    multi_typelink = [f for f in multi if f["category"] in TYPELINK_CATEGORIES]
    single_typelink = [f for f in single if f["category"] in TYPELINK_CATEGORIES]

    lines.append("## Typelink-shaped fraction\n")
    if multi:
        pct = 100 * len(multi_typelink) / len(multi)
        lines.append(
            f"- Multi-file failures classified as typelink-shaped: "
            f"**{len(multi_typelink)} / {len(multi)} ({pct:.1f}%)**"
        )
    if single:
        pct = 100 * len(single_typelink) / len(single)
        lines.append(
            f"- Single-file failures classified as typelink-shaped: "
            f"{len(single_typelink)} / {len(single)} ({pct:.1f}%)"
        )
    lines.append("")

    # Per-category breakdown
    lines.append("## Categories — multi-file failures\n")
    cats = Counter(f["category"] for f in multi)
    for c, n in cats.most_common():
        marker = " ←typelink" if c in TYPELINK_CATEGORIES else ""
        pct = 100 * n / len(multi) if multi else 0
        lines.append(f"- `{c}`: {n} ({pct:.1f}%){marker}")
    lines.append("")

    lines.append("## Categories — single-file failures\n")
    cats = Counter(f["category"] for f in single)
    for c, n in cats.most_common():
        marker = " ←typelink" if c in TYPELINK_CATEGORIES else ""
        pct = 100 * n / len(single) if single else 0
        lines.append(f"- `{c}`: {n} ({pct:.1f}%){marker}")
    lines.append("")

    # Per-phase breakdown (multi-file only)
    lines.append("## Per-phase breakdown — multi-file failures\n")
    phases = sorted(set(f["phase"] for f in multi))
    lines.append("| phase | total fail | typelink | typelink % |")
    lines.append("|---|---:|---:|---:|")
    for p in phases:
        ps = [f for f in multi if f["phase"] == p]
        tl = [f for f in ps if f["category"] in TYPELINK_CATEGORIES]
        pct = 100 * len(tl) / len(ps) if ps else 0
        lines.append(f"| {p} | {len(ps)} | {len(tl)} | {pct:.1f}% |")
    lines.append("")

    # Sample snippets per category
    lines.append("## Sample failure snippets\n")
    by_cat: dict[str, list] = {}
    for f in failures:
        by_cat.setdefault(f["category"], []).append(f)
    for c in sorted(by_cat.keys()):
        lines.append(f"### `{c}` ({len(by_cat[c])} failures)")
        for f in by_cat[c][:3]:
            mf = "multi" if f["multi_file"] else "single"
            lines.append(f"- **{f['trial']}** ({mf}): `{f['snippet'][:160]}`")
        lines.append("")

    return "\n".join(lines)


def main():
    failures = collect_failures()
    text = report(failures)
    out = REPO / "experiments" / "bakeoff" / "FAILURE_AUDIT.md"
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {len(failures)} failures categorized")


if __name__ == "__main__":
    main()
