#!/usr/bin/env python3
"""
Loom retrieval benchmark — baseline vs. LLM-expanded queries.

Same corpus + labeled queries as benchmarks/retrieval.py, but runs each
query twice: once as-is, once after expanding it to 3 variants via an
LLM (see query_expansion.py). Variant results are merged with Reciprocal
Rank Fusion (RRF, k=60), a standard technique for combining ranked lists.

Prints a head-to-head comparison so the delta per metric and per query
style is obvious. The question we're answering: does query expansion
fix the jargon weakness the baseline benchmark revealed?

Cost caveat: expansion adds an LLM call per query (~1-2s with llama3.1:8b).
A real integration would cache or batch; this is the honest per-call cost.
"""
from __future__ import annotations

import shutil
import statistics
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

from retrieval_dataset import REQUIREMENTS, QUERIES  # noqa: E402
from query_expansion import expand  # noqa: E402


RRF_K = 60  # standard value; larger k damps the contribution of each rank


def require_ollama() -> None:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            body = r.read().decode()
    except Exception as e:
        print(f"ERROR: Ollama not reachable at localhost:11434 ({e}).", file=sys.stderr)
        sys.exit(1)
    if "nomic-embed-text" not in body:
        print("ERROR: nomic-embed-text not installed. Run: ollama pull nomic-embed-text", file=sys.stderr)
        sys.exit(1)


def seed(store: LoomStore) -> None:
    from loom.embedding import get_embedding
    for (rid, domain, value) in REQUIREMENTS:
        req = Requirement(
            id=rid, domain=domain, value=value,
            source_msg_id="bench", source_session="bench",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(req, get_embedding(value))


def rank_of(results: list[dict], target_id: str) -> int | None:
    for i, r in enumerate(results, start=1):
        if r["id"] == target_id:
            return i
    return None


def rrf_merge(
    result_lists: list[list[dict]],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[dict]:
    """Reciprocal Rank Fusion: combine multiple ranked lists into one.

    score(req) = sum_i weight_i / (k + rank_i(req))

    `weights` is parallel to `result_lists`; defaults to all 1.0. A
    higher weight on the original query protects answers that were
    already ranked #1 from being displaced by imperfect paraphrases.
    """
    if weights is None:
        weights = [1.0] * len(result_lists)
    assert len(weights) == len(result_lists)

    scored: dict[str, float] = defaultdict(float)
    by_id: dict[str, dict] = {}
    for results, w in zip(result_lists, weights):
        for rank, item in enumerate(results, start=1):
            scored[item["id"]] += w / (k + rank)
            by_id.setdefault(item["id"], item)
    return [by_id[rid] for rid, _ in sorted(scored.items(), key=lambda kv: -kv[1])]


def summarize(ranks: list[int | None]) -> dict:
    n = len(ranks)
    if n == 0:
        return {"n": 0, "r1": 0, "r5": 0, "r10": 0, "mrr": 0}
    r1 = sum(1 for r in ranks if r == 1) / n
    r5 = sum(1 for r in ranks if r is not None and r <= 5) / n
    r10 = sum(1 for r in ranks if r is not None and r <= 10) / n
    mrr = statistics.mean((1 / r) if r else 0 for r in ranks)
    return {"n": n, "r1": r1, "r5": r5, "r10": r10, "mrr": mrr}


def req_domain(req_id: str) -> str:
    return req_id.split("-")[1] if req_id.startswith("REQ-") else "?"


# ---------------------------------------------------------------------------

def main() -> None:
    require_ollama()

    workdir = Path(tempfile.mkdtemp(prefix="loom-retrieval-exp-"))
    print(f"workspace: {workdir}")
    print(f"corpus:    {len(REQUIREMENTS)} requirements")
    print(f"queries:   {len(QUERIES)}")
    print()

    try:
        store = LoomStore(project="bench-retrieval-exp", data_dir=workdir)

        print("seeding ...", flush=True)
        t0 = time.perf_counter()
        seed(store)
        print(f"  done in {time.perf_counter() - t0:.1f}s")
        print()

        # Three parallel rank streams over the SAME set of LLM paraphrases,
        # so the only variable between configs is the fusion strategy.
        ranks: dict[str, list[int | None]] = {
            "baseline": [], "uniform": [], "weighted": [],
        }
        per_style: dict[str, dict[str, list[int | None]]] = {
            s: defaultdict(list) for s in ranks
        }
        per_domain: dict[str, dict[str, list[int | None]]] = {
            s: defaultdict(list) for s in ranks
        }

        expand_time = 0.0
        search_time_baseline = 0.0
        search_time_expanded = 0.0

        print(f"running {len(QUERIES)} queries ...", flush=True)
        for i, (q, expected, difficulty) in enumerate(QUERIES, start=1):
            if i % 10 == 0:
                print(f"  ... {i}/{len(QUERIES)}", flush=True)

            # ---- Expand ONCE; use the same variants for both RRF configs ----
            t0 = time.perf_counter()
            variants = expand(q)  # variants[0] is the original query
            expand_time += time.perf_counter() - t0

            t0 = time.perf_counter()
            variant_results = [services.query(store, v, limit=10) for v in variants]
            search_time_expanded += time.perf_counter() - t0

            baseline_results = variant_results[0]  # same as a fresh baseline call
            search_time_baseline += 0  # rolled into expanded (no double-count)

            # Three ranks to compare.
            r_baseline = rank_of(baseline_results, expected)
            merged_uniform = rrf_merge(variant_results)
            r_uniform = rank_of(merged_uniform, expected)
            weights = [2.0] + [1.0] * (len(variant_results) - 1)
            merged_weighted = rrf_merge(variant_results, weights=weights)
            r_weighted = rank_of(merged_weighted, expected)

            for name, r in (("baseline", r_baseline), ("uniform", r_uniform),
                            ("weighted", r_weighted)):
                ranks[name].append(r)
                per_style[name][difficulty].append(r)
                per_domain[name][req_domain(expected)].append(r)

        print()

        # ---- Head-to-head overall ----
        print("=" * 78)
        print("OVERALL  —  three strategies over the SAME LLM expansions")
        print("=" * 78)
        print(f"  {'metric':<12}{'baseline':>12}{'uniform RRF':>15}{'weighted RRF':>16}")
        summaries = {name: summarize(rs) for name, rs in ranks.items()}
        for metric_key, metric_label, fmt in (
            ("r1",  "recall@1",  "{:.1%}"),
            ("r5",  "recall@5",  "{:.1%}"),
            ("r10", "recall@10", "{:.1%}"),
            ("mrr", "MRR",       "{:.3f}"),
        ):
            b = summaries["baseline"][metric_key]
            u = summaries["uniform"][metric_key]
            w = summaries["weighted"][metric_key]
            print(f"  {metric_label:<12}{fmt.format(b):>12}{fmt.format(u):>15}{fmt.format(w):>16}")
        print()

        # ---- Per query style ----
        print("=" * 78)
        print("BY QUERY STYLE  —  recall@1 per strategy")
        print("=" * 78)
        print(f"  {'style':<12}{'n':>4}{'baseline':>12}{'uniform':>12}{'weighted':>12}")
        for style in ("paraphrase", "goal", "jargon"):
            bs = summarize(per_style["baseline"][style])
            us = summarize(per_style["uniform"][style])
            ws = summarize(per_style["weighted"][style])
            if bs["n"] == 0:
                continue
            print(f"  {style:<12}{bs['n']:>4}{bs['r1']:>12.1%}{us['r1']:>12.1%}{ws['r1']:>12.1%}")
        print()
        print(f"  {'style':<12}{'n':>4}{'baseline@5':>12}{'uniform@5':>12}{'wgt@5':>12}")
        for style in ("paraphrase", "goal", "jargon"):
            bs = summarize(per_style["baseline"][style])
            us = summarize(per_style["uniform"][style])
            ws = summarize(per_style["weighted"][style])
            if bs["n"] == 0:
                continue
            print(f"  {style:<12}{bs['n']:>4}{bs['r5']:>12.1%}{us['r5']:>12.1%}{ws['r5']:>12.1%}")
        print()

        # ---- Per domain (recall@1 only — keep it compact) ----
        print("=" * 78)
        print("BY DOMAIN  —  recall@1 per strategy")
        print("=" * 78)
        print(f"  {'domain':<12}{'n':>4}{'baseline':>12}{'uniform':>12}{'weighted':>12}")
        for dom in sorted(per_domain["baseline"]):
            bs = summarize(per_domain["baseline"][dom])
            us = summarize(per_domain["uniform"][dom])
            ws = summarize(per_domain["weighted"][dom])
            print(f"  {dom:<12}{bs['n']:>4}{bs['r1']:>12.1%}{us['r1']:>12.1%}{ws['r1']:>12.1%}")
        print()

        # ---- Cost ----
        print("=" * 78)
        print("COST")
        print("=" * 78)
        print(f"  expansion (LLM):       {expand_time:.1f}s total, "
              f"{1000 * expand_time / len(QUERIES):.0f} ms/query")
        print(f"  search (3x variants):  {search_time_expanded:.1f}s total, "
              f"{1000 * search_time_expanded / len(QUERIES):.0f} ms/query")

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
