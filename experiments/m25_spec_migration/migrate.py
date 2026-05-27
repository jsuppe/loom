#!/usr/bin/env python3
"""
M25 — Migrate existing direct req→impl links to req→spec→impl per
REQ-7df25683.

For each impl in the loom store that has a direct req-link (a
satisfies entry with a req_id and no corresponding spec), this tool:

1. Reads the file content (truncated for embedding-cap compatibility)
2. Calls qwen3.5:latest via Ollama to produce a contract-style spec
   text summarizing what the file does to operationalize the req
3. Creates a Specification with parent_req = the original req
4. Adds the spec id to the impl's satisfies_specs
5. (Optionally — see --keep-req-links) removes the req from the
   impl's satisfies, severing the direct link

One spec is generated per (req, file) pair. If one file satisfies
multiple reqs, multiple specs are produced (one per req), each
describing what that file does to operationalize THAT req.

Usage:
    python migrate.py --dry-run         # show plan, no writes
    python migrate.py --apply           # commit changes
    python migrate.py --apply --keep-req-links   # leave direct links in place; just add specs
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
sys.path.insert(0, str(_REPO / "src"))

from loom.embedding import get_embedding  # noqa: E402
from loom.store import LoomStore, Specification  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PROJECT = "loom"
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3.5:latest"
LOG_PATH = _HERE / "migration_log.jsonl"


def call_ollama(prompt: str, timeout: int = 120) -> str:
    body = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "seed": 42,
            "num_predict": 400,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return (data.get("response") or "").strip()


SPEC_PROMPT = """You are helping migrate a software-requirements-tracing store. A
Requirement describes intent; a Specification describes the contract
of a particular implementation that operationalizes that requirement.

Below is a Requirement and the head of a file that implements it.
Write a SPECIFICATION: a contract-style summary of WHAT THIS FILE
provides toward fulfilling the requirement.

Rules:
* 2-4 sentences total
* Focus on the contract (what the file exposes, what guarantees it
  makes) NOT the implementation details (no "uses a for loop")
* Reference specific function/class names from the file if useful
* Do NOT restate the requirement verbatim
* Output ONLY the specification text, no preamble, no "Specification:"
  prefix

--- REQUIREMENT ---
ID: {req_id}
Domain: {req_domain}
Value: {req_value}
Rationale: {req_rationale}

--- FILE: {file} ---
{file_head}

--- SPECIFICATION ---
"""


def head_of(path: Path, max_chars: int = 3500) -> str:
    """Read the first ~3500 chars of a file. Falls back to '' if
    the file isn't on disk or is binary."""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "\n# … (truncated)"
    return text


def collect_direct_links(store: LoomStore) -> list[tuple]:
    """Return [(impl, req_id, req_obj), ...] for every direct
    req-impl link in the store. A 'direct link' is a satisfies entry
    that has a req_id and the impl has empty satisfies_specs (i.e. no
    spec mediating the link)."""
    reqs_by_id = {r.id: r for r in store.list_requirements(include_superseded=True)}
    pairs = []
    for imp in store.list_implementations():
        has_specs = bool(imp.satisfies_specs and imp.satisfies_specs != ["TBD"])
        if has_specs:
            continue  # already mediated
        for s_ref in (imp.satisfies or []):
            rid = s_ref.get("req_id")
            if not rid:
                continue
            req = reqs_by_id.get(rid)
            if req is None:
                continue
            # Only migrate links to requirement-kind targets; evidence
            # links to findings/methodology are a different relationship.
            req_kind = getattr(req, "kind", "requirement")
            link_type = s_ref.get("link_type", "implementation")
            if req_kind != "requirement" or link_type == "evidences":
                continue
            pairs.append((imp, rid, req))
    return pairs


def generate_spec_id() -> str:
    return f"SPEC-{uuid.uuid4().hex[:8]}"


def log_event(event: dict) -> None:
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="commit changes; default is dry-run")
    ap.add_argument("--keep-req-links", action="store_true",
                    help="leave direct req-links in satisfies; only "
                         "add specs to satisfies_specs (lossy migration)")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after N migrations (0 = no limit)")
    args = ap.parse_args()

    store = LoomStore(PROJECT)
    pairs = collect_direct_links(store)

    print(f"Found {len(pairs)} direct req→impl link(s) to migrate")
    if args.limit and len(pairs) > args.limit:
        pairs = pairs[:args.limit]
        print(f"  (limited to first {args.limit})")
    print()

    if not args.apply:
        print("Dry-run plan:")
        for imp, rid, req in pairs:
            print(f"  {imp.file}  ->  {rid}  ({(req.value or '')[:60]}…)")
        print()
        print(f"Pass --apply to commit (will call Ollama "
              f"{len(pairs)}× ≈ {len(pairs)*5}s)")
        return 0

    print(f"Calling Ollama {len(pairs)} times. Estimated ~{len(pairs)*5}s…")
    print()
    run_ts = datetime.now(timezone.utc).isoformat()
    log_event({
        "run_started": run_ts,
        "count": len(pairs),
        "keep_req_links": args.keep_req_links,
    })

    success = 0
    for i, (imp, rid, req) in enumerate(pairs, 1):
        t0 = time.time()
        file_path = _REPO / imp.file
        file_head = head_of(file_path)
        if not file_head:
            print(f"  [{i}/{len(pairs)}] {imp.file}  ⚠ file not on disk; "
                  f"generating spec from req text alone")
        prompt = SPEC_PROMPT.format(
            req_id=rid, req_domain=req.domain or "",
            req_value=req.value or "",
            req_rationale=req.rationale or "(no rationale captured)",
            file=imp.file,
            file_head=file_head or "(file not available on disk)",
        )
        try:
            spec_text = call_ollama(prompt)
        except Exception as e:
            print(f"  [{i}/{len(pairs)}] {imp.file} -> {rid}  ERROR: {e}")
            log_event({"ts": datetime.now(timezone.utc).isoformat(),
                        "impl_id": imp.id, "req_id": rid,
                        "file": imp.file, "error": str(e)})
            continue

        if not spec_text:
            spec_text = f"Implementation of {rid} in {imp.file}."
            print(f"  [{i}/{len(pairs)}] {imp.file} -> {rid}  ⚠ empty model "
                  f"response; using placeholder")

        spec_id = generate_spec_id()
        spec = Specification(
            id=spec_id,
            parent_req=rid,
            description=spec_text,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="draft",
            source_doc=f"auto-migrated from direct link on {imp.file}",
        )
        store.add_specification(spec, get_embedding(spec_text))

        # Update impl: add spec to satisfies_specs; optionally remove req.
        new_satisfies_specs = list(imp.satisfies_specs or [])
        if new_satisfies_specs == ["TBD"]:
            new_satisfies_specs = []
        new_satisfies_specs.append(spec_id)
        new_satisfies = list(imp.satisfies or [])
        if not args.keep_req_links:
            new_satisfies = [s for s in new_satisfies
                              if s.get("req_id") != rid]

        # Re-insert the impl with the updated link fields. We delete
        # and re-add since the store API doesn't expose an in-place
        # update of satisfies fields.
        store.delete_implementation(imp.id)
        imp.satisfies = new_satisfies
        imp.satisfies_specs = new_satisfies_specs
        store.add_implementation(imp, get_embedding(imp.content or " "))

        elapsed = time.time() - t0
        print(f"  [{i}/{len(pairs)}] {imp.file}  ->  {spec_id} "
              f"-> {rid}  ({elapsed:.1f}s)")
        print(f"     spec: {spec_text[:140]}{'…' if len(spec_text)>140 else ''}")
        log_event({"ts": datetime.now(timezone.utc).isoformat(),
                    "impl_id": imp.id, "req_id": rid, "spec_id": spec_id,
                    "file": imp.file, "spec_text": spec_text})
        success += 1

    print()
    print(f"Migration complete: {success}/{len(pairs)} succeeded")
    print(f"Log: {LOG_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
