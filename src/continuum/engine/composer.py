"""Composer — build the resume package (the artifact that moves between chats/providers).

Hybrid + salience-bounded:
- STRUCTURE (from the reasoning graph + workspace) for navigation/why.
- VERBATIM (retrieved, guided by graph refs) for fidelity — answers "verbatim beats extraction".
- BOUNDED by a token budget so it never bloats the next context window (the forgetting/
  salience layer that keeps the context math a net win).
"""

from __future__ import annotations

from continuum.engine.salience import rank_nodes
from continuum.memory.base import Chunk, MemoryBackend
from continuum.models import ReasoningGraph, WorkspaceState


def _toks(s: str) -> int:
    return max(1, len(s) // 4)  # rough tokens ≈ chars/4


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
