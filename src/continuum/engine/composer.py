"""Composer — build the resume package (the artifact that moves between chats/providers).

Hybrid + salience-bounded:
- STRUCTURE (from the reasoning graph + workspace) for navigation/why.
- VERBATIM (retrieved, guided by graph refs) for fidelity — answers "verbatim beats extraction".
- BOUNDED by a token budget so it never bloats the next context window (the forgetting/
  salience layer that keeps the context math a net win).
"""

from __future__ import annotations

import re

from continuum.engine.salience import rank_nodes
from continuum.memory.base import Chunk, MemoryBackend
from continuum.models import Decision, ReasoningGraph, WorkspaceState


def _toks(s: str) -> int:
    return max(1, len(s) // 4)  # rough tokens ≈ chars/4


_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9-]{2,}")
_Q_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "is", "it", "we", "i",
           "this", "that", "with", "how", "what", "why", "work", "task", "continue"}


def _terms(q: str) -> set[str]:
    return {w for w in _WORD.findall(q.lower()) if w not in _Q_STOP}


def compose_resume(
    backend: MemoryBackend, project: str, intent: str, budget_tokens: int = 8000
) -> str:
    ws = backend.latest_workspace(project)
    graph = backend.get_reasoning(project)
    if ws is None and not graph.nodes:
        return f"(No saved state for project '{project}'. Nothing to resume.)"

    used = 0
    out: list[str] = []

    def add(block: str) -> bool:
        nonlocal used
        t = _toks(block)
        if used + t > budget_tokens:
            return False
        out.append(block)
        used += t
        return True

    add(
        f"# RESUME PACKAGE — project: {project.split('::')[-1]}\n"
        f"You are resuming prior work. This is the reconstructed reasoning state. "
        f"Continue exactly from here; do not restart.\n"
    )

    if ws:
        add(_fmt_workspace(ws, intent))

    # Knowledge-graph answer (Cognee GRAPH_COMPLETION) — facts synthesized from the entity graph,
    # not just chunks. None on the local backend (no knowledge graph). This is the layer that
    # makes resume use everything Cognee builds, on top of the reasoning graph.
    kg = _knowledge_answer(backend, project, intent, ws)
    if kg:
        add("## Knowledge-graph context (from Cognee)\n" + kg + "\n")

    # Rejected alternatives — the differentiator: why we did NOT do things.
    rejected = _rejected_from_graph(graph)
    if rejected:
        add("## Rejected alternatives (do NOT re-propose these)\n" + "\n".join(rejected) + "\n")

    # Verbatim, guided by the graph + intent retrieval (fidelity for the relevant spots).
    add("## Relevant verbatim (exact words from the original session)\n")
    seen: set[str] = set()
    for ch in _relevant_verbatim(backend, project, graph, intent, ws):
        if ch.id in seen:
            continue
        seen.add(ch.id)
        block = f"> {ch.text.strip()}\n"
        if not add(block):
            break

    add(f"\n---\n_Reconstructed by Continuum · ~{used} tokens · budget {budget_tokens}._")
    return "\n".join(out)


def _fmt_workspace(ws: WorkspaceState, intent: str) -> str:
    lines = ["## Working state"]
    if intent:
        lines.append(f"- **Resuming toward:** {intent}")
    if ws.goal:
        lines.append(f"- **Goal:** {ws.goal}")
    if ws.current_task:
        lines.append(f"- **Was working on:** {ws.current_task}")
    if ws.decisions:
        lines.append("- **Decisions made:**")
        for d in ws.decisions:
            why = f" — because {d.why}" if d.why else ""
            lines.append(f"    - {d.choice}{why}")
            for r in d.rejected:
                lines.append(f"        - (rejected: {r.option} — {r.why_rejected})")
    if ws.constraints:
        lines.append("- **Constraints:** " + "; ".join(ws.constraints))
    if ws.active_hypotheses:
        lines.append("- **Active hypotheses:** " + "; ".join(ws.active_hypotheses))
    if ws.open_questions:
        lines.append("- **Open questions:** " + "; ".join(ws.open_questions))
    if ws.blocked_by:
        lines.append("- **Blocked by:** " + "; ".join(ws.blocked_by))
    if ws.next_steps:
        lines.append("- **Next steps:** " + "; ".join(ws.next_steps))
    if ws.code_refs:
        lines.append("- **Code refs:** " + ", ".join(ws.code_refs))
    return "\n".join(lines) + "\n"


def _knowledge_answer(
    backend: MemoryBackend, project: str, intent: str, ws: WorkspaceState | None
) -> str | None:
    """Ask the backend's knowledge graph a focused question (Cognee GRAPH_COMPLETION). Backends
    without a knowledge graph return None, so this is a no-op on local."""
    query = intent or (ws.current_task if ws else "") or (ws.goal if ws else "")
    if not query:
        return None
    try:
        return backend.graph_answer(project, query)
    except Exception:  # noqa: BLE001 — never let enrichment break a resume
        return None


def _rejected_from_graph(graph: ReasoningGraph) -> list[str]:
    # Salience-ranked so, when trimmed, we keep the most important rejections.
    ranked = rank_nodes(graph)
    out = []
    for n, _ in ranked:
        if n.kind == "Alternative" or n.status == "rejected":
            out.append(f"- {n.name}: {n.description}")
    return out[:10]


def _relevant_verbatim(
    backend: MemoryBackend,
    project: str,
    graph: ReasoningGraph,
    intent: str,
    ws: WorkspaceState | None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    # 1) verbatim refs cited by reasoning nodes, most-salient first (graph-guided fidelity)
    for n, _ in rank_nodes(graph):
        if n.verbatim_ref:
            ch = backend.get_chunk(project, n.verbatim_ref)
            if ch:
                chunks.append(ch)
    # 2) semantic/keyword retrieval on the resume intent
    query = intent or (ws.current_task if ws else "") or (ws.goal if ws else "")
    chunks += backend.search_verbatim(project, query, k=6)
    return chunks


# ---------------------------------------------------------------- topic/intent RECALL
def _ws_text(ws: WorkspaceState) -> str:
    """Everything a checkpoint is 'about', flattened for matching."""
    parts = [ws.goal, ws.current_task, " ".join(ws.topics)]
    parts += [d.choice for d in ws.decisions]
    parts += ws.open_questions + ws.constraints
    return " ".join(p for p in parts if p)


def _overlap(ws: WorkspaceState, terms: set[str]) -> float:
    """Fraction of query terms this checkpoint mentions (0..1)."""
    if not terms:
        return 0.0
    return len(terms & _terms(_ws_text(ws))) / len(terms)


def _score_ws(ws: WorkspaceState, terms: set[str], newest_ts: float, oldest_ts: float) -> float:
    """Relevance = term overlap (dominant) + a mild recency nudge for ranking ties."""
    span = (newest_ts - oldest_ts) or 1.0
    recency = (ws.timestamp - oldest_ts) / span  # 0 oldest → 1 newest
    return _overlap(ws, terms) + 0.15 * recency


def compose_recall(
    backend: MemoryBackend,
    project: str,
    query: str,
    budget_tokens: int = 8000,
    max_checkpoints: int = 8,
) -> str:
    """Resume by SUBJECT across the whole history, not just the latest checkpoint.

    Gathers every checkpoint whose reasoning is about `query` (topic or intent), ranks them by
    relevance, and composes a single bounded package: merged decisions (with why + rejected),
    still-open questions, the knowledge-graph answer, and the most relevant verbatim. This is
    the answer to "I worked on X weeks ago but the latest checkpoint is about something else."
    """
    workspaces = backend.list_workspaces(project)
    graph = backend.get_reasoning(project)
    if not workspaces and not graph.nodes:
        return f"(No saved state for project '{project}'. Nothing to recall.)"

    terms = _terms(query)
    if workspaces:
        newest = max(w.timestamp for w in workspaces)
        oldest = min(w.timestamp for w in workspaces)
        scored = sorted(
            ((w, _score_ws(w, terms, newest, oldest)) for w in workspaces),
            key=lambda t: t[1], reverse=True,
        )
        # A checkpoint qualifies only if it actually mentions the subject (real term overlap);
        # recency alone must never pull in unrelated work. With no subject, take the recent ones.
        if terms:
            matching = [w for w, _ in scored if _overlap(w, terms) > 0][:max_checkpoints]
        else:
            matching = [w for w, _ in scored[:max_checkpoints]]
        if not matching:  # subject worked on nowhere → fall back to the latest so resume isn't empty
            matching = [w for w, _ in scored[:2]]
        matching = sorted(matching, key=lambda w: w.timestamp)  # chronological for reading
    else:
        matching = []

    used = 0
    out: list[str] = []

    def add(block: str) -> bool:
        nonlocal used
        t = _toks(block)
        if used + t > budget_tokens:
            return False
        out.append(block)
        used += t
        return True

    disp = project.split("::")[-1]
    add(
        f"# RECALL — project: {disp} · subject: {query or '(everything)'}\n"
        f"Reconstructed from {len(matching)} of {len(workspaces)} checkpoints that match this "
        f"subject (not just the latest). Continue from this accumulated state.\n"
    )

    # Chronological arc — how the thinking on this subject evolved.
    if matching:
        arc = ["## How this subject evolved"]
        for w in matching:
            when = _ymd(w.timestamp)
            what = w.current_task or w.goal or (w.topics[0] if w.topics else w.checkpoint_id)
            arc.append(f"- {when} · {what} ({len(w.decisions)} decisions)")
        add("\n".join(arc) + "\n")

    # Merged decisions across all matching checkpoints (deduped, most recent wins).
    merged = _merge_decisions(matching)
    if merged:
        lines = ["## Decisions so far (across all matching checkpoints)"]
        for d in merged:
            why = f" — because {d.why}" if d.why else ""
            lines.append(f"- {d.choice}{why}")
            for r in d.rejected:
                lines.append(f"    - rejected: {r.option} — {r.why_rejected}")
        add("\n".join(lines) + "\n")

    # Still-open questions gathered from every matching checkpoint.
    open_qs = _dedup(q for w in matching for q in w.open_questions)
    if open_qs:
        add("## Still-open questions\n" + "\n".join(f"- {q}" for q in open_qs) + "\n")

    constraints = _dedup(c for w in matching for c in w.constraints)
    if constraints:
        add("## Constraints in force\n" + "\n".join(f"- {c}" for c in constraints) + "\n")

    kg = None
    try:
        kg = backend.graph_answer(project, query) if query else None
    except Exception:  # noqa: BLE001
        kg = None
    if kg:
        add("## Knowledge-graph context (from Cognee)\n" + kg + "\n")

    # Verbatim retrieved for the subject (fidelity for the exact words).
    add("## Relevant verbatim (exact words on this subject)\n")
    seen: set[str] = set()
    for ch in backend.search_verbatim(project, query, k=8):
        if ch.id in seen:
            continue
        seen.add(ch.id)
        if not add(f"> {ch.text.strip()}\n"):
            break

    add(f"\n---\n_Continuum recall · ~{used} tokens · budget {budget_tokens}._")
    return "\n".join(out)


def _merge_decisions(workspaces: list[WorkspaceState]) -> list[Decision]:
    """Dedup decisions by their choice text; later checkpoints win (they reflect newer thinking)."""
    by_key: dict[str, Decision] = {}
    for w in workspaces:  # already chronological
        for d in w.decisions:
            by_key[re.sub(r"\s+", " ", d.choice.lower()).strip()[:80]] = d
    return list(by_key.values())


def _dedup(items) -> list[str]:
    out, seen = [], set()
    for it in items:
        k = re.sub(r"\s+", " ", (it or "").lower()).strip()[:80]
        if k and k not in seen:
            seen.add(k)
            out.append(it)
    return out


def _ymd(ts: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
