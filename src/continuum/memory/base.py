"""Memory backend port (ports-and-adapters).

The engine talks only to `MemoryBackend`. Concrete adapters (local SQLite, Cognee) plug in
behind it, so we run with zero services today and swap to Cognee for production without
touching the engine.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from continuum.models import ReasoningGraph, WorkspaceState


class Chunk(BaseModel):
    """A verbatim slice of conversation — the source of truth (never lossy)."""

    id: str = ""
    project: str
    text: str
    index: int = 0

    def with_id(self) -> "Chunk":
        if not self.id:
            digest = hashlib.sha256(f"{self.project}:{self.text}".encode()).hexdigest()[:16]
            self.id = f"ck-{digest}"
        return self


@runtime_checkable
class MemoryBackend(Protocol):
    """Storage + retrieval contract. Implemented by LocalBackend and CogneeBackend."""

    def add_verbatim(self, project: str, chunks: list[Chunk]) -> None:
        """Persist verbatim chunks (idempotent by content-addressed id)."""

    def store_workspace(self, project: str, ws: WorkspaceState) -> None:
        """Persist a workspace snapshot."""

    def store_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        """Merge a reasoning graph into the project's stored graph."""

    def replace_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        """Overwrite the project's reasoning graph (used by improve/prune, which shrink it)."""

    def latest_workspace(self, project: str) -> Optional[WorkspaceState]:
        """Most recent workspace snapshot, or None."""

    def list_workspaces(self, project: str) -> list[WorkspaceState]:
        """All workspace snapshots oldest→newest (the temporal timeline of the thinking)."""

    def search_verbatim(self, project: str, query: str, k: int = 6) -> list[Chunk]:
        """Return the k most relevant verbatim chunks for a query."""

    def get_chunk(self, project: str, chunk_id: str) -> Optional[Chunk]:
        """Fetch a specific verbatim chunk by id (for hybrid resume)."""

    def all_chunks(self, project: str) -> list[Chunk]:
        """Every verbatim chunk for a project, in original order (for export/portability)."""

    def get_reasoning(self, project: str) -> ReasoningGraph:
        """The project's accumulated reasoning graph."""

    def graph_answer(self, project: str, query: str) -> Optional[str]:
        """A synthesized answer from the KNOWLEDGE graph (Cognee GRAPH_COMPLETION), or None if
        the backend has no knowledge graph (e.g. the local keyword backend). Used to enrich resume."""

    def capabilities(self) -> dict:
        """What this backend can do — knowledge_graph / semantic_retrieval / managed_llm — so
        surfaces can show the user which storage layers are actually active."""

    def list_projects(self) -> list[str]:
        """All project names that have any stored state."""

    def delete_project(self, project: str) -> dict:
        """Forget everything for a project. Returns counts of what was removed."""
