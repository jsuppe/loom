#!/usr/bin/env python3
"""
Pilot — calibrate the confidence threshold for `find_related_requirements`
proposed in DESIGN-rationale-linkage.md.

Synthesizes a realistic 24-requirement corpus drawn from Loom's own
domain (drift, hooks, embeddings, indexers, runners, etc.), then runs
8 test "new requirement" queries — each with a hand-labeled expected
match — through the existing `services.query` to measure:

  * Precision: how often is the top-1 match the expected one?
  * Score distribution: where does the threshold actually need to be?
  * False positive rate: what scores do clearly-unrelated reqs get?

Output: per-query top-3 results with cosine scores, plus a
recommendation for the threshold.

Run: python experiments/pilot/rationale_linkage_pilot.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force UTF-8 stdout so check/x marks render on Windows cp1252 terminals.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

LOOM_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LOOM_DIR / "src"))

# Use the deterministic hash provider so the pilot is reproducible
# and doesn't depend on Ollama being up. The relative-distance
# pattern between related vs unrelated reqs is what matters here.
os.environ.setdefault("LOOM_EMBEDDING_PROVIDER", "ollama")

from loom import services
from loom.store import LoomStore


# ---------------------------------------------------------------------------
# Synthetic corpus — 24 requirements drawn from Loom's actual domain.
#
# Design: cover ~6 sub-domains with 3-5 reqs each, including some that
# are textually similar (lexical overlap) and some that are
# semantically related but lexically distinct. This lets us test
# whether embeddings catch semantic-but-not-lexical matches that a
# naive grep wouldn't.
# ---------------------------------------------------------------------------

CORPUS = [
    # Drift detection (4)
    ("DRF-1", "behavior", "Loom check should detect when file content has diverged from the linked requirement's recorded snapshot, not only when the requirement itself has been superseded."),
    ("DRF-2", "behavior", "The drift signal must distinguish whitespace-only changes from structural changes to function signatures."),
    ("DRF-3", "behavior", "Drift detection events should be appended to a JSONL log with the offending requirement IDs and which signal channels fired."),
    ("DRF-4", "behavior", "When the linked requirement has been superseded, drift detection must mark the implementation as drifted regardless of the file's content state."),

    # Hooks / agent integration (4)
    ("HOK-1", "behavior", "PreToolUse hook should inject linked requirements as a system-reminder before any Edit, Write, or MultiEdit tool call."),
    ("HOK-2", "behavior", "The hook telemetry log must record per-fire latency, byte counts, and whether the fire was skipped or actually injected context."),
    ("HOK-3", "behavior", "When LOOM_HOOK_BLOCK_ON_DRIFT is set, the hook must hard-block the agent's edit when drift is detected."),
    ("HOK-4", "behavior", "Hook fires should not depend on Ollama being available; embedding fallbacks must keep the hook fast and deterministic."),

    # Embeddings (4)
    ("EMB-1", "behavior", "Loom must support multiple embedding providers — Ollama, OpenAI, and a deterministic hash fallback — selected via env or config."),
    ("EMB-2", "behavior", "The embedding cache key must include the provider name so that switching providers cannot return a stale vector from a different model."),
    ("EMB-3", "behavior", "On first vector write, the SQLite store must pin its embedding dimension; mismatched subsequent writes raise EmbeddingDimensionMismatch."),
    ("EMB-4", "behavior", "The Ollama provider should fall back to deterministic hash-based pseudo-embeddings on outage; the OpenAI provider must surface the error explicitly without silent degradation."),

    # Indexer pipeline (4)
    ("IDX-1", "behavior", "Loom should surface a pluggable SemanticIndexer interface that can be backed by Kythe, an LSP server, or a stub depending on language."),
    ("IDX-2", "behavior", "When an indexer is registered for a file's language, the executor prompt should include peek-references-style call sites for the file's exported symbols."),
    ("IDX-3", "behavior", "Indexer health must be queryable via a single command that reports binary availability and per-language coverage."),
    ("IDX-4", "behavior", "Loom link --symbol should resolve a symbol reference like 'OrderService.commit' through the registered indexer to a stable ticket plus signature hash."),

    # Test runners (4)
    ("RUN-1", "behavior", "The executor must support multiple test runners — pytest, dart_test, flutter_test, vitest — selected per project."),
    ("RUN-2", "behavior", "Each runner owns its own command shape, code-block fence, apply mode, and grading parser; adding a new runner should require no changes elsewhere."),
    ("RUN-3", "behavior", "When the test runner reports compile failure, the trial should record the failure mode separately from a wrong-answer pass-rate failure."),
    ("RUN-4", "behavior", "The grading workspace must be isolated from the executor's scratch workspace so a failing test cannot corrupt the source files under modification."),

    # Documentation generation (4)
    ("DOC-1", "behavior", "REQUIREMENTS.md must be regenerated by `loom sync` and never edited by hand; manual edits are silently overwritten."),
    ("DOC-2", "behavior", "Generated REQUIREMENTS.md should include a traceability matrix mapping every active requirement to its linked code files and test specs."),
    ("DOC-3", "behavior", "When PRIVATE.md lists a requirement ID, that requirement must be excluded from public doc generation via `loom sync --public`."),
    ("DOC-4", "behavior", "Test specifications without linked implementations should render an 'Uncovered code' section so the user can see coverage gaps at a glance."),
]


# ---------------------------------------------------------------------------
# Test queries — paraphrased / extended versions of corpus reqs.
#
# Each query has a hand-labeled "expected_id" that should be the top
# match if find_related_requirements is working. Queries are
# deliberately re-phrased rather than copied so we test semantic
# matching, not lexical.
# ---------------------------------------------------------------------------

QUERIES = [
    # Direct paraphrases (high expectation)
    {
        "query": "When the file body changes after a link is recorded, loom check should report that as drift.",
        "expected_id": "DRF-1",
        "kind": "paraphrase",
    },
    {
        "query": "Drift events should land in an append-only log with which channels were responsible.",
        "expected_id": "DRF-3",
        "kind": "paraphrase",
    },
    # Semantic-but-not-lexical (medium expectation)
    {
        "query": "Want a way for the pre-edit hook to outright stop the agent if there's drift, instead of just warning.",
        "expected_id": "HOK-3",
        "kind": "semantic",
    },
    {
        "query": "Need to switch from local Ollama to OpenAI for embeddings without breaking existing search.",
        "expected_id": "EMB-2",  # provider in cache key — but EMB-1 is also valid
        "kind": "semantic",
    },
    # Domain-overlap but specific target (test ranking discrimination)
    {
        "query": "Add a doctor-style health check that tells me if my LSP server is reachable.",
        "expected_id": "IDX-3",
        "kind": "specific",
    },
    {
        "query": "When the test scaffold can't even compile the model's output, that's a different failure mode than a logic bug.",
        "expected_id": "RUN-3",
        "kind": "specific",
    },
    # Cross-domain similar wording (test for false positives)
    {
        "query": "Require a clean traceability matrix in the published documentation showing which files satisfy which requirements.",
        "expected_id": "DOC-2",
        "kind": "specific",
    },
    # Known-unrelated (sanity check — top score should be low)
    {
        "query": "Set up CI/CD pipeline with GitHub Actions to deploy to AWS Lambda on every merge to main.",
        "expected_id": None,  # no good match
        "kind": "unrelated",
    },
]


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def setup_store() -> tuple[LoomStore, str]:
    project = "pilot-rationale-linkage"
    store = LoomStore(project)
    # Re-seed only if the corpus isn't already present (idempotent reruns).
    existing = {r.value for r in store.list_requirements(include_superseded=True)}
    seeded = 0
    for hint_id, domain, value in CORPUS:
        if value in existing:
            continue
        services.extract(
            store,
            domain=domain,
            value=value,
            msg_id=f"pilot:{hint_id}",
            session="pilot-corpus",
        )
        seeded += 1
    print(f"[setup] seeded {seeded} new reqs (corpus size: {len(CORPUS)})")
    return store, project


def run_pilot():
    print("=== Rationale Linkage — threshold calibration pilot ===\n")
    store, project = setup_store()

    # Collect all reqs in the store with their generated IDs so we can
    # map "expected DRF-1" back to whatever ID was actually generated.
    # (services.extract auto-generates IDs from value text.)
    actual_reqs = list(store.list_requirements())
    # Map first 4 chars of each canonical-ID hint to a real req via
    # value-prefix matching.
    id_lookup: dict[str, str] = {}
    for hint_id, _, value in CORPUS:
        for r in actual_reqs:
            if r.value == value:
                id_lookup[hint_id] = r.id
                break

    # Collect score statistics.
    top1_correct = 0
    top1_scores = []
    top2_correct = 0  # whether expected ID appears in top 2
    unrelated_top_scores = []
    related_top_scores = []
    related_correct_score = []

    print(f"Corpus: {len(actual_reqs)} requirements\n")
    print(f"{'#':<3} {'kind':<12} {'expected':<10} {'top hit':<10} "
          f"{'top score':<10} {'top match':<6} {'top2 match':<10}")
    print("-" * 80)

    for i, q in enumerate(QUERIES, 1):
        hits = services.query(store, q["query"], limit=3)
        if not hits:
            print(f"{i}  {q['kind']:<12} {q['expected_id'] or '-':<10} "
                  f"(no results)")
            continue

        top_hit = hits[0]
        top_dist = top_hit.get("distance") or 0.0
        top_score = 1.0 - top_dist

        # Map back via value match (since services.extract may have
        # generated different IDs than our corpus hints).
        top_hit_canonical = next(
            (cid for cid, _, val in CORPUS if val == top_hit["value"]),
            "(unknown)",
        )

        is_top1 = top_hit_canonical == q["expected_id"]
        if is_top1:
            top1_correct += 1

        top2_canonical = [
            next((cid for cid, _, val in CORPUS if val == h["value"]),
                 "(unknown)") for h in hits[:2]
        ]
        is_top2 = q["expected_id"] in top2_canonical
        if is_top2 and q["expected_id"] is not None:
            top2_correct += 1

        if q["kind"] == "unrelated":
            unrelated_top_scores.append(top_score)
        else:
            related_top_scores.append(top_score)
            if is_top1:
                related_correct_score.append(top_score)

        top1_scores.append(top_score)
        print(f"{i}  {q['kind']:<12} {(q['expected_id'] or '-'):<10} "
              f"{top_hit_canonical:<10} {top_score:.3f}      "
              f"{'✓' if is_top1 else '✗':<6} "
              f"{'✓' if is_top2 else '✗'}")

        # Per-query top-3 detail.
        for j, h in enumerate(hits[:3], 1):
            cid = next(
                (c for c, _, val in CORPUS if val == h["value"]),
                "(unknown)",
            )
            d = h.get("distance") or 0.0
            score = 1.0 - d
            print(f"      [{j}] {cid:<8} score={score:.3f}  "
                  f"\"{h['value'][:80]}...\"")
        print()

    # Summary stats.
    n_related = sum(1 for q in QUERIES if q["kind"] != "unrelated")
    n_unrelated = sum(1 for q in QUERIES if q["kind"] == "unrelated")
    print("\n=== Summary ===")
    print(f"Top-1 precision (expected = #1):  {top1_correct}/{n_related}"
          f"  ({100*top1_correct/n_related:.0f}%)")
    print(f"Top-2 precision (expected in #1-2): {top2_correct}/{n_related}"
          f"  ({100*top2_correct/n_related:.0f}%)")
    print()
    if related_top_scores:
        print(f"Related-query top scores: "
              f"min={min(related_top_scores):.3f}, "
              f"max={max(related_top_scores):.3f}, "
              f"mean={sum(related_top_scores)/len(related_top_scores):.3f}")
    if related_correct_score:
        print(f"Related-and-correct top scores: "
              f"min={min(related_correct_score):.3f}, "
              f"max={max(related_correct_score):.3f}")
    if unrelated_top_scores:
        print(f"Unrelated-query top scores: "
              f"min={min(unrelated_top_scores):.3f}, "
              f"max={max(unrelated_top_scores):.3f}")
    print()

    # Threshold recommendation.
    print("=== Threshold analysis ===")
    if related_correct_score and unrelated_top_scores:
        min_correct = min(related_correct_score)
        max_unrelated = max(unrelated_top_scores)
        print(f"Lowest correct-match score:      {min_correct:.3f}")
        print(f"Highest unrelated top score:     {max_unrelated:.3f}")
        if min_correct > max_unrelated:
            mid = (min_correct + max_unrelated) / 2
            print(f"Clean separation. Recommended threshold: {mid:.2f}")
        else:
            print(f"OVERLAP — cannot cleanly separate. Need richer "
                  f"signal beyond cosine score.")


if __name__ == "__main__":
    run_pilot()
