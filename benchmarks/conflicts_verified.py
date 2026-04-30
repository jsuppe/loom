#!/usr/bin/env python3
"""
Loom conflict detection with an LLM verification layer.

Pipeline per candidate requirement:
  1. Build a CANDIDATE POOL of possibly-conflicting existing reqs by:
     - top-N semantic neighbors from the ChromaDB vector search (no threshold)
     - any req flagged by the keyword-overlap heuristic in docs.check_conflicts
  2. For each pool member, ask a small LLM "does this conflict?"
  3. Emit the ones the LLM confirms.

This benchmark runs three strategies on the same dataset, over the
same pool per candidate, so the only variable is the verifier:

  - similarity-only     — the existing services.conflicts behavior (baseline)
  - llama3.2:3b         — small fast verifier
  - llama3.1:8b         — bigger stronger verifier

Reports precision, recall (overall and excluding logic-only cases),
false-positive rate on clean candidates, and per-call latency for each
strategy. Latency is measured warm (second pass), not including model
load time.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "benchmarks"))

from loom import services  # noqa: E402
from loom.store import LoomStore, Requirement  # noqa: E402

from retrieval_dataset import REQUIREMENTS  # noqa: E402
from conflict_dataset import CANDIDATES  # noqa: E402
from conflict_verifier import verify  # noqa: E402

POOL_TOP_N = 7   # top-N semantic neighbors to consider for verification
MODELS = [
    "llama3.2:latest",  # ~3B class baseline (already shown to fail this task)
    "gemma4:e2b",       # ~2B effective
    "gemma4:e4b",       # ~4B effective
    "phi4-mini",        # ~3.8B — Microsoft
    "llama3.1:8b",      # ~8B class
    "granite3.2:8b",    # IBM, compliance/review-tuned
    "qwen3.5:latest",   # ~9.7B
    "qwen2.5-coder:32b",  # 32B — ceiling measurement; not a shipping candidate
]


def require_ollama() -> None:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            body = r.read().decode()
    except Exception as e:
        print(f"ERROR: Ollama not reachable ({e}).", file=sys.stderr)
        sys.exit(1)
    if "nomic-embed-text" not in body:
        print("ERROR: nomic-embed-text not installed.", file=sys.stderr)
        sys.exit(1)
    for m in MODELS:
        if m.split(":")[0] not in body:
            print(f"ERROR: model {m} not installed in Ollama.", file=sys.stderr)
            sys.exit(1)


def seed(store: LoomStore) -> dict[str, str]:
    """Seed corpus and return {req_id: value} for quick lookup during verification."""
    from loom.embedding import get_embedding
    text_by_id: dict[str, str] = {}
    for (rid, domain, value) in REQUIREMENTS:
        req = Requirement(
            id=rid, domain=domain, value=value,
            source_msg_id="bench", source_session="bench",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(req, get_embedding(value))
        text_by_id[rid] = value
    return text_by_id


def build_pool(store: LoomStore, candidate_text: str, candidate_domain: str,
               top_n: int) -> set[str]:
    """Candidate pool = top-N semantic neighbors union keyword-overlap hits.

    This is the set of existing reqs we ASK the LLM about. The baseline
    similarity-only run also sees this pool, so all three strategies
    start from the same candidates.
    """
    # Semantic neighbors (unfiltered — we want recall here, precision
    # comes from the verifier).
    neighbors = services.query(store, candidate_text, limit=top_n)
    pool = {r["id"] for r in neighbors}

    # Keyword-overlap hits from the existing algorithm. We reconstruct
    # the condition rather than calling services.conflicts so we can
    # isolate the pool construction from the baseline's filtering.
    stopwords = {"the", "a", "an", "is", "are", "should", "be", "to",
                 "for", "with", "and", "or"}
    cand_words = set(candidate_text.lower().split()) - stopwords
    for req in store.list_requirements(include_superseded=False):
        if req.domain != candidate_domain:
            continue
        overlap = cand_words & (set(req.value.lower().split()) - stopwords)
        if len(overlap) >= 3:
            pool.add(req.id)
    return pool


def baseline_flags(store: LoomStore, candidate_text: str, candidate_domain: str) -> set[str]:
    """What services.conflicts flags today — our similarity-only baseline."""
    found = services.conflicts(store, f"{candidate_domain} | {candidate_text}")
    return {c["existing_id"] for c in found}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def summarize(candidates, flagged_by_candidate) -> dict:
    """Return overall precision / recall / FP-rate metrics."""
    all_flags = 0
    all_correct = 0
    all_truth = 0
    all_caught = 0
    fair_truth = 0
    fair_caught = 0
    clean_with_flag = 0
    clean_total = 0

    for (cand_text, cand_domain, truth, cat, note), flags in zip(candidates,
                                                                  flagged_by_candidate):
        all_flags += len(flags)
        all_correct += len(flags & truth)
        if truth:
            all_truth += len(truth)
            all_caught += len(flags & truth)
            if cat in ("contradiction", "overlap"):
                fair_truth += len(truth)
                fair_caught += len(flags & truth)
        else:
            clean_total += 1
            if flags:
                clean_with_flag += 1

    precision = (all_correct / all_flags) if all_flags else 0.0
    recall = (all_caught / all_truth) if all_truth else 0.0
    fair_recall = (fair_caught / fair_truth) if fair_truth else 0.0
    fp_rate = (clean_with_flag / clean_total) if clean_total else 0.0

    return {
        "flags": all_flags,
        "correct_flags": all_correct,
        "precision": precision,
        "recall": recall,
        "fair_recall": fair_recall,
        "clean_with_flag": clean_with_flag,
        "clean_total": clean_total,
        "fp_rate": fp_rate,
    }


# ---------------------------------------------------------------------------

def warmup(model: str) -> None:
    """Issue a throwaway verify() so cold-start isn't charged to the first candidate."""
    try:
        verify("dummy", "dummy", model)
    except Exception:
        pass


def main() -> None:
    require_ollama()

    workdir = Path(tempfile.mkdtemp(prefix="loom-conflict-verified-"))
    print(f"workspace: {workdir}")
    print(f"corpus:    {len(REQUIREMENTS)} requirements")
    print(f"candidates: {len(CANDIDATES)}")
    print(f"pool size: top-{POOL_TOP_N} semantic + keyword-overlap hits")
    print()

    try:
        store = LoomStore(project="bench-conflict-v", data_dir=workdir)
        print("seeding ...", flush=True)
        t0 = time.perf_counter()
        seed(store)
        print(f"  done in {time.perf_counter() - t0:.1f}s")
        print()

        # Precompute pool + baseline flags once (shared across strategies).
        print("building per-candidate pool + baseline flags ...", flush=True)
        pools: list[set[str]] = []
        baseline_per_cand: list[set[str]] = []
        pool_coverage_total = 0
        pool_coverage_hits = 0
        for (cand_text, cand_domain, truth, cat, note) in CANDIDATES:
            pool = build_pool(store, cand_text, cand_domain, POOL_TOP_N)
            pools.append(pool)
            baseline_per_cand.append(baseline_flags(store, cand_text, cand_domain))
            if truth:
                pool_coverage_total += len(truth)
                pool_coverage_hits += len(pool & truth)

        # Pool-coverage ceiling: the verifier can't flag what's not in the pool.
        pool_recall_ceiling = (
            pool_coverage_hits / pool_coverage_total if pool_coverage_total else 0
        )
        print(f"  pool-recall ceiling: {pool_recall_ceiling:.1%}  "
              f"({pool_coverage_hits}/{pool_coverage_total} truth items in pool)")
        print()

        # Build per-candidate text lookup for the verifier's 'existing' input.
        req_text: dict[str, str] = {rid: value for (rid, _, value) in REQUIREMENTS}

        # Run LLM verifiers.
        verified_per_model: dict[str, list[set[str]]] = {}
        latency_per_model: dict[str, list[float]] = {}
        for model in MODELS:
            print(f"warming up {model} ...", flush=True)
            warmup(model)
            print(f"running verifier: {model}", flush=True)
            flags_per_cand: list[set[str]] = []
            call_latencies: list[float] = []
            for i, (pool, (cand_text, cand_domain, truth, cat, note)) in enumerate(
                zip(pools, CANDIDATES), start=1
            ):
                confirmed: set[str] = set()
                for rid in sorted(pool):  # sort for determinism
                    existing = req_text.get(rid, "")
                    t0 = time.perf_counter()
                    is_conflict, _raw = verify(cand_text, existing, model)
                    call_latencies.append((time.perf_counter() - t0) * 1000)
                    if is_conflict:
                        confirmed.add(rid)
                flags_per_cand.append(confirmed)
                if i % 5 == 0:
                    print(f"  ... {i}/{len(CANDIDATES)}", flush=True)
            verified_per_model[model] = flags_per_cand
            latency_per_model[model] = call_latencies
            print()

        # ---- Report ----
        print("=" * 110)
        print("OVERALL  --  baseline + per-model verifier")
        print("=" * 110)
        summaries = {"baseline": summarize(CANDIDATES, baseline_per_cand)}
        for m in MODELS:
            summaries[m] = summarize(CANDIDATES, verified_per_model[m])

        col_names = ["baseline"] + MODELS
        header = f"  {'metric':<30}" + "".join(f"{name[:16]:>18}" for name in col_names)
        print(header)

        def row(label, key, fmt):
            cells = "".join(f"{fmt.format(summaries[n][key]):>18}" for n in col_names)
            print(f"  {label:<30}{cells}")

        row("precision", "precision", "{:.1%}")
        row("recall (all truth)", "recall", "{:.1%}")
        row("recall (excl logic-only)", "fair_recall", "{:.1%}")
        row("FP rate on clean candidates", "fp_rate", "{:.1%}")
        row("total flags emitted", "flags", "{}")
        row("correct flags", "correct_flags", "{}")
        print()

        # ---- Latency ----
        print("=" * 82)
        print("LATENCY  (LLM verify calls, warm model)")
        print("=" * 82)
        print(f"  {'model':<22}{'n_calls':>10}{'median':>12}{'p95':>12}{'max':>12}")
        import statistics
        for model in MODELS:
            lat = sorted(latency_per_model[model])
            if not lat:
                continue
            med = statistics.median(lat)
            p95 = lat[int(0.95 * (len(lat) - 1))]
            mx = lat[-1]
            print(f"  {model:<22}{len(lat):>10}{med:>11.0f}ms{p95:>11.0f}ms{mx:>11.0f}ms")
        print()

        # ---- Qualitative diffs: only show RECOVERED / LOST / NEW FP cases,
        # otherwise the output drowns in routine agreement. ----
        print("=" * 110)
        print("NOTABLE CHANGES vs BASELINE (RECOVERED / LOST / NEW FP only)")
        print("=" * 110)
        for model_name in MODELS:
            model_flags = verified_per_model[model_name]
            lines: list[str] = []
            for (cand, flags_base), (_, flags_v), c in zip(
                zip(CANDIDATES, baseline_per_cand),
                zip(CANDIDATES, model_flags),
                CANDIDATES,
            ):
                cand_text, cand_domain, truth, cat, note = c
                if flags_base == flags_v:
                    continue
                truth_hit_before = bool(flags_base & truth)
                truth_hit_after = bool(flags_v & truth)
                verdict = None
                if truth and not truth_hit_before and truth_hit_after:
                    verdict = "RECOVERED"
                elif truth and truth_hit_before and not truth_hit_after:
                    verdict = "LOST"
                elif not truth and not flags_base and flags_v:
                    verdict = "NEW FP"
                if verdict is None:
                    continue
                lines.append(f"    [{verdict:<10}] [{cat}] {cand_text[:70]}")
            print(f"\n  [{model_name}]  ({len(lines)} notable)")
            for line in lines[:15]:
                print(line)
            if len(lines) > 15:
                print(f"    ... and {len(lines) - 15} more")

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
