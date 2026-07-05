"""HTTP API surface (FastAPI).

The backbone every non-CLI surface talks to: browser extension, web dashboard, integrations.
Endpoints mirror the engine: checkpoint / resume / status. Plain JSON in/out; the resume
package is plain text so it drops into any provider.

Run: `continuum serve`  (or `uvicorn continuum.surfaces.api:app`).
"""

from __future__ import annotations

import os
from typing import Optional

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "The API surface needs FastAPI: pip install 'continuum[api]'"
    ) from e


def _auth(authorization: Optional[str] = Header(default=None)) -> None:
    """Require `Authorization: Bearer <CONTINUUM_TOKEN>` when a token is configured."""
    token = os.getenv("CONTINUUM_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "unauthorized")

from continuum import __version__
from continuum.config import Config
from continuum.engine import Continuum

app = FastAPI(title="Continuum", version=__version__, description="Reasoning-state continuity API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten per-deployment; browser ext needs cross-origin
    allow_methods=["*"],
    allow_headers=["*"],
)

# Multi-tenant: one engine per user (isolated memory). Users identify via the
# `X-Continuum-User` header; absent = "default". This is what makes the cloud serve any user.
_engines: dict[str, Continuum] = {}


def _user(x_continuum_user: Optional[str] = Header(default=None)) -> str:
    return x_continuum_user or "default"


def engine(user: str = "default") -> Continuum:
    if user not in _engines:
        _engines[user] = Continuum(Config(user=user))
    return _engines[user]


class CheckpointReq(BaseModel):
    project: str
    text: str


class IngestReq(BaseModel):
    project: str
    text: str


class ResumeReq(BaseModel):
    project: str
    intent: str = ""
    budget_tokens: Optional[int] = None


class ImportReq(BaseModel):
    bundle: dict


class ContextReq(BaseModel):
    text: str = ""
    model: str = ""
    window: int = 0


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__, "mode": engine().llm.available() and "llm" or "heuristic"}


@app.post("/checkpoint")
def checkpoint(req: CheckpointReq, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    if not req.text.strip():
        raise HTTPException(400, "empty text")
    ws = engine(user).checkpoint(req.project, req.text)
    return {
        "checkpoint_id": ws.checkpoint_id,
        "project": req.project,
        "decisions": len(ws.decisions),
        "goal": ws.goal,
    }


@app.post("/resume")
def resume(req: ResumeReq, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    pkg = engine(user).resume(req.project, intent=req.intent, budget_tokens=req.budget_tokens)
    return {"project": req.project, "resume_package": pkg}


@app.post("/ingest")
def ingest(req: IngestReq, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    if not req.text.strip():
        raise HTTPException(400, "empty text")
    return engine(user).ingest(req.project, req.text)


@app.get("/status/{project}")
def status(project: str, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return engine(user).status(project)


@app.get("/mode")
def mode(user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return engine(user).mode()


@app.get("/projects")
def projects(user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"projects": engine(user).list_projects()}


@app.delete("/projects/{project}")
def forget(project: str, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "removed": engine(user).forget(project)}


@app.post("/improve/{project}")
def improve(project: str, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "stats": engine(user).improve(project)}


@app.post("/prune/{project}")
def prune(project: str, keep: int = 60, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "stats": engine(user).prune(project, keep=keep)}


@app.post("/distill/{project}")
def distill(project: str, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "lessons": engine(user).distill(project)}


@app.get("/lessons")
def lessons(user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"lessons": engine(user).lessons()}


@app.get("/timeline/{project}")
def timeline(project: str, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "timeline": engine(user).timeline(project)}


@app.get("/export/{project}")
def export(project: str, format: str = "json", user: str = Depends(_user), _=Depends(_auth)):
    """Export a project. format=json → lossless bundle; format=md → paste-anywhere document."""
    data = engine(user).export(project, fmt="md" if format == "md" else "json")
    if isinstance(data, str):
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(data)
    return data


@app.post("/import/{project}")
def import_project(project: str, req: ImportReq, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return {"project": project, "stats": engine(user).import_project(project, req.bundle)}


@app.post("/context/{project}")
def context(project: str, req: ContextReq, user: str = Depends(_user), _=Depends(_auth)) -> dict:
    return engine(user).context(project, live_text=req.text, model=req.model, window=req.window)


def serve(host: str = "127.0.0.1", port: int = 8770) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port)
