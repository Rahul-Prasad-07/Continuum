"""Local SQLite backend — zero external services, runs anywhere.

Verbatim chunks in an FTS5 table (keyword retrieval), workspace snapshots and the reasoning
graph as JSON. This makes Continuum demoable with only pydantic+click installed. The Cognee
backend swaps in for production semantic + graph retrieval.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

from continuum.memory.base import Chunk
from continuum.models import ReasoningGraph, WorkspaceState


def _has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


class LocalBackend:
    """SQLite-backed MemoryBackend. Retrieval = FTS5 keyword search (or LIKE fallback)."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: the HTTP API serves sync handlers from a threadpool, so the
        # connection may be touched from different threads. Our writes commit immediately and
        # concurrency is low, so this is safe here.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._fts = _has_fts5(self.conn)
        self._init_schema()

    def _init_schema(self) -> None:
        c = self.conn
        c.execute(
            "CREATE TABLE IF NOT EXISTS chunks "
            "(id TEXT PRIMARY KEY, project TEXT, idx INTEGER, text TEXT)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS ix_chunks_project ON chunks(project)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS workspaces "
            "(checkpoint_id TEXT PRIMARY KEY, project TEXT, ts REAL, json TEXT)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS ix_ws_project ON workspaces(project, ts)")
        c.execute(
            "CREATE TABLE IF NOT EXISTS reasoning (project TEXT PRIMARY KEY, json TEXT)"
        )
        if self._fts:
            c.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts "
                "USING fts5(id UNINDEXED, project UNINDEXED, text)"
            )
        c.commit()

    # ---- verbatim (source of truth) ----
    def add_verbatim(self, project: str, chunks: list[Chunk]) -> None:
        for ch in chunks:
            ch = ch.with_id()
            self.conn.execute(
                "INSERT OR IGNORE INTO chunks(id, project, idx, text) VALUES (?,?,?,?)",
                (ch.id, project, ch.index, ch.text),
            )
            if self._fts:
                self.conn.execute(
                    "INSERT INTO chunks_fts(id, project, text) VALUES (?,?,?)",
                    (ch.id, project, ch.text),
                )
        self.conn.commit()

    def search_verbatim(self, project: str, query: str, k: int = 6) -> list[Chunk]:
        rows = []
        if self._fts and query.strip():
            terms = " OR ".join(w for w in _keywords(query))
            if terms:
                try:
                    rows = self.conn.execute(
                        "SELECT c.id, c.project, c.idx, c.text FROM chunks_fts f "
                        "JOIN chunks c ON c.id=f.id "
                        "WHERE f.project=? AND chunks_fts MATCH ? LIMIT ?",
                        (project, terms, k),
                    ).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:  # LIKE fallback / empty query
            like = f"%{_keywords(query)[0]}%" if _keywords(query) else "%"
            rows = self.conn.execute(
                "SELECT id, project, idx, text FROM chunks WHERE project=? AND text LIKE ? "
                "LIMIT ?",
                (project, like, k),
            ).fetchall()
        return [Chunk(id=r["id"], project=r["project"], index=r["idx"], text=r["text"]) for r in rows]

    def get_chunk(self, project: str, chunk_id: str) -> Optional[Chunk]:
        r = self.conn.execute(
            "SELECT id, project, idx, text FROM chunks WHERE project=? AND id=?",
            (project, chunk_id),
        ).fetchone()
        return Chunk(id=r["id"], project=r["project"], index=r["idx"], text=r["text"]) if r else None

    def all_chunks(self, project: str) -> list[Chunk]:
        rows = self.conn.execute(
            "SELECT id, project, idx, text FROM chunks WHERE project=? ORDER BY idx ASC",
            (project,),
        ).fetchall()
        return [
            Chunk(id=r["id"], project=r["project"], index=r["idx"], text=r["text"]) for r in rows
        ]

    # ---- workspace snapshots ----
    def store_workspace(self, project: str, ws: WorkspaceState) -> None:
        ws = ws.with_id()
        self.conn.execute(
            "INSERT OR REPLACE INTO workspaces(checkpoint_id, project, ts, json) VALUES (?,?,?,?)",
            (ws.checkpoint_id, project, ws.timestamp, ws.model_dump_json()),
        )
        self.conn.commit()

    def latest_workspace(self, project: str) -> Optional[WorkspaceState]:
        r = self.conn.execute(
            "SELECT json FROM workspaces WHERE project=? ORDER BY ts DESC LIMIT 1", (project,)
        ).fetchone()
        return WorkspaceState.model_validate_json(r["json"]) if r else None

    def list_workspaces(self, project: str) -> list[WorkspaceState]:
        rows = self.conn.execute(
            "SELECT json FROM workspaces WHERE project=? ORDER BY ts ASC", (project,)
        ).fetchall()
        return [WorkspaceState.model_validate_json(r["json"]) for r in rows]

    # ---- reasoning graph (accumulated, merged) ----
    def store_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        existing = self.get_reasoning(project)
        merged = existing.merge(graph)
        self.conn.execute(
            "INSERT OR REPLACE INTO reasoning(project, json) VALUES (?,?)",
            (project, merged.model_dump_json()),
        )
        self.conn.commit()

    def replace_reasoning(self, project: str, graph: ReasoningGraph) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO reasoning(project, json) VALUES (?,?)",
            (project, graph.model_dump_json()),
        )
        self.conn.commit()

    def get_reasoning(self, project: str) -> ReasoningGraph:
        r = self.conn.execute(
            "SELECT json FROM reasoning WHERE project=?", (project,)
        ).fetchone()
        return ReasoningGraph.model_validate_json(r["json"]) if r else ReasoningGraph()

    def graph_answer(self, project: str, query: str) -> Optional[str]:
        return None  # local backend is keyword + reasoning only — no knowledge graph

    def capabilities(self) -> dict:
        return {
            "backend": "local",
            "verbatim": True,
            "reasoning_graph": True,
            "knowledge_graph": False,
            "semantic_retrieval": False,  # FTS5 keyword only
            "managed_llm": False,
        }

    # ---- project management ----
    def list_projects(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT project FROM workspaces UNION SELECT project FROM chunks ORDER BY 1"
        ).fetchall()
        return [r["project"] for r in rows]

    def delete_project(self, project: str) -> dict:
        counts = {}
        for table in ("chunks", "workspaces", "reasoning"):
            cur = self.conn.execute(f"DELETE FROM {table} WHERE project=?", (project,))
            counts[table] = cur.rowcount
        if self._fts:
            self.conn.execute("DELETE FROM chunks_fts WHERE project=?", (project,))
        self.conn.commit()
        return counts


_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "we", "i"}


def _keywords(text: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split()
            if len(w) > 2 and w not in _STOP]
