#!/usr/bin/env python3
"""
Driftgraph → Loom webhook receiver (M13.5d).

Listens on a configurable port for events the Driftgraph substrate
fires when graph state changes (claim_created / claim_invalidated /
supersedes / foundation_drift). Verifies the HMAC signature using
the same shared secret as the outbound /warrants endpoint
(``LOOM_WEBHOOK_SECRET`` or ``~/.driftgraph/loom-webhook-secret``)
— substrate ↔ Loom are symmetric. On valid events, appends the
payload to the project's local cache via
``loom.driftgraph_cache.record_event``.

Run as a daemon on the agent's machine alongside whatever long-
running Claude Code session needs fresh graph state. Loom's
PreToolUse hook reads from the cache with zero latency; the
receiver keeps the cache fresh in the background.

  python hooks/loom_drift_webhook.py --project loom --port 8081

Environment:
  LOOM_WEBHOOK_SECRET    — same shared secret as outbound. If unset,
                          tries ~/.driftgraph/loom-webhook-secret.
                          Empty = receiver refuses to start.
  LOOM_DRIFT_PORT        — default 8081 (NOT 8080; that's
                          Driftgraph's outbound endpoint we POST to).

Stdlib-only on purpose: no aiohttp, no extra deps. The receiver
is a fallback to the future cleaner implementation; the dep budget
matters.

Substrate-side contract (per the Driftgraph dev's M13.5 plan):
  POST /drift-events
  Headers:
    Content-Type: application/json
    X-Hub-Signature-256: sha256=<hmac-sha256 of body using shared secret>

  Body (one of):
    {project, event: "claim_created",     claim_id, episode_id, ...}
    {project, event: "claim_invalidated", retracted_claim_id, ...}
    {project, event: "supersedes",        invalidated_claim_id,
                                           by_claim_id, ...}
    {project, event: "foundation_drift",  retracted_claim_id,
                                           dependents: [{claim_id, ...}],
                                           detected_at}

The receiver is event-shape-agnostic — anything that arrives gets
appended to the cache verbatim; the cache reader
(loom.driftgraph_cache.compute_claim_state) does the per-event-kind
interpretation. This means substrate-side payload additions don't
require receiver-side updates.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Match the rest of Loom — force UTF-8 stdout/stderr so emoji in
# log lines don't trip cp1252 on Windows console hosts.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Make the loom package importable when run as a script.
_HERE = Path(__file__).resolve().parent
_SRC = _HERE.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from loom import driftgraph_cache  # noqa: E402
from loom import warrants  # noqa: E402  — for load_secret()
from loom.store import LoomStore  # noqa: E402


log = logging.getLogger("loom.drift_webhook")


def _verify_hmac(secret: str, body: bytes, sig_header: str) -> bool:
    """GitHub-style HMAC verification — same shape as
    Driftgraph's warrants_endpoint.verify_hmac so the symmetry
    holds: Loom signs outbound with this secret, Driftgraph signs
    inbound with the same secret."""
    if not secret or not sig_header:
        return False
    if not sig_header.startswith("sha256="):
        return False
    expected = (
        "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, sig_header)


def _make_handler(*, secret: str, project: str):
    """Closure-bind config so the stdlib handler factory can create
    instances without per-request lookups."""
    store = LoomStore(project)
    data_dir = Path(store.data_dir)

    class DriftHandler(BaseHTTPRequestHandler):
        # Suppress stdlib's default access-log spam (one line per
        # request to stderr). Replace with structured logging in L4.
        def log_message(self, fmt, *args):
            log.debug("%s - - %s", self.address_string(), fmt % args)

        def _send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, {"ok": True, "service": "loom-drift-receiver",
                                 "project": project})
                return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/drift-events":
                self._send(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length > 0 else b""
            sig = self.headers.get("X-Hub-Signature-256", "")
            if not _verify_hmac(secret, body, sig):
                self._send(401, {"error": "invalid signature"})
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                self._send(400, {"error": f"invalid JSON: {e}"})
                return
            if not isinstance(payload, dict):
                self._send(400, {"error": "payload must be a JSON object"})
                return
            # Optional safety: refuse events for OTHER projects so
            # one mis-configured webhook can't pollute another
            # loom store. The receiver knows its project at startup.
            ev_project = payload.get("project")
            if ev_project and ev_project != project:
                # Not an error — just ignored. Substrate may broadcast
                # to multiple receivers; each filters.
                self._send(200, {"ok": True, "ignored": "project_mismatch"})
                return
            driftgraph_cache.record_event(data_dir, payload)
            log.info("recorded event=%s project=%s",
                     payload.get("event", "?"), project)
            self._send(200, {"ok": True,
                             "event": payload.get("event"),
                             "received_at_cache": str(
                                 driftgraph_cache.cache_path(data_dir),
                             )})

    return DriftHandler


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=(
            "Driftgraph → Loom webhook receiver. Listens for graph "
            "state-change events and persists them to the per-project "
            "cache under <data_dir>/.driftgraph-cache.jsonl."
        ),
    )
    p.add_argument("--project", required=True,
                   help="Loom project whose cache should receive events. "
                        "Determines which <data_dir>/.driftgraph-cache.jsonl "
                        "file gets written.")
    p.add_argument(
        "--port", type=int,
        default=int(os.environ.get("LOOM_DRIFT_PORT", "8081")),
        help="TCP port to listen on (default: 8081 / "
             "$LOOM_DRIFT_PORT). NOT 8080 — that's Driftgraph's "
             "outbound /warrants endpoint we POST to.",
    )
    p.add_argument("--bind", default="127.0.0.1",
                   help="Listen address (default: 127.0.0.1)")
    p.add_argument("--quiet", action="store_true",
                   help="Suppress per-event log lines")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    secret = warrants.load_secret()
    if not secret:
        print(
            "❌ no LOOM_WEBHOOK_SECRET — set the env var or write the "
            "secret to ~/.driftgraph/loom-webhook-secret. Without it "
            "the receiver can't verify substrate signatures and "
            "refuses to start.", file=sys.stderr,
        )
        return 1

    handler_cls = _make_handler(secret=secret, project=args.project)
    server = HTTPServer((args.bind, args.port), handler_cls)
    print(
        f"🪨 Loom drift webhook receiver — project={args.project} "
        f"listening on http://{args.bind}:{args.port}/drift-events",
    )
    print("   (HMAC-verified via LOOM_WEBHOOK_SECRET; "
          "events appended to .driftgraph-cache.jsonl)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
    return 0


if __name__ == "__main__":
    sys.exit(main())
