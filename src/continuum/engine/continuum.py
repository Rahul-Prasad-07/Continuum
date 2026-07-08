"""Continuum orchestrator — the public engine: checkpoint / resume / improve / distill / prune.

Multi-tenant: every operation is scoped to a `user` (from Config), so one deployment serves
many users with fully isolated memory (the "any user" requirement). Isolation is by scoping the
project key — which also scopes the Cognee dataset per user.
"""

from __future__ import annotations

from typing import Optional

from continuum._logging import get_logger
from continuum.config import Config
from continuum.engine.composer import compose_recall, compose_resume
from continuum.engine.extractor import chunk_conversation, extract
from continuum.engine.meter import context_report, render_gauge, window_for
from continuum.engine.portable import (
    export_bundle,
    export_digest,
    export_markdown,
    export_transcript,
    import_bundle,
)
from continuum.engine.refine import (
    build_timeline,
    distill_lessons,
    improve_graph,
    lessons_to_graph,
    prune_graph,
)
from continuum.llm import LLMClient
from continuum.memory import MemoryBackend, get_backend
from continuum.models import WorkspaceState

log = get_logger(__name__)

_LESSONS = "__lessons__"  # reserved per-user project holding cross-project distilled insights


class Continuum:
    """The reasoning-state continuity engine. Backed by a MemoryBackend + an LLMClient."""

    def __init__(self, config: Optional[Config] = None, backend: Optional[MemoryBackend] = None):
        self.config = (config or Config()).ensure_home()
        self.user = self.config.user or "default"
        self.backend = backend or get_backend(
            self.config.backend,
            self.config.db_path,
            dataset=self.config.dataset,
            cognee_reasoning=self.config.cognee_reasoning,
            api_url=self.config.cognee_api_url,
            api_key=self.config.cognee_api_key,
        )
        self.llm = LLMClient()

    # ---- multi-tenant scoping -------------------------------------------------
    def _scope(self, project: str) -> str:
        """Namespace a project by user. Default user keeps bare names (backward compatible)."""
        return project if self.user == "default" else f"{self.user}::{project}"

    def _unscope(self, scoped: str) -> str:
        prefix = f"{self.user}::"
        return scoped[len(prefix):] if scoped.startswith(prefix) else scoped

    # ---- core: checkpoint / resume -------------------------------------------
    def checkpoint(self, project: str, conversation_text: str) -> WorkspaceState:
        """Capture in flight: store verbatim, extract reasoning-state, persist both."""
        sp = self._scope(project)
        chunks = chunk_conversation(conversation_text, sp)
        self.backend.add_verbatim(sp, chunks)  # verbatim = source of truth
        ws, graph = extract(conversation_text, sp, chunks, self.llm)
        self.backend.store_workspace(sp, ws)
        self.backend.store_reasoning(sp, graph)  # reasoning graph = index (merged)
        log.info(
            "checkpoint user=%s project=%s id=%s chunks=%d decisions=%d nodes=%d",
            self.user, project, ws.checkpoint_id, len(chunks), len(ws.decisions), len(graph.nodes),
        )
        return ws

    def resume(self, project: str, intent: str = "", budget_tokens: Optional[int] = None) -> str:
        """Reconstruct a compact, provider-agnostic resume package (plain text)."""
        return compose_resume(
            self.backend,
            self._scope(project),
            intent,
            budget_tokens or self.config.resume_budget_tokens,
        )

    def recall(self, project: str, subject: str, budget_tokens: Optional[int] = None) -> str:
        """Resume by SUBJECT across the whole project history — gather every checkpoint about
        `subject` (a topic or an intent), not just the latest. Solves "I worked on X weeks ago
        but the latest checkpoint is about something else." Uses semantic retrieval on the Cognee
        backends and keyword/topic matching everywhere."""
        return compose_recall(
            self.backend,
            self._scope(project),
            subject,
            budget_tokens or self.config.resume_budget_tokens,
        )

    # ---- new layers: improve / distill / prune / timeline --------------------
    def improve(self, project: str) -> dict:
        """memify: self-improve the reasoning graph (dedup nodes, drop dangling edges, mark
        superseded decisions resolved)."""
        sp = self._scope(project)
        graph = self.backend.get_reasoning(sp)
        improved, stats = improve_graph(graph)
        self.backend.replace_reasoning(sp, improved)
        log.info("improve user=%s project=%s %s", self.user, project, stats)
        return stats

    def prune(self, project: str, keep: int = 60, min_score: float = 0.5) -> dict:
        """Active forgetting: trim the reasoning index to the most-salient nodes (verbatim
        source is never deleted — only the index shrinks, keeping resume packages bounded)."""
        sp = self._scope(project)
        graph = self.backend.get_reasoning(sp)
        pruned, stats = prune_graph(graph, keep=keep, min_score=min_score)
        self.backend.replace_reasoning(sp, pruned)
        log.info("prune user=%s project=%s %s", self.user, project, stats)
        return stats

    def distill(self, project: str) -> list[str]:
        """Harvest durable lessons from a project and store them in the user's cross-project
        lessons memory (reusable by any future project)."""
        sp = self._scope(project)
        graph = self.backend.get_reasoning(sp)
        ws = self.backend.latest_workspace(sp)
        lessons = distill_lessons(graph, ws)
        if lessons:
            self.backend.store_reasoning(self._scope(_LESSONS), lessons_to_graph(lessons))
        log.info("distill user=%s project=%s lessons=%d", self.user, project, len(lessons))
        return lessons

    def lessons(self) -> list[str]:
        """The user's accumulated cross-project lessons (distilled insights)."""
        graph = self.backend.get_reasoning(self._scope(_LESSONS))
        return [n.description or n.name for n in graph.nodes]

    def timeline(self, project: str) -> list[dict]:
        """The temporal evolution of the thinking — one row per checkpoint, oldest→newest."""
        return build_timeline(self.backend.list_workspaces(self._scope(project)))

    # ---- capture from another tool's native session (cross-platform switch) ---
    def capture(self, project: str, path: Optional[str] = None, source: str = "auto") -> dict:
        """Import a conversation directly from another AI tool's on-disk session (Grok / Claude
        Code / Codex / generic), normalize it, and checkpoint it — zero copy-paste. If `path` is
        omitted, uses the most recent session for `source`."""
        from continuum import adapters

        if not path:
            if source in ("auto", "", None):
                raise ValueError("give a --source (grok/claude_code/codex) to auto-find the latest session")
            path = adapters.latest_session(source)
            if not path:
                raise FileNotFoundError(f"no {source} sessions found on this machine")
        text = adapters.parse_file(path, source)
        if not text.strip():
            raise ValueError(f"no user/assistant messages parsed from {path}")
        ws = self.checkpoint(project, text)
        turns = text.count("\n\n") + 1
        log.info("capture user=%s project=%s source=%s turns=%d", self.user, project, source, turns)
        return {
            "project": project, "source": source, "path": str(path), "turns": turns,
            "checkpoint_id": ws.checkpoint_id, "decisions": len(ws.decisions),
        }

    # ---- portability: export / import (save & switch platforms) --------------
    def export(
        self,
        project: str,
        fmt: str = "json",
        max_tokens: Optional[int] = None,
        since: Optional[float] = None,
    ):
        """Export a project.
        fmt='json'       → lossless bundle (supports `since` for an incremental delta).
        fmt='md'         → paste-anywhere reasoning-state doc (supports `max_tokens`, `since`).
        fmt='digest'     → hierarchical compression (recent full, older summarized) for long work.
        fmt='transcript' → clean full conversation (grok-style).
        """
        sp = self._scope(project)
        if fmt == "md":
            return export_markdown(self.backend, sp, project, max_tokens=max_tokens, since=since)
        if fmt == "digest":
            return export_digest(self.backend, sp, project,
                                 budget_tokens=max_tokens or 6000)
        if fmt == "transcript":
            return export_transcript(self.backend, sp, project)
        return export_bundle(self.backend, sp, project, since=since)

    def import_project(self, project: str, data: dict) -> dict:
        """Import a previously-exported bundle into `project` (this user's scope)."""
        stats = import_bundle(self.backend, self._scope(project), data)
        log.info("import user=%s project=%s %s", self.user, project, stats)
        return stats

    # ---- context-window strength meter ---------------------------------------
    def context(self, project: str, live_text: str = "", model: str = "", window: int = 0) -> dict:
        """Gauge live-conversation safety: window fill, uncaptured drift, and a strength score
        with a checkpoint recommendation. Pass the current transcript as `live_text`."""
        win = window or window_for(model)
        return context_report(self.backend, self._scope(project), project, live_text, win)

    # ---- autopilot: watch the window, auto-hand you a portable export at the threshold --------
    def autopilot(
        self, project: str, live_text: str = "", model: str = "", threshold_pct: int = 80
    ) -> dict:
        """One call that (1) gauges context health and (2), when the window crosses `threshold_pct`
        (or nothing is captured yet), returns a ready-to-paste export so you can switch to a fresh
        tab / another provider before reasoning-state is lost. This is the buildable core of the
        "auto-export at 80%" ask — surfaces (dashboard bar, MCP tool) trigger on `switch_now`."""
        report = self.context(project, live_text=live_text, model=model)
        window_over = report["window_used_pct"] >= threshold_pct
        over = window_over or report["action"] == "checkpoint_now"
        if not over:
            reason = ""
        elif window_over:
            reason = f"context window ≥ {threshold_pct}% ({report['window_used_pct']}%)"
        elif not report["captured"]:
            reason = "nothing checkpointed yet"
        else:
            reason = f"{report['unsaved_pct']}% of this chat is uncaptured (drift)"
        result = {
            "project": project,
            "threshold_pct": threshold_pct,
            "window_used_pct": report["window_used_pct"],
            "zone": report["zone"],
            "strength": report["strength"],
            "switch_now": bool(over),
            "reason": reason,
            "gauge": render_gauge(report),
            "recommendation": report["recommendation"],
            "export": None,
        }
        if over:
            result["export"] = export_markdown(
                self.backend, self._scope(project), project, max_tokens=6000
            )
        return result

    # ---- session auto-capture: buffer each turn, checkpoint automatically at a threshold -----
    def observe(
        self, project: str, turn_text: str, flush_tokens: int = 6000, force: bool = False
    ) -> dict:
        """Append one conversation turn to a rolling session buffer and auto-checkpoint when the
        buffer grows past `flush_tokens` (or `force=True`). Call this every turn to save a whole
        session with no explicit "save" — the buffer persists under CONTINUUM_HOME so it survives
        across calls within a session. Returns whether a checkpoint fired."""
        buf_path = self._buffer_path(project)
        prior = buf_path.read_text() if buf_path.exists() else ""
        buffer = (prior + "\n\n" + turn_text).strip() if prior else turn_text.strip()
        tokens = max(1, len(buffer) // 4)

        if force or tokens >= flush_tokens:
            ws = self.checkpoint(project, buffer)
            buf_path.write_text("")  # clear the buffer after a successful checkpoint
            return {
                "project": project, "checkpointed": True, "checkpoint_id": ws.checkpoint_id,
                "decisions": len(ws.decisions), "buffered_tokens": 0,
            }
        buf_path.write_text(buffer)
        return {
            "project": project, "checkpointed": False, "buffered_tokens": tokens,
            "flush_at": flush_tokens,
        }

    def _buffer_path(self, project: str):
        from pathlib import Path
        d = Path(self.config.db_path).parent / "buffers"
        d.mkdir(parents=True, exist_ok=True)
        safe = self._scope(project).replace("::", "__").replace("/", "_")
        return d / f"{safe}.txt"

    # ---- hook-driven autosave: read the live session file, checkpoint on real growth -----------
    def autosave(
        self,
        project: str,
        source: str = "claude_code",
        path: Optional[str] = None,
        min_new_tokens: int = 1500,
    ) -> dict:
        """Read the CURRENT session transcript straight from the tool's on-disk store and
        checkpoint it — but only when it has grown by `min_new_tokens` since the last autosave
        (debounced, so a Stop/after-turn hook can fire every turn without spamming checkpoints).

        This is the *genuinely automatic* path: a client hook (e.g. Claude Code's Stop hook) calls
        this after every turn; no model cooperation needed. Returns whether a checkpoint fired."""
        from continuum import adapters

        p = path or adapters.latest_session(source)
        if not p:
            return {"saved": False, "reason": f"no {source} session found"}
        text = adapters.parse_file(p, source)
        if not text.strip():
            return {"saved": False, "reason": "empty transcript"}

        toks = max(1, len(text) // 4)
        marker = self._autosave_marker(project)
        last = 0
        if marker.exists():
            try:
                last = int(marker.read_text().strip() or "0")
            except ValueError:
                last = 0
        if toks - last < min_new_tokens:
            return {"saved": False, "new_tokens": max(0, toks - last),
                    "min_new_tokens": min_new_tokens, "session_tokens": toks}

        ws = self.checkpoint(project, text)
        marker.write_text(str(toks))
        return {"saved": True, "project": project, "checkpoint_id": ws.checkpoint_id,
                "decisions": len(ws.decisions), "session_tokens": toks, "source": source}

    def _autosave_marker(self, project: str):
        from pathlib import Path
        d = Path(self.config.db_path).parent / "buffers"
        d.mkdir(parents=True, exist_ok=True)
        safe = self._scope(project).replace("::", "__").replace("/", "_")
        return d / f"{safe}.autosave"

    # ---- ingest reference docs (knowledge, not a conversation) ----------------
    def ingest(self, project: str, text: str, source: str = "doc") -> dict:
        """Add reference material (docs/notes) as knowledge — stored verbatim and, on the Cognee
        backends, run through the full ingest→knowledge-graph pipeline. Unlike `checkpoint`, this
        does NOT extract reasoning-state (it's source knowledge, not a conversation)."""
        sp = self._scope(project)
        chunks = chunk_conversation(text, sp)
        self.backend.add_verbatim(sp, chunks)
        log.info("ingest user=%s project=%s source=%s chunks=%d", self.user, project, source, len(chunks))
        return {"project": project, "chunks": len(chunks), "backend": self.config.backend}

    # ---- which storage layers are actually active ----------------------------
    def mode(self) -> dict:
        """Report the live backend's capabilities (knowledge graph / semantic retrieval / managed
        LLM) so a user can see exactly what a checkpoint stores right now."""
        try:
            caps = dict(self.backend.capabilities())
        except Exception:  # noqa: BLE001
            caps = {"backend": self.config.backend}
        caps["reasoning_extraction"] = "llm" if self.llm.available() else "heuristic"
        return caps

    # ---- management ----------------------------------------------------------
    def list_projects(self) -> list[str]:
        """Projects with saved state for the current user (scoping stripped, lessons hidden)."""
        out = []
        for p in self.backend.list_projects():
            if self.user == "default":
                if "::" not in p and p != _LESSONS:
                    out.append(p)
            elif p.startswith(f"{self.user}::"):
                name = self._unscope(p)
                if name != _LESSONS:
                    out.append(name)
        return sorted(set(out))

    def forget(self, project: str) -> dict:
        """Permanently delete a project's memory (cascade). Returns removed counts."""
        counts = self.backend.delete_project(self._scope(project))
        log.info("forget user=%s project=%s removed=%s", self.user, project, counts)
        return counts

    def search(self, project: str, query: str, k: int = 6) -> list[str]:
        """Search a project's verbatim memory; returns matching passages."""
        return [c.text for c in self.backend.search_verbatim(self._scope(project), query, k)]

    def status(self, project: str) -> dict:
        sp = self._scope(project)
        ws = self.backend.latest_workspace(sp)
        graph = self.backend.get_reasoning(sp)
        return {
            "user": self.user,
            "project": project,
            "has_state": ws is not None,
            "checkpoint_id": ws.checkpoint_id if ws else None,
            "decisions": len(ws.decisions) if ws else 0,
            "reasoning_nodes": len(graph.nodes),
            "reasoning_edges": len(graph.edges),
            "checkpoints": len(self.backend.list_workspaces(sp)),
            "llm_mode": "llm" if self.llm.available() else "heuristic",
            "backend": self.config.backend,
            "capabilities": self.mode(),
        }
