#!/usr/bin/env python3
"""
Loom retrieval quality benchmark.

Answers: given a natural-language query, does `loom query` return the
correct requirement in its top-k results?

Method:
    1. Seed a fresh temp store with the corpus from retrieval_dataset.py
       using real Ollama embeddings (nomic-embed-text).
    2. For each labeled query, run `services.query(..., limit=10)`.
    3. Record the rank of the ground-truth req in the returned list
       (or `None` if not present).
    4. Report recall@1/@5/@10, MRR, per-domain breakdown, and a list of
       queries where the correct answer was outside the top 10.

Requires Ollama running with `nomic-embed-text` pulled. Without that
this benchmark is measuring the hash-fallback, which is meaningless.
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

import services  # noqa: E402
from store import LoomStore, Requirement  # noqa: E402

from retrieval_dataset import REQUIREMENTS, QUERIES  # noqa: E402


# ---------------------------------------------------------------------------

def require_ollama() -> None:
    """Fail loudly if Ollama isn't available — hash fallback invalidates the test."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            body = r.read().decode()
    except Exception as e:
        print(f"ERROR: Ollama not reachable at localhost:11434 ({e}).", file=sys.stderr)
        print("This benchmark requires real embeddings. Start Ollama and retry.", file=sys.stderr)
        sys.exit(1)

    if "nomic-embed-text" not in body:
        print("ERROR: Ollama is reachable but `nomic-embed-text` is not installed.", file=sys.stderr)
        print("Run:  ollama pull nomic-embed-text", file=sys.stderr)
        sys.exit(1)


def seed(store: LoomStore) -> None:
    from embedding import get_embedding
    for (rid, domain, value) in REQUIREMENTS:
        req = Requirement(
            id=rid, domain=domain, value=value,
            source_msg_id="bench", source_session="bench",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(req, get_embedding(value))


def rank_of(results: list[dict], target_id: str) -> int | None:
    """1-indexed rank of target_id in results, or None if absent."""
    for i, r in enumerate(results, start=1):
        if r["id"] == target_id:
            return i
    return None


def main() -> None:
    require_ollama()

    workdir = Path(tempfile.mkdtemp(prefix="loom-retrieval-"))
    print(f"workspace: {workdir}")
    print(f"corpus:    {len(REQUIREMENTS)} requirements")
    print(f"queries:   {len(QUERIES)}")
    print()

    try:
        store = LoomStore(project="bench-retrieval", data_dir=workdir)

        print("seeding (embedding each requirement) ...", flush=True)
        t0 = time.perf_counter()
        seed(store)
        print(f"  done in {time.perf_counter() - t0:.1f}s")
        print()

        # Domain breakdown setup: prefix up to the first dash after "REQ-".
        def req_domain(req_id: str) -> str:
            # REQ-auth-01 → auth
            return req_id.split("-")[1] if req_id.startswith("REQ-") else "?"

        per_difficulty: dict[str, list[int | None]] = defaultdict(list)
        per_domain: dict[str, list[int | None]] = defaultdict(list)
        all_ranks: list[int | None] = []
        failures: list[tuple[str, str, list[dict]]] = []

        print("running queries ...", flush=True)
        t0 = time.perf_counter()
        for (q, expected, difficulty) in QUERIES:
            results = services.query(store, q, limit=10)
            rank = rank_of(results, expected)
            all_ranks.append(rank)
            per_difficulty[difficulty].append(rank)
            per_domain[req_domain(expected)].append(rank)
            if rank is None or rank > 5:
                failures.append((q, expected, results))
        qtime = time.perf_counter() - t0
        print(f"  {len(QUERIES)} queries in {qtime:.1f}s "
              f"({1000 * qtime / len(QUERIES):.0f} ms/query including embedding)")
        print()

        # ---- Aggregate metrics ----
        def summarize(ranks: list[int | None]) -> dict:
            n = len(ranks)
            if n == 0:
                return {"n": 0}
            r1 = sum(1 for r in ranks if r == 1) / n
            r5 = sum(1 for r in ranks if r is not None and r <= 5) / n
            r10 = sum(1 for r in ranks if r is not None and r <= 10) / n
            # MRR: if rank is None, reciprocal is 0.
            mrr = statistics.mean((1 / r) if r else 0 for r in ranks)
            return {"n": n, "r1": r1, "r5": r5, "r10": r10, "mrr": mrr}

        print("=" * 72)
        print("OVERALL")
        print("=" * 72)
        s = summarize(all_ranks)
        print(f"  queries:      {s['n']}")
        print(f"  recall@1:     {s['r1']:.1%}  ({int(s['r1'] * s['n'])}/{s['n']})")
        print(f"  recall@5:     {s['r5']:.1%}  ({int(s['r5'] * s['n'])}/{s['n']})")
        print(f"  recall@10:    {s['r10']:.1%}  ({int(s['r10'] * s['n'])}/{s['n']})")
        print(f"  MRR:          {s['mrr']:.3f}")
        print()

        print("=" * 72)
        print("BY QUERY STYLE")
        print("=" * 72)
        print(f"  {'style':<12}{'n':>4}{'@1':>10}{'@5':>10}{'@10':>10}{'MRR':>10}")
        for style in ("paraphrase", "goal", "jargon"):
            s = summarize(per_difficulty[style])
            if s["n"] == 0:
                continue
            print(f"  {style:<12}{s['n']:>4}{s['r1']:>10.1%}{s['r5']:>10.1%}{s['r10']:>10.1%}{s['mrr']:>10.3f}")
        print()

        print("=" * 72)
        print("BY DOMAIN")
        print("=" * 72)
        print(f"  {'domain':<12}{'n':>4}{'@1':>10}{'@5':>10}{'@10':>10}{'MRR':>10}")
        for dom in sorted(per_domain):
            s = summarize(per_domain[dom])
            print(f"  {dom:<12}{s['n']:>4}{s['r1']:>10.1%}{s['r5']:>10.1%}{s['r10']:>10.1%}{s['mrr']:>10.3f}")
        print()

        # ---- Failures: rank > 5 or missing. Useful for qualitative review. ----
        print("=" * 72)
        print(f"FAILURES (correct answer not in top 5)  —  {len(failures)} of {len(QUERIES)}")
        print("=" * 72)
        for q, expected, results in failures:
            top = results[0] if results else None
            top_str = f"{top['id']}: {top['value'][:60]}" if top else "<no results>"
            # Find actual rank or say 'missing'.
            r = rank_of(results, expected)
            rank_str = f"rank {r}" if r else "not in top 10"
            print(f"  Q: {q}")
            print(f"     expected: {expected}  ({rank_str})")
            print(f"     got top:  {top_str}")
            print()

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
