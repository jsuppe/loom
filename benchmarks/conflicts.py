#!/usr/bin/env python3
"""
Loom conflict-detection benchmark.

Answers: when someone adds a new requirement, does Loom correctly flag
existing requirements that should be reviewed -- without drowning the
user in false positives on unrelated changes?

Method:
  1. Seed the 50-req e-commerce corpus (shared with retrieval.py).
  2. For each candidate in conflict_dataset.CANDIDATES, call
     services.conflicts() and collect the set of flagged REQ-ids.
  3. Compare that set to the ground-truth `conflicts_with` label.
  4. Report precision, recall, per-category breakdown, and the full
     set of misses & false-positives for qualitative review.

Note on labels:
  `contradiction` and `overlap` cases expect Loom to flag at least the
  labeled REQ-ids. `related-ok` and `unrelated` cases expect ZERO
  flags -- any flag is a false positive.

  `contradiction-logic` cases are contradictions the algorithm cannot
  reasonably catch (they need understanding of negation / specific
  numbers). They're labeled separately so we can report the honest
  ceiling on recall without them, then show the adversarial floor
  with them included.

Requires Ollama running with nomic-embed-text.
"""
from __future__ import annotations

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


def seed(store: LoomStore) -> None:
    from loom.embedding import get_embedding
    for (rid, domain, value) in REQUIREMENTS:
        req = Requirement(
            id=rid, domain=domain, value=value,
            source_msg_id="bench", source_session="bench",
            timestamp="2026-01-01T00:00:00Z",
        )
        store.add_requirement(req, get_embedding(value))


def main() -> None:
    require_ollama()

    workdir = Path(tempfile.mkdtemp(prefix="loom-conflict-"))
    print(f"workspace: {workdir}")
    print(f"corpus:    {len(REQUIREMENTS)} requirements")
    print(f"candidates: {len(CANDIDATES)}")
    print()

    try:
        store = LoomStore(project="bench-conflict", data_dir=workdir)
        print("seeding ...", flush=True)
        t0 = time.perf_counter()
        seed(store)
        print(f"  done in {time.perf_counter() - t0:.1f}s")
        print()

        results_by_cat: dict[str, list] = defaultdict(list)
        all_flags_correct = 0
        all_flags_total = 0
        all_conflicts_caught = 0
        all_conflicts_total = 0
        false_positive_count = 0
        false_positive_candidates = 0
        per_candidate_detail: list[dict] = []

        print("running conflict checks ...", flush=True)
        t0 = time.perf_counter()
        for cand_text, cand_domain, truth_set, category, note in CANDIDATES:
            # services.conflicts takes "domain | text" or just text.
            flagged_result = services.conflicts(store, f"{cand_domain} | {cand_text}")
            flagged_ids: set[str] = {c["existing_id"] for c in flagged_result}

            # Compute per-candidate metrics.
            tp = flagged_ids & truth_set
            fp = flagged_ids - truth_set
            fn = truth_set - flagged_ids

            # Precision undefined when no flags; track "flag events" aggregate.
            per_cand_precision = (len(tp) / len(flagged_ids)) if flagged_ids else None
            per_cand_recall = (len(tp) / len(truth_set)) if truth_set else None

            all_flags_total += len(flagged_ids)
            all_flags_correct += len(tp)
            if truth_set:
                all_conflicts_total += len(truth_set)
                all_conflicts_caught += len(tp)
            if not truth_set and flagged_ids:
                false_positive_candidates += 1
                false_positive_count += len(flagged_ids)

            results_by_cat[category].append({
                "candidate": cand_text,
                "truth": truth_set,
                "flagged": flagged_ids,
                "tp": tp, "fp": fp, "fn": fn,
                "note": note,
            })
            per_candidate_detail.append({
                "candidate": cand_text,
                "category": category,
                "truth": truth_set,
                "flagged": flagged_ids,
                "tp": tp, "fp": fp, "fn": fn,
                "note": note,
            })
        total_time = time.perf_counter() - t0
        print(f"  {len(CANDIDATES)} candidates in {total_time:.1f}s")
        print()

        # ---- Aggregate metrics ----
        print("=" * 78)
        print("OVERALL")
        print("=" * 78)
        # Micro precision = correct flags / total flags (across all candidates).
        micro_precision = (all_flags_correct / all_flags_total) if all_flags_total else 0
        # Micro recall: fraction of true-conflict relationships caught.
        micro_recall = (all_conflicts_caught / all_conflicts_total) if all_conflicts_total else 0
        # Recall excluding the logic-only contradictions we know are unfair.
        fair_catches = 0
        fair_total = 0
        for cat in ("contradiction", "overlap"):
            for r in results_by_cat[cat]:
                fair_total += len(r["truth"])
                fair_catches += len(r["tp"])
        fair_recall = (fair_catches / fair_total) if fair_total else 0

        print(f"  total flags emitted:            {all_flags_total}")
        print(f"  flags that hit true conflicts:  {all_flags_correct}")
        print(f"  micro precision:                {micro_precision:.1%}")
        print()
        print(f"  true conflicts in dataset:      {all_conflicts_total}")
        print(f"  caught by Loom:                 {all_conflicts_caught}")
        print(f"  micro recall (all categories):  {micro_recall:.1%}")
        print(f"  micro recall (excluding logic-only):  {fair_recall:.1%}")
        print()
        no_conflict_candidates = sum(1 for _, _, t, _, _ in CANDIDATES if not t)
        print(f"  'no conflict' candidates (related-ok + unrelated): {no_conflict_candidates}")
        print(f"  of those, triggered >=1 false flag:  {false_positive_candidates}")
        print(f"  false-positive rate on clean candidates:  "
              f"{false_positive_candidates / no_conflict_candidates:.1%}")
        print()

        # ---- Per-category breakdown ----
        print("=" * 78)
        print("BY CATEGORY")
        print("=" * 78)
        print(f"  {'category':<22}{'n':>4}{'recall':>12}{'FP rate':>14}")
        for cat in ("contradiction", "contradiction-logic", "overlap",
                    "related-ok", "unrelated"):
            rows = results_by_cat.get(cat, [])
            if not rows:
                continue
            n = len(rows)
            if cat in ("contradiction", "contradiction-logic", "overlap"):
                truth_total = sum(len(r["truth"]) for r in rows)
                caught = sum(len(r["tp"]) for r in rows)
                rec = (caught / truth_total) if truth_total else 0
                # "FP rate" here is flags NOT in truth, averaged per candidate.
                avg_fp = sum(len(r["fp"]) for r in rows) / n
                print(f"  {cat:<22}{n:>4}{rec:>12.1%}{avg_fp:>14.2f}  (avg FP/candidate)")
            else:
                # No true conflicts; all flags are false.
                flagged_cands = sum(1 for r in rows if r["flagged"])
                print(f"  {cat:<22}{n:>4}{'--':>12}{flagged_cands}/{n:<10}  (candidates w/ any flag)")
        print()

        # ---- Qualitative: misses ----
        print("=" * 78)
        print("MISSES  --  true conflicts Loom did not flag")
        print("=" * 78)
        for r in per_candidate_detail:
            if r["fn"]:
                missed = ", ".join(sorted(r["fn"]))
                print(f"  [{r['category']}] {r['candidate']}")
                print(f"     expected: {missed}    flagged: {sorted(r['flagged']) or 'none'}")
                print(f"     note:     {r['note']}")
                print()

        # ---- Qualitative: false positives ----
        print("=" * 78)
        print("FALSE POSITIVES  --  flags on related-ok / unrelated candidates")
        print("=" * 78)
        for r in per_candidate_detail:
            if r["category"] in ("related-ok", "unrelated") and r["flagged"]:
                flagged = ", ".join(sorted(r["flagged"]))
                print(f"  [{r['category']}] {r['candidate']}")
                print(f"     flagged:  {flagged}")
                print(f"     note:     {r['note']}")
                print()

    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
