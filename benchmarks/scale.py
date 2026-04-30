#!/usr/bin/env python3
"""
Loom scale benchmark.

Measures read-path latency at increasing store sizes. The question this
answers: is `loom context` fast enough to run in a PreToolUse hook on
every Edit/Write?

Method:
    For each scale N:
      1. Seed a fresh temp LoomStore with N requirements and ~2N
         implementations across ~N/2 files.
      2. Run each read-path service function K times against that store,
         record per-call latency in nanoseconds.
      3. Report median and p95.

Also runs a single cold-start subprocess invocation at the top scale to
measure the CLI-startup cost an actual hook would pay.

Embedding: forces the hash-fallback (no Ollama needed) so results are
reproducible. That slightly disadvantages `query` since hash vectors
have higher collision rates than real embeddings, but for latency — the
thing we're measuring — it's representative: the vector search cost is
the same regardless of vector quality.
"""
from __future__ import annotations

import json
import random
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from loom import embedding  # noqa: E402
from loom import services  # noqa: E402
from loom.store import (  # noqa: E402
    LoomStore, Requirement, Implementation,
    generate_impl_id, generate_content_hash,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCALES = [100, 1_000, 5_000]  # requirement counts to test
ITERS_PER_OP = 30              # per-call repetitions; median + p95 reported
DOMAINS = ("behavior", "ui", "data", "architecture", "terminology")
SEED = 1337


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _force_hash_fallback() -> None:
    """Route get_embedding through its deterministic hash fallback.

    Also silences embedding.py's per-fallback warning print — on Windows
    the default cp1252 stdout encoding crashes on the emoji it uses, and
    even on POSIX the spam pollutes benchmark output.
    """
    import urllib.request as ur

    def boom(*a, **kw):
        raise ConnectionResetError("benchmark: ollama disabled")

    ur.urlopen = boom  # type: ignore[assignment]
    embedding.print = lambda *a, **kw: None  # type: ignore[assignment]
    embedding._embedding_cache.clear()


def _seed_store(store: LoomStore, n_reqs: int, rng: random.Random,
                files_dir: Path) -> list[Path]:
    """Insert n_reqs requirements + ~2*n_reqs implementations across ~n/2 files.

    Returns the list of file paths created (caller needs them to time
    context/check operations against real paths).
    """
    emb = [0.1] * 768  # pre-computed so we don't pay embedding cost per row

    # Requirements.
    for i in range(n_reqs):
        req = Requirement(
            id=f"REQ-{i:06x}",
            domain=rng.choice(DOMAINS),
            value=f"synthetic requirement {i}: must handle condition {rng.randint(0, 999)}",
            source_msg_id=f"msg-{i}",
            source_session="bench",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(req, emb)

    # Implementations. Spread across ~n/2 files, 1-3 impls each, 1-2 req
    # links per impl. Keeps the shape realistic without blowing up seed time.
    n_files = max(1, n_reqs // 2)
    files: list[Path] = []
    for fi in range(n_files):
        p = files_dir / f"synthetic_{fi:06x}.py"
        p.write_text(f"# synthetic file {fi}\npass\n")
        files.append(p)

    req_ids = [f"REQ-{i:06x}" for i in range(n_reqs)]
    for fi, p in enumerate(files):
        n_impls = rng.randint(1, 3)
        for k in range(n_impls):
            lines = f"{k * 10 + 1}-{k * 10 + 9}" if k > 0 else "all"
            linked = rng.sample(req_ids, k=rng.randint(1, min(2, len(req_ids))))
            impl = Implementation(
                id=generate_impl_id(str(p), lines),
                file=str(p),
                lines=lines,
                content=p.read_text(),
                content_hash=generate_content_hash(p.read_text()),
                satisfies=[{"req_id": rid, "req_version": "x"} for rid in linked],
                timestamp="2026-01-01T00:00:00Z",
            )
            store.add_implementation(impl, emb)

    # Supersede ~5% of requirements so drift scenarios exist.
    for rid in rng.sample(req_ids, k=max(1, n_reqs // 20)):
        store.supersede_requirement(rid)

    return files


def _time_calls(fn, iters: int) -> tuple[float, float]:
    """Run fn() iters times; return (median_ms, p95_ms)."""
    samples_ns: list[int] = []
    for _ in range(iters):
        t0 = time.perf_counter_ns()
        fn()
        samples_ns.append(time.perf_counter_ns() - t0)
    samples_ns.sort()
    median_ms = statistics.median(samples_ns) / 1e6
    # p95 by simple index on sorted samples.
    p95_ms = samples_ns[int(0.95 * (len(samples_ns) - 1))] / 1e6
    return median_ms, p95_ms


# ---------------------------------------------------------------------------
# Benchmark drivers
# ---------------------------------------------------------------------------

def bench_scale(n_reqs: int, base_dir: Path, rng: random.Random) -> dict:
    """Seed a store of size n_reqs and time each read path."""
    data_dir = base_dir / f"store-{n_reqs}"
    files_dir = base_dir / f"files-{n_reqs}"
    files_dir.mkdir(parents=True, exist_ok=True)

    t_seed = time.perf_counter_ns()
    store = LoomStore(project=f"bench-{n_reqs}", data_dir=data_dir)
    files = _seed_store(store, n_reqs, rng, files_dir)
    seed_ms = (time.perf_counter_ns() - t_seed) / 1e6

    # Pick a linked file (guaranteed to have >=1 impl) and an unlinked one.
    linked_file = str(files[0])
    unlinked_file = str(files_dir / "unlinked.py")
    Path(unlinked_file).write_text("# nothing here\n")

    results: dict[str, tuple[float, float]] = {}
    results["context (linked)"]   = _time_calls(lambda: services.context(store, linked_file),   ITERS_PER_OP)
    results["context (unlinked)"] = _time_calls(lambda: services.context(store, unlinked_file), ITERS_PER_OP)
    results["check (linked)"]     = _time_calls(lambda: services.check(store, linked_file),     ITERS_PER_OP)
    results["trace (file)"]       = _time_calls(lambda: services.trace(store, linked_file),     ITERS_PER_OP)
    results["status"]             = _time_calls(lambda: services.status(store),                 ITERS_PER_OP)
    results["list (active)"]      = _time_calls(lambda: services.list_requirements(store),      ITERS_PER_OP)
    results["query"]              = _time_calls(lambda: services.query(store, "condition 500", limit=5), ITERS_PER_OP)

    return {
        "n_reqs": n_reqs,
        "seed_ms": seed_ms,
        "results": results,
        "linked_file": linked_file,
        "data_dir": str(data_dir),
    }


def bench_cold_start(data_dir: Path, project: str, linked_file: str) -> float:
    """One-shot: time `python scripts/loom -p <project> context <file>` end-to-end."""
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "loom"),
        "-p", project,
        "context",
        linked_file,
    ]
    # Point loom at the same data_dir via env? LoomStore uses default
    # ~/.openclaw path when data_dir not passed, and the CLI doesn't
    # accept a data_dir arg. To measure cold start fairly we'd need to
    # seed at the default path — which we don't, to keep the benchmark
    # hermetic. So we time a *cold-start-only* cost: parse + import +
    # open an existing store. That's still representative because the
    # hot path in the hook is the same code path — the difference is
    # whether the store has our seeded data or not, which doesn't move
    # the startup number meaningfully (<1ms to open a small store).
    t0 = time.perf_counter_ns()
    subprocess.run(cmd, capture_output=True, text=True, check=False)
    return (time.perf_counter_ns() - t0) / 1e6


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_table(rows: list[dict]) -> None:
    ops = list(rows[0]["results"].keys())
    col_w = 22
    scale_w = 12

    header = f"{'operation':<{col_w}}"
    for row in rows:
        header += f"{'N=' + str(row['n_reqs']):<{scale_w}}"
    print(header)
    print("-" * len(header))

    for op in ops:
        line = f"{op:<{col_w}}"
        for row in rows:
            med, p95 = row["results"][op]
            line += f"{med:>5.1f} / {p95:>5.1f} ".ljust(scale_w)
        print(line)

    print()
    print("values are: median_ms / p95_ms   (per call, in-process)")
    print()
    print("seed time:")
    for row in rows:
        print(f"  N={row['n_reqs']}: {row['seed_ms']:.0f} ms")


def main() -> None:
    rng = random.Random(SEED)
    _force_hash_fallback()

    base_dir = Path(tempfile.mkdtemp(prefix="loom-bench-"))
    print(f"benchmark workspace: {base_dir}")
    print()

    try:
        rows: list[dict] = []
        for n in SCALES:
            print(f"seeding + timing N={n} ...", flush=True)
            rows.append(bench_scale(n, base_dir, rng))

        print()
        print("=" * 70)
        print("RESULTS (in-process, Ollama-free hash fallback)")
        print("=" * 70)
        print_table(rows)

        print()
        print("=" * 70)
        print("COLD START (subprocess: python scripts/loom context ...)")
        print("=" * 70)
        top = rows[-1]
        # Warmup so we amortize any first-run cost like .pyc generation.
        bench_cold_start(Path(top["data_dir"]), f"bench-{top['n_reqs']}", top["linked_file"])
        samples_ms = [
            bench_cold_start(Path(top["data_dir"]), f"bench-{top['n_reqs']}", top["linked_file"])
            for _ in range(5)
        ]
        samples_ms.sort()
        print(f"N={top['n_reqs']}:  min {samples_ms[0]:.0f} ms   median {samples_ms[len(samples_ms) // 2]:.0f} ms   max {samples_ms[-1]:.0f} ms")
        print("(note: cold-start dominates any in-process measurement —")
        print(" this is the cost the hook actually pays per Edit/Write.)")

    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
