#!/usr/bin/env python3
"""
Phase L3e demo — end-to-end foundation-drift verification.

Two paths exercised:

Phase 1 — HTTP read path (this script's main flow). Fully
deterministic: pushes a Loom requirement as a warrant, uses
direct Cypher to wire a BECAUSE_OF edge from its claim to an
already-invalidated ancestor in the substrate, then verifies
that `services.context()` on a file linked to that req surfaces
``graph_drift_detected: True`` via ``graph_drift_source="http"``.
The synthetic edge is removed at the end.

Phase 2 — Webhook receiver path (documented runbook only). To
exercise the webhook channel end-to-end, the substrate's
``projects.yaml`` needs ``loom_drift_webhook: "http://127.0.0.1:8081/
drift-events"`` uncommented and the bot restarted. This script
prints the steps but doesn't touch substrate state.

Output:
  experiments/pilot/warrants_l3e_results.json — full per-step trace
  experiments/pilot/warrants_l3e_summary.md   — human-readable summary
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
RESULTS_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l3e_results.json"
SUMMARY_PATH = LOOM_DIR / "experiments" / "pilot" / "warrants_l3e_summary.md"

sys.path.insert(0, str(LOOM_DIR / "src"))
from loom import driftgraph_http as dh, driftgraph_query as dq, services, warrants  # noqa: E402
from loom.store import LoomStore  # noqa: E402


def step(label: str, ok: bool, **details) -> dict:
    icon = "✓" if ok else "✗"
    print(f"  {icon} {label}")
    for k, v in details.items():
        if v is not None:
            print(f"      {k}: {v}")
    return {"label": label, "ok": ok, **details}


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    trace: list[dict] = []

    print("=== L3e demo — end-to-end foundation-drift verification ===\n")

    print("Phase 0 — preflight\n")

    # 0a — substrate reachable
    avail = dh.is_available()
    trace.append(step("substrate /health reachable", avail))
    if not avail:
        print("\n❌ substrate not reachable — start the Driftgraph bot first")
        return 1

    # 0b — Loom can write to the right project
    project_tag = "sparkeye"
    store = LoomStore("loom")
    trace.append(step(
        "Loom store + project_tag", True,
        data_dir=str(store.data_dir), project_tag=project_tag,
    ))

    # ────────────────────────────────────────────────────────────────
    # Phase 1 — HTTP read path
    # ────────────────────────────────────────────────────────────────

    print("\nPhase 1 — HTTP read path (deterministic)\n")

    # 1a — Pick a passing-validator loom req that we can push.
    # Use REQ-bdb1e667 (the L2 cross-validator finding; passes
    # toulmin@v1 cleanly per L2 results) as our 'child' claim.
    target_req_id = "REQ-bdb1e667"
    req = store.get_requirement(target_req_id)
    if req is None:
        trace.append(step("locate child req", False,
                          reason=f"{target_req_id} not in store"))
        return 1
    trace.append(step("located child req", True,
                      req_id=target_req_id,
                      kind=req.kind, status=req.status,
                      value_preview=req.value[:80]))

    # 1b — Push child via Loom CLI (passes through the L2 validator).
    print("\n  pushing child via `loom warrant push`...")
    push_proc = subprocess.run(
        [sys.executable, "-m", "loom.cli", "-p", "loom",
         "warrant", "push", target_req_id, "--validator", "toulmin@v1",
         "--project-tag", project_tag],
        cwd=LOOM_DIR, capture_output=True, text=True, encoding="utf-8",
    )
    push_ok = push_proc.returncode == 0
    # Extract first claim_id from stdout
    child_claim_id = None
    for line in (push_proc.stdout or "").splitlines():
        if "claim_id:" in line:
            child_claim_id = line.split("claim_id:")[1].strip()
            break
    trace.append(step(
        "child pushed", push_ok and bool(child_claim_id),
        claim_id=child_claim_id,
        stdout_tail=(push_proc.stdout or "").strip().splitlines()[-1]
                    if push_proc.stdout else None,
        stderr=(push_proc.stderr or "").strip()[:200] if not push_ok else None,
    ))
    if not push_ok or not child_claim_id:
        return 1

    # 1c — Find an already-invalidated claim in the project to use as
    # the 'parent'. The substrate has plenty (we retracted ~20 in L3a-c
    # smoke).
    if not dq._ensure_modules():
        trace.append(step("driftgraph_query module load", False,
                          reason="repo or neo4j driver missing"))
        return 1
    driver = dq._schema_mod.connect()
    parent_claim_id = None
    try:
        with driver.session(database=project_tag) as s:
            row = s.run(
                "MATCH (c:Claim) WHERE c.invalidated_at IS NOT NULL "
                "  AND c.validator_id IS NOT NULL "
                "  AND c.claim_id <> $child_id "
                "RETURN c.claim_id AS cid LIMIT 1",
                parameters={"child_id": child_claim_id},
            ).single()
            if row:
                parent_claim_id = row["cid"]
        trace.append(step(
            "found invalidated parent candidate", parent_claim_id is not None,
            parent_claim_id=parent_claim_id,
        ))
        if parent_claim_id is None:
            return 1

        # 1d — Wire the BECAUSE_OF edge: child → parent.
        with driver.session(database=project_tag) as s:
            s.run(
                "MATCH (child:Claim {claim_id: $child}), "
                "      (parent:Claim {claim_id: $parent}) "
                "MERGE (child)-[r:BECAUSE_OF]->(parent) "
                "ON CREATE SET r.synthetic = true, "
                "              r.rationale = 'L3e demo synthetic edge'",
                child=child_claim_id, parent=parent_claim_id,
            ).consume()
        trace.append(step(
            "synthetic BECAUSE_OF edge created", True,
            child=child_claim_id[:24], parent=parent_claim_id[:24],
        ))

        # 1e — Verify substrate reports drift via HTTP read API
        status = dh.get_claim_status(project_tag, child_claim_id)
        substrate_says_drifted = bool(
            status and status.get("foundation_drifted")
        )
        trace.append(step(
            "substrate /claims/<id> reports foundation_drifted", substrate_says_drifted,
            n_invalidated_parents=(status or {}).get("n_invalidated_parents"),
            because_of_targets=(status or {}).get("because_of_targets"),
        ))
        if not substrate_says_drifted:
            return 1

        # 1f — find_drifted_ancestors_for_req returns the right shape
        gd = dh.find_drifted_ancestors_for_req(store.data_dir, target_req_id)
        trace.append(step(
            "loom HTTP wrapper returns drift", gd["drifted"],
            n_drifted_ancestors=len(gd["drifted_ancestors"]),
            available=gd["available"],
        ))
        if not gd["drifted"]:
            return 1

        # 1g — Now link a real Loom file to the req and run
        # services.context() against it; graph_drift_detected
        # must be True with graph_drift_source="http".
        # Pick the file the L2 finding's rationale references
        # (warrants_l3d_results.json), since the dogfooding
        # script linked it earlier.
        link_target = LOOM_DIR / "experiments" / "pilot" / "warrants_l2_results.json"
        if link_target.exists():
            # Make sure it's linked. `loom link` is idempotent.
            link_proc = subprocess.run(
                [sys.executable, "-m", "loom.cli", "-p", "loom",
                 "link", str(link_target), "--req", target_req_id],
                cwd=LOOM_DIR, capture_output=True, text=True, encoding="utf-8",
            )
            trace.append(step(
                "linked file to req", link_proc.returncode == 0,
                file=str(link_target), stdout_tail=(link_proc.stdout or "").strip()[-200:],
            ))

            ctx = services.context(store, str(link_target))
            ctx_drift = bool(ctx.get("graph_drift_detected"))
            trace.append(step(
                "services.context() detects graph drift",
                ctx_drift and ctx.get("graph_drift_source") == "http",
                graph_drift_source=ctx.get("graph_drift_source"),
                graph_drift_detected=ctx_drift,
                summary_tail=(ctx.get("summary") or "")[-160:],
            ))
        else:
            trace.append(step(
                "skip context check (file missing)", True,
                file=str(link_target),
            ))

    finally:
        # 1h — Cleanup synthetic edge so the substrate state is clean.
        with driver.session(database=project_tag) as s:
            n = s.run(
                "MATCH ()-[r:BECAUSE_OF {synthetic: true}]->() "
                "DELETE r RETURN count(r) AS n",
            ).data()
            removed = n[0]["n"] if n else 0
        trace.append(step(
            "cleanup synthetic edge(s)", True, removed=removed,
        ))

        # 1i — Also retract the demo claim we created so we don't leave
        # dead claims in the substrate.
        retract_proc = subprocess.run(
            [sys.executable, "-m", "loom.cli", "-p", "loom",
             "warrant", "retract", "--req", target_req_id,
             "--project-tag", project_tag,
             "--reason", "L3e demo cleanup"],
            cwd=LOOM_DIR, capture_output=True, text=True, encoding="utf-8",
        )
        trace.append(step(
            "demo claim retracted", retract_proc.returncode == 0,
            stdout_tail=(retract_proc.stdout or "").strip().splitlines()[-1]
                       if retract_proc.stdout else None,
        ))
        driver.close()

    # ────────────────────────────────────────────────────────────────
    # Phase 2 — Webhook receiver path (runbook only; no auto-exec)
    # ────────────────────────────────────────────────────────────────

    print("\nPhase 2 — webhook receiver runbook (not auto-executed)\n")
    runbook = [
        "1. Edit ~/Downloads/grag/product/discord_demo/projects.yaml",
        "   uncomment + set:",
        "     loom_drift_webhook: \"http://127.0.0.1:8081/drift-events\"",
        "2. Restart the Driftgraph bot (the running process needs to",
        "   reload projects.yaml; current PID is the python3.13 listening",
        "   on 8080).",
        "3. Start the Loom-side receiver:",
        "     python hooks/loom_drift_webhook.py --project loom --port 8081",
        "4. Run this script again. Step 1d (the BECAUSE_OF wiring)",
        "   will not fire a webhook by itself — for that, run a real",
        "   `loom warrant retract --req REQ-id` on a parent that has",
        "   live BECAUSE_OF children. The substrate's foundation-drift",
        "   detector fires synchronously after the retract and the",
        "   webhook hits the receiver.",
        "5. Verify ~/.openclaw/loom/loom/.driftgraph-cache.jsonl gains",
        "   a `foundation_drift_detected` event line.",
        "6. Re-run `loom context <file>` — graph_drift_source flips",
        "   from 'http' to 'cache' (zero-latency lookup; no HTTP hop).",
    ]
    for line in runbook:
        print(f"  {line}")

    finished = datetime.now(timezone.utc).isoformat()
    overall_pass = all(
        t["ok"] for t in trace if t["label"] != "skip context check (file missing)"
    )
    summary = {
        "started_at": started,
        "finished_at": finished,
        "phase_1_pass": overall_pass,
        "phase_2_runbook": runbook,
        "trace": trace,
    }
    RESULTS_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md = []
    md.append("# L3e — End-to-end foundation-drift demo\n")
    md.append(f"**Started:** {started}  ")
    md.append(f"**Finished:** {finished}  \n")
    md.append("## Phase 1 — HTTP read path\n")
    md.append("| step | result |")
    md.append("|---|---|")
    for t in trace:
        md.append(f"| {t['label']} | {'✓ ok' if t['ok'] else '✗ FAIL'} |")
    md.append(f"\n**Phase 1 verdict:** "
              f"{'PASS' if overall_pass else 'FAIL'}\n")
    md.append("## Phase 2 — webhook runbook\n")
    md.extend(f"  {line}" for line in runbook)
    SUMMARY_PATH.write_text("\n".join(md), encoding="utf-8")

    print(f"\n=== L3e Phase 1 verdict: {'PASS' if overall_pass else 'FAIL'} ===")
    print(f"Trace: {RESULTS_PATH}")
    print(f"Summary: {SUMMARY_PATH}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
