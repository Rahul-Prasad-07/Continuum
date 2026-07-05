"""Cognee Cloud backend — the *complete* production path.

Talks to the hosted Cognee platform REST API (the tenant URL + `X-Api-Key`). Every checkpoint
runs Cognee's full managed pipeline — **ingest → knowledge graph → embeddings/vector index** —
and retrieval can use Cognee's **GRAPH_COMPLETION** (an answer synthesized from the knowledge
graph) as well as raw semantic **CHUNKS**. Because the platform runs the LLM + embeddings for
you, **no local OpenAI key is required** for the Cognee side.

Continuum keeps a local SQLite sidecar for the things Cognee doesn't model: the reasoning graph,
workspace snapshots, and a verbatim mirror (so export/import and the reasoning layer always work,
and so we degrade gracefully if the network/API is down).

This is what makes Continuum a true superset of Cognee: everything Cognee does (here, via the
managed platform) **plus** the reasoning-state layer.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from continuum._logging import get_logger
from continuum.memory.base import Chunk
from continuum.memory.local_backend import LocalBackend
from continuum.models import ReasoningGraph, WorkspaceState

log = get_logger(__name__)


def _safe_ds(name: str) -> str:
    """Cognee dataset names must be simple; map `user::project` → `continuum-user-project`."""
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower() or "default"


class CogneeCloudBackend:
    """MemoryBackend backed by the hosted Cognee platform (REST). Defensive: any API failure
    falls back to the local sidecar so a checkpoint/resume never hard-fails."""

    def __init__(
        self,
        db_path: str | Path,
        dataset: str = "continuum",
        api_url: str = "",
        api_key: str = "",
        run_cognify_in_background: bool = True,
        **_ignore,
    ):
        self._local = LocalBackend(db_path)
        self._dataset = dataset
        self._url = (api_url or "").rstrip("/")
        self._key = api_key or ""
        self._bg = run_cognify_in_background
        self._live = bool(self._url and self._key)

    # ---- REST helper ---------------------------------------------------------
    def _post(self, path: str, payload: dict, timeout: int = 120):
        req = urllib.request.Request(
            self._url + path,
            data=json.dumps(payload).encode(),
            method="POST",
            headers={"X-Api-Key": self._key, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode() or "null")

    def _ds(self, project: str) -> str:
        return _safe_ds(f"{self._dataset}-{project}")

    # ---- verbatim + ingestion (the full Cognee pipeline) ---------------------
    def add_verbatim(self, project: str, chunks: list[Chunk]) -> None:
        self._local.add_verbatim(project, chunks)  # always mirror locally (source of truth)
        if not self._live or not chunks:
            return
        ds = self._ds(project)
        try:
            texts = [c.text for c in chunks]
            self._post("/api/v1/add_text", {"textData": texts, "datasetName": ds})
            # Build the knowledge graph. Background = fast checkpoints; the KG is ready shortly.
            self._post("/api/v1/cognify", {"datasets": [ds], "runInBackground": self._bg})
        except Exception as e:  # noqa: BLE001 — never block a checkpoint on the network
            log.warning("cognee_cloud add/cognify failed (%s); local mirror holds", e)

    def search_verbatim(self, project: str, query: str, k: int = 6) -> list[Chunk]:
        if self._live and query.strip():
            try:
                res = self._post(
                    "/api/v1/search",
                    {"searchType": "CHUNKS", "datasets": [self._ds(project)],
                     "query": query, "topK": k},
                )
                chunks = _chunks_from_search(res, project, k)
                if chunks:
                    return chunks
            except Exception as e:  # noqa: BLE001
                log.warning("cognee_cloud CHUNKS search failed (%s); local fallback", e)
        return self._local.search_verbatim(project, query, k)

    def graph_answer(self, project: str, query: str) -> Optional[str]:
        """Point #1: use the KNOWLEDGE graph in resume — a synthesized GRAPH_COMPLETION answer."""
        if not (self._live and query.strip()):
            return None
        try:
            res = self._post(
                "/api/v1/search",
                {"searchType": "GRAPH_COMPLETION", "datasets": [self._ds(project)],
                 "query": query, "topK": 10},
                timeout=90,
            )
            return _answer_from_search(res)
        except Exception as e:  # noqa: BLE001
            log.warning("cognee_cloud GRAPH_COMPLETION failed (%s)", e)
            return None

    # ---- structured sidecar (reasoning + workspace + verbatim reads) ----------
    def get_chunk(self, project: str, chunk_id: str) -> Optional[Chunk]:
        return self._local.get_chunk(project, chunk_id)

    def all_chunks(self, project: str) -> list[Chunk]:
        return self._local.all_chunks(project)

    def store_workspace(self, project: str, ws: WorkspaceState) -> None:
        self._local.store_workspace(project, ws)

    def latest_workspace(self, project: str) -> Optional[WorkspaceState]:
        return self._local.latest_workspace(project)

    def list_workspaces(self, project: str) -> list[WorkspaceState]:
        return self._local.list_workspaces(project)

    def store_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        self._local.store_reasoning(project, graph)

    def replace_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        self._local.replace_reasoning(project, graph)

    def get_reasoning(self, project: str) -> ReasoningGraph:
        return self._local.get_reasoning(project)

    def list_projects(self) -> list[str]:
        return self._local.list_projects()

    def delete_project(self, project: str) -> dict:
        counts = self._local.delete_project(project)
        if self._live:
            try:
                self._post("/api/v1/forget", {"dataset": self._ds(project), "everything": True})
            except Exception as e:  # noqa: BLE001
                log.warning("cognee_cloud forget failed (%s)", e)
        return counts

    def capabilities(self) -> dict:
        return {
            "backend": "cognee_cloud",
            "connected": self._live,
            "verbatim": True,
            "reasoning_graph": True,
            "knowledge_graph": self._live,
            "semantic_retrieval": self._live,
            "managed_llm": self._live,  # Cognee platform runs the LLM + embeddings
        }


# ---- response parsers (the platform wraps results per-dataset) ---------------
def _iter_results(res) -> list:
    """The search response is a list of {dataset_…, search_result: [...]}. Flatten search_result."""
    out = []
    if isinstance(res, list):
        for item in res:
            if isinstance(item, dict) and "search_result" in item:
                out.extend(item.get("search_result") or [])
            else:
                out.append(item)
    elif isinstance(res, dict) and "search_result" in res:
        out.extend(res.get("search_result") or [])
    return out


def _chunks_from_search(res, project: str, k: int) -> list[Chunk]:
    chunks = []
    for r in _iter_results(res)[:k]:
        text = r.get("text") if isinstance(r, dict) else str(r)
        if text:
            chunks.append(Chunk(project=project, text=str(text)).with_id())
    return chunks


def _answer_from_search(res) -> Optional[str]:
    parts = [str(r) for r in _iter_results(res) if r]
    ans = "\n".join(p for p in parts if p).strip()
    return ans or None
