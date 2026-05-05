# L3e — End-to-end foundation-drift demo

**Started:** 2026-05-05T12:14:57.037595+00:00  
**Finished:** 2026-05-05T12:15:08.975370+00:00  

## Phase 1 — HTTP read path

| step | result |
|---|---|
| substrate /health reachable | ✓ ok |
| Loom store + project_tag | ✓ ok |
| located child req | ✓ ok |
| child pushed | ✓ ok |
| found invalidated parent candidate | ✓ ok |
| synthetic BECAUSE_OF edge created | ✓ ok |
| substrate /claims/<id> reports foundation_drifted | ✓ ok |
| loom HTTP wrapper returns drift | ✓ ok |
| linked file to req | ✓ ok |
| services.context() detects graph drift | ✓ ok |
| cleanup synthetic edge(s) | ✓ ok |
| demo claim retracted | ✓ ok |

**Phase 1 verdict:** PASS

## Phase 2 — webhook runbook

  1. Edit ~/Downloads/grag/product/discord_demo/projects.yaml
     uncomment + set:
       loom_drift_webhook: "http://127.0.0.1:8081/drift-events"
  2. Restart the Driftgraph bot (the running process needs to
     reload projects.yaml; current PID is the python3.13 listening
     on 8080).
  3. Start the Loom-side receiver:
       python hooks/loom_drift_webhook.py --project loom --port 8081
  4. Run this script again. Step 1d (the BECAUSE_OF wiring)
     will not fire a webhook by itself — for that, run a real
     `loom warrant retract --req REQ-id` on a parent that has
     live BECAUSE_OF children. The substrate's foundation-drift
     detector fires synchronously after the retract and the
     webhook hits the receiver.
  5. Verify ~/.openclaw/loom/loom/.driftgraph-cache.jsonl gains
     a `foundation_drift_detected` event line.
  6. Re-run `loom context <file>` — graph_drift_source flips
     from 'http' to 'cache' (zero-latency lookup; no HTTP hop).