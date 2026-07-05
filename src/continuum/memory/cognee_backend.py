"""Cognee backend (production).

Delegates the hard parts to Cognee — verbatim storage + **semantic** retrieval (and, on the
roadmap, `cognify(graph_model=ReasoningGraph)` for a real reasoning graph). Workspace snapshots
and the merged reasoning graph are kept in a local SQLite sidecar for fast, structured access.

Defensive by design: any Cognee error (e.g. no LLM key configured) falls back to the local
keyword retrieval, so the product never hard-fails on a memory read.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from continuum.memory.base import Chunk
from continuum.memory.local_backend import LocalBackend
from continuum.models import ReasoningGraph, WorkspaceState


class CogneeBackend:
    """MemoryBackend backed by Cognee for semantic verbatim retrieval."""

    def __init__(self, db_path: str | Path, dataset: str = "continuum", cognee_reasoning: bool = True):
        # Sidecar keeps verbatim mirror + workspace + reasoning (fast, structured).
        self._local = LocalBackend(db_path)
        self._dataset = dataset
        self._cognee_reasoning = cognee_reasoning
        try:
            import cognee  # noqa: F401

            self._cognee = cognee
        except Exception:
            self._cognee = None

    def _run(self, coro):
        try:
            return asyncio.run(coro)
        except RuntimeError:  # already in a loop
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    # ---- verbatim ----
    def add_verbatim(self, project: str, chunks: list[Chunk]) -> None:
        self._local.add_verbatim(project, chunks)  # always mirror locally
        if self._cognee:
            ds = f"{self._dataset}:{project}"  # project is user-scoped by the engine → tenant isolation
            try:
                text = "\n\n".join(c.text for c in chunks)
                self._run(self._cognee.add(text, dataset_name=ds))
                # Default cognify = the KNOWLEDGE graph (entities/relations).
                self._run(self._cognee.cognify(datasets=[ds]))
                # Optional: let Cognee's LLM also extract a REASONING graph with our schema
                # (cognify with a custom graph_model). Best-effort enrichment — our own
                # extractor remains the primary, controllable path.
                if self._cognee_reasoning:
                    try:
                        from continuum.models import ReasoningGraph

                        self._run(
                            self._cognee.cognify(datasets=[ds], graph_model=ReasoningGraph)
                        )
                    except Exception:
                        pass
            except Exception:
                pass  # local mirror still holds the truth

    def search_verbatim(self, project: str, query: str, k: int = 6) -> list[Chunk]:
        if self._cognee:
            try:
                from cognee import SearchType

                results = self._run(
                    self._cognee.search(
                        query_text=query,
                        query_type=SearchType.CHUNKS,
                        datasets=[f"{self._dataset}:{project}"],
                    )
                )
                chunks = [
                    Chunk(project=project, text=str(r)).with_id() for r in (results or [])[:k]
                ]
                if chunks:
                    return chunks
            except Exception:
                pass
        return self._local.search_verbatim(project, query, k)  # graceful fallback

    def get_chunk(self, project: str, chunk_id: str) -> Optional[Chunk]:
        return self._local.get_chunk(project, chunk_id)

    def all_chunks(self, project: str) -> list[Chunk]:
        return self._local.all_chunks(project)

    # ---- workspace + reasoning (structured sidecar) ----
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

    def graph_answer(self, project: str, query: str) -> Optional[str]:
        """Answer from the knowledge graph via the local SDK (GRAPH_COMPLETION), best-effort."""
        if self._cognee and query.strip():
            try:
                from cognee import SearchType

                res = self._run(
                    self._cognee.search(
                        query_text=query,
                        query_type=SearchType.GRAPH_COMPLETION,
                        datasets=[f"{self._dataset}:{project}"],
                    )
                )
                if res:
                    return "\n".join(str(r) for r in res).strip() or None
            except Exception:
                pass
        return None

    def capabilities(self) -> dict:
        return {
            "backend": "cognee",
            "connected": self._cognee is not None,
            "verbatim": True,
            "reasoning_graph": True,
            "knowledge_graph": self._cognee is not None,
            "semantic_retrieval": self._cognee is not None,
            "managed_llm": False,  # local SDK uses YOUR configured LLM key
        }

    def list_projects(self) -> list[str]:
        return self._local.list_projects()

    def delete_project(self, project: str) -> dict:
        counts = self._local.delete_project(project)
        if self._cognee:
            try:  # best-effort cascade delete in Cognee
                self._run(self._cognee.prune.prune_data(dataset=f"{self._dataset}:{project}"))
            except Exception:
                pass
        return counts
