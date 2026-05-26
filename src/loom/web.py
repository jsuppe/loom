"""
Loom Web UI — local browsing surface for reqs / specs / findings / files.

A minimal FastAPI app served on localhost:8090 by ``loom ui``. Read-only
v1; mutations stay CLI/MCP-driven. Single-project per server start
(``loom ui -p sparkeye``). Localhost-only bind by design (same security
model as Ollama).

Architecture: route handlers call ``loom.services`` for data access —
no SQL or store internals in routes. Templates are Jinja2; no JS
framework, no build step.

Install: ``pip install loom-cli[ui]`` to pull in fastapi / uvicorn /
jinja2 (optional dep). If those aren't importable, ``loom ui`` exits
with an install hint.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from . import services as _services
from .store import LoomStore

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates
    _HAS_UI_DEPS = True
except ImportError:
    _HAS_UI_DEPS = False


_TEMPLATES_DIR = Path(__file__).parent / "templates" / "web"


def _check_deps() -> None:
    if not _HAS_UI_DEPS:
        raise RuntimeError(
            "loom ui requires fastapi + uvicorn + jinja2. Install with:\n"
            "    pip install 'loom-cli[ui]'\n"
            "or directly:\n"
            "    pip install fastapi uvicorn jinja2"
        )


def _humanize_ts(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        ts = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return ts.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return iso


def _kind_color(kind: str) -> str:
    return {
        "requirement": "blue",
        "finding": "green",
        "methodology": "purple",
        "hypothesis": "orange",
        "process_rule": "teal",
    }.get(kind, "gray")


def _status_color(status: str) -> str:
    return {
        "pending": "gray",
        "in_progress": "blue",
        "implemented": "teal",
        "verified": "green",
        "superseded": "orange",
        "archived": "gray",
        # finding states
        "captured": "blue",
        "refined": "teal",
        "confirmed": "green",
        "refuted": "red",
        # methodology / process_rule
        "active": "green",
        "deprecated": "gray",
    }.get(status, "gray")


def create_app(project: str) -> "FastAPI":
    """Build the FastAPI app bound to a specific project store."""
    _check_deps()

    app = FastAPI(title=f"Loom UI — {project}")
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    templates.env.filters["humanize_ts"] = _humanize_ts
    templates.env.filters["kind_color"] = _kind_color
    templates.env.filters["status_color"] = _status_color

    def _render(request: Request, name: str, **extra: Any):
        ctx = {"project": project}
        ctx.update(extra)
        return templates.TemplateResponse(request, name, ctx)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        store = LoomStore(project)
        reqs = list(store.list_requirements())
        by_kind: Counter = Counter()
        by_status: Counter = Counter()
        for r in reqs:
            by_kind[getattr(r, "kind", "requirement")] += 1
            by_status[r.status or "pending"] += 1
        impls = list(store.list_implementations())
        recent_events = _recent_events(project, limit=15)
        try:
            doctor_data = _services.doctor(store)
        except Exception:
            doctor_data = {}
        return _render(
            request, "dashboard.html",
            req_count=len(reqs),
            impl_count=len(impls),
            by_kind=dict(by_kind),
            by_status=dict(by_status),
            recent_events=recent_events,
            doctor=doctor_data,
        )

    # ------------------------------------------------------------------
    # M23.1 — Requirements list + detail
    # ------------------------------------------------------------------

    @app.get("/reqs", response_class=HTMLResponse)
    def reqs_list(request: Request,
                   kind: Optional[str] = None,
                   status: Optional[str] = None,
                   domain: Optional[str] = None,
                   q: Optional[str] = None):
        store = LoomStore(project)
        reqs = list(store.list_requirements())
        if kind:
            reqs = [r for r in reqs if getattr(r, "kind", "requirement") == kind]
        if status:
            reqs = [r for r in reqs if (r.status or "pending") == status]
        if domain:
            reqs = [r for r in reqs if r.domain == domain]
        if q:
            q_low = q.lower()
            reqs = [
                r for r in reqs
                if q_low in (r.value or "").lower()
                or q_low in (r.id or "").lower()
                or q_low in (r.elaboration or "").lower()
            ]
        # Sort by status (active first), then timestamp desc
        active_first = {"pending": 0, "in_progress": 1, "captured": 2, "active": 3}
        reqs.sort(
            key=lambda r: (
                active_first.get(r.status or "pending", 99),
                -(_dt.datetime.fromisoformat(
                    (r.timestamp or "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")
                ).timestamp() if r.timestamp else 0),
            ),
        )
        # Distinct values for filter widgets
        all_reqs = list(store.list_requirements())
        kinds_avail = sorted({getattr(r, "kind", "requirement") for r in all_reqs})
        statuses_avail = sorted({r.status or "pending" for r in all_reqs})
        domains_avail = sorted({r.domain or "—" for r in all_reqs})
        return _render(
            request, "reqs_list.html",
            reqs=reqs,
            total=len(all_reqs),
            shown=len(reqs),
            kinds_avail=kinds_avail,
            statuses_avail=statuses_avail,
            domains_avail=domains_avail,
            filter_kind=kind or "",
            filter_status=status or "",
            filter_domain=domain or "",
            q=q or "",
            list_title="Requirements",
            list_active="reqs",
        )

    @app.get("/reqs/{req_id}", response_class=HTMLResponse)
    def reqs_detail(request: Request, req_id: str):
        store = LoomStore(project)
        req = store.get_requirement(req_id)
        if req is None:
            raise HTTPException(status_code=404, detail=f"req {req_id} not found")

        # Linked impls
        impls = [
            i for i in store.list_implementations()
            if any(s.get("req_id") == req_id for s in (i.satisfies or []))
        ]

        # Linked specs (specs whose parent_req matches)
        try:
            specs = [s for s in store.list_specifications()
                     if getattr(s, "parent_req", None) == req_id]
        except AttributeError:
            specs = []

        # Derivation chain — reqs this one derives from + reqs that derive from this
        derives_from_ids = list(getattr(req, "rationale_links", []) or [])
        derives_from = [store.get_requirement(rid) for rid in derives_from_ids]
        derives_from = [r for r in derives_from if r]

        all_reqs = list(store.list_requirements())
        derives_to = [
            r for r in all_reqs
            if req_id in (getattr(r, "rationale_links", []) or [])
        ]

        return _render(
            request, "req_detail.html",
            req=req,
            kind=getattr(req, "kind", "requirement"),
            impls=impls,
            specs=specs,
            derives_from=derives_from,
            derives_to=derives_to,
            list_active="reqs" if getattr(req, "kind", "requirement") == "requirement" else "findings",
        )

    # ------------------------------------------------------------------
    # M23.2 — Findings list + Specs detail
    # ------------------------------------------------------------------

    @app.get("/findings", response_class=HTMLResponse)
    def findings_list(request: Request,
                       status: Optional[str] = None,
                       domain: Optional[str] = None,
                       q: Optional[str] = None):
        # Reuse reqs_list machinery with locked kind=finding.
        store = LoomStore(project)
        reqs = [r for r in store.list_requirements()
                if getattr(r, "kind", "requirement") == "finding"]
        if status:
            reqs = [r for r in reqs if (r.status or "pending") == status]
        if domain:
            reqs = [r for r in reqs if r.domain == domain]
        if q:
            q_low = q.lower()
            reqs = [
                r for r in reqs
                if q_low in (r.value or "").lower()
                or q_low in (r.id or "").lower()
                or q_low in (r.rationale or "").lower()
            ]
        reqs.sort(
            key=lambda r: -(_dt.datetime.fromisoformat(
                (r.timestamp or "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")
            ).timestamp() if r.timestamp else 0),
        )
        all_findings = [r for r in store.list_requirements()
                         if getattr(r, "kind", "requirement") == "finding"]
        statuses_avail = sorted({r.status or "pending" for r in all_findings})
        domains_avail = sorted({r.domain or "—" for r in all_findings})
        return _render(
            request, "reqs_list.html",
            reqs=reqs,
            total=len(all_findings),
            shown=len(reqs),
            kinds_avail=[],  # kind facet hidden — locked to finding
            statuses_avail=statuses_avail,
            domains_avail=domains_avail,
            filter_kind="finding",
            filter_status=status or "",
            filter_domain=domain or "",
            q=q or "",
            list_title="Findings",
            list_active="findings",
        )

    @app.get("/specs", response_class=HTMLResponse)
    def specs_list(request: Request):
        store = LoomStore(project)
        try:
            specs = list(store.list_specifications())
        except AttributeError:
            specs = []
        specs.sort(key=lambda s: s.id or "")
        return _render(
            request, "specs_list.html",
            specs=specs,
        )

    @app.get("/specs/{spec_id}", response_class=HTMLResponse)
    def specs_detail(request: Request, spec_id: str):
        store = LoomStore(project)
        try:
            spec = store.get_specification(spec_id)
        except AttributeError:
            spec = None
        if spec is None:
            raise HTTPException(status_code=404, detail=f"spec {spec_id} not found")

        parent = None
        if getattr(spec, "parent_req", None):
            parent = store.get_requirement(spec.parent_req)

        # Impls satisfying this spec
        impls = [
            i for i in store.list_implementations()
            if spec_id in [s if isinstance(s, str) else s.get("spec_id")
                            for s in (i.satisfies_specs or [])]
        ]
        return _render(
            request, "spec_detail.html",
            spec=spec,
            parent=parent,
            impls=impls,
        )

    # ------------------------------------------------------------------
    # M23.3 — Files list + detail
    # ------------------------------------------------------------------

    @app.get("/files", response_class=HTMLResponse)
    def files_list(request: Request, q: Optional[str] = None):
        store = LoomStore(project)
        impls = list(store.list_implementations())
        # Group by file
        by_file: dict[str, list] = {}
        for imp in impls:
            if not imp.file:
                continue
            by_file.setdefault(imp.file, []).append(imp)
        rows = []
        for fpath, group in by_file.items():
            req_ids = set()
            for imp in group:
                for s_ref in (imp.satisfies or []):
                    if s_ref.get("req_id"):
                        req_ids.add(s_ref["req_id"])
            rows.append({
                "file": fpath,
                "impl_count": len(group),
                "req_ids": sorted(req_ids),
                "last_updated": max(
                    (imp.timestamp or "") for imp in group
                ),
            })
        if q:
            q_low = q.lower()
            rows = [r for r in rows if q_low in r["file"].lower()]
        rows.sort(key=lambda r: r["file"])
        return _render(
            request, "files_list.html",
            files=rows, total=len(by_file), shown=len(rows), q=q or "",
        )

    @app.get("/files/{path:path}", response_class=HTMLResponse)
    def files_detail(request: Request, path: str):
        store = LoomStore(project)
        impls = [i for i in store.list_implementations()
                  if i.file == path]
        if not impls:
            raise HTTPException(status_code=404,
                                 detail=f"file {path} has no linked impls")
        # Collect all linked reqs across the file's impls.
        req_ids: set = set()
        for imp in impls:
            for s_ref in (imp.satisfies or []):
                if s_ref.get("req_id"):
                    req_ids.add(s_ref["req_id"])
        reqs = [store.get_requirement(rid) for rid in sorted(req_ids)]
        reqs = [r for r in reqs if r]

        # Recent git commits touching this file
        recent_commits = _recent_commits_for(path, limit=10)

        # Current drift status via services.check
        try:
            drift = _services.check(store, path)
        except Exception:
            drift = None

        return _render(
            request, "file_detail.html",
            path=path, impls=impls, reqs=reqs,
            recent_commits=recent_commits,
            drift=drift,
        )

    # ------------------------------------------------------------------
    # M23.4 — Semantic search
    # ------------------------------------------------------------------

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: Optional[str] = None,
                limit: int = 15, min_score: float = 0.5):
        results = []
        if q:
            try:
                store = LoomStore(project)
                results = _services.find_related_requirements(
                    store, q, limit=limit, min_score=min_score,
                )
            except Exception as e:
                results = [{"error": f"{type(e).__name__}: {e}"}]
        return _render(
            request, "search.html",
            q=q or "",
            results=results,
            limit=limit,
            min_score=min_score,
            list_active="search",
        )

    # ------------------------------------------------------------------
    # M23.5 — JSON API mirrors
    # ------------------------------------------------------------------

    @app.get("/api/reqs")
    def api_reqs(kind: Optional[str] = None,
                  status: Optional[str] = None):
        store = LoomStore(project)
        reqs = list(store.list_requirements())
        if kind:
            reqs = [r for r in reqs if getattr(r, "kind", "requirement") == kind]
        if status:
            reqs = [r for r in reqs if (r.status or "pending") == status]
        return JSONResponse([r.to_dict() for r in reqs])

    @app.get("/api/reqs/{req_id}")
    def api_reqs_detail(req_id: str):
        store = LoomStore(project)
        req = store.get_requirement(req_id)
        if req is None:
            raise HTTPException(status_code=404, detail="not found")
        impls = [
            i.to_dict() for i in store.list_implementations()
            if any(s.get("req_id") == req_id for s in (i.satisfies or []))
        ]
        return JSONResponse({"requirement": req.to_dict(), "impls": impls})

    @app.get("/api/specs")
    def api_specs():
        store = LoomStore(project)
        try:
            specs = [s.to_dict() for s in store.list_specifications()]
        except AttributeError:
            specs = []
        return JSONResponse(specs)

    @app.get("/api/specs/{spec_id}")
    def api_specs_detail(spec_id: str):
        store = LoomStore(project)
        try:
            spec = store.get_specification(spec_id)
        except AttributeError:
            spec = None
        if spec is None:
            raise HTTPException(status_code=404, detail="not found")
        return JSONResponse(spec.to_dict())

    @app.get("/api/files")
    def api_files():
        store = LoomStore(project)
        by_file: dict[str, list] = {}
        for imp in store.list_implementations():
            if imp.file:
                by_file.setdefault(imp.file, []).append(imp.to_dict())
        return JSONResponse({
            f: {"impls": impls} for f, impls in by_file.items()
        })

    @app.get("/api/files/{path:path}")
    def api_files_detail(path: str):
        store = LoomStore(project)
        impls = [i.to_dict() for i in store.list_implementations()
                  if i.file == path]
        if not impls:
            raise HTTPException(status_code=404, detail="not found")
        try:
            drift = _services.check(store, path)
        except Exception:
            drift = None
        return JSONResponse({"path": path, "impls": impls, "drift": drift})

    @app.get("/api/search")
    def api_search(q: str, limit: int = 15, min_score: float = 0.5):
        if not q:
            raise HTTPException(status_code=400, detail="q required")
        store = LoomStore(project)
        try:
            results = _services.find_related_requirements(
                store, q, limit=limit, min_score=min_score,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
        return JSONResponse({"q": q, "results": results})

    # Expose the render helper for views added by later milestones.
    app.state.render = _render
    app.state.project = project

    return app


def _recent_commits_for(path: str, limit: int = 10) -> list[dict]:
    """git log --max-count=N -- <path> for the file detail view."""
    try:
        proc = subprocess.run(
            ["git", "log", f"--max-count={limit}",
             "--pretty=%H%x09%ci%x09%s", "--", path],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            shell=(sys.platform == "win32"),
            timeout=10,
        )
        if proc.returncode != 0:
            return []
        out = []
        for line in proc.stdout.splitlines():
            parts = line.split("\t", 2)
            if len(parts) == 3:
                out.append({
                    "hash": parts[0][:12],
                    "date": parts[1],
                    "subject": parts[2],
                })
        return out
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _recent_events(project: str, limit: int = 15) -> list[dict]:
    """Read the last N rows from ``.loom-events.jsonl`` for the project."""
    data_dir = Path.home() / ".openclaw" / "loom" / project
    log_path = data_dir / ".loom-events.jsonl"
    if not log_path.exists():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-(limit * 3):]):
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            out.append(ev)
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def run(project: str, host: str = "127.0.0.1", port: int = 8090,
        reload: bool = False) -> int:
    """Entrypoint called by ``loom ui`` CLI command."""
    _check_deps()
    import uvicorn  # local import — only loaded when running
    app = create_app(project)
    print(f"Loom UI for project={project!r}")
    print(f"  Serving on http://{host}:{port}")
    print(f"  Templates: {_TEMPLATES_DIR}")
    print()
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0
