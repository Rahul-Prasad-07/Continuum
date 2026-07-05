"""Portable export / import — take your reasoning-state anywhere.

Two shapes, two jobs:
  - BUNDLE (json): lossless — every workspace snapshot, the reasoning graph, and all verbatim
    chunks. Import it into another Continuum install or another user to move/clone a project
    with full fidelity. This is the "switch machines / back up / migrate tenant" path.
  - MARKDOWN: a single human-readable document of the whole saved conversation-state. Paste it
    into a brand-new chat on ANY provider (Claude, ChatGPT, Grid, Gemini…) to pick up exactly
    where you left off. This is the "start a fresh chat / switch platforms" path.

Both are provider-neutral plain data — no lock-in.
"""

from __future__ import annotations

import time

from continuum.memory.base import Chunk, MemoryBackend
from continuum.models import ReasoningGraph, WorkspaceState

BUNDLE_VERSION = 1


# ---------------------------------------------------------------- lossless bundle (json)
def export_bundle(backend: MemoryBackend, scoped_project: str, display_name: str) -> dict:
    """Serialize a whole project (verbatim + workspaces + reasoning) to a portable dict."""
    workspaces = backend.list_workspaces(scoped_project)
    graph = backend.get_reasoning(scoped_project)
    chunks = backend.all_chunks(scoped_project)
    return {
        "continuum_bundle": BUNDLE_VERSION,
        "project": display_name,
        "exported_at": time.time(),
        "counts": {
            "workspaces": len(workspaces),
            "verbatim": len(chunks),
            "reasoning_nodes": len(graph.nodes),
            "reasoning_edges": len(graph.edges),
        },
        "workspaces": [ws.model_dump(mode="json") for ws in workspaces],
        "reasoning": graph.model_dump(mode="json"),
        "verbatim": [c.model_dump(mode="json") for c in chunks],
    }


def import_bundle(backend: MemoryBackend, scoped_project: str, data: dict) -> dict:
    """Restore a bundle into `scoped_project` (may be a different user/install)."""
    if not isinstance(data, dict) or "continuum_bundle" not in data:
        raise ValueError("not a Continuum bundle (missing 'continuum_bundle')")

    # Verbatim first (reasoning nodes reference chunk ids); re-project to the target scope.
    chunks: list[Chunk] = []
    for c in data.get("verbatim", []):
        ch = Chunk(**c)
        ch.project = scoped_project  # keep content-addressed id, retarget the scope
        chunks.append(ch)
    if chunks:
        backend.add_verbatim(scoped_project, chunks)

    for wsd in data.get("workspaces", []):
        ws = WorkspaceState(**wsd)
        ws.project = scoped_project
        backend.store_workspace(scoped_project, ws)

    graph = ReasoningGraph(**data.get("reasoning", {"nodes": [], "edges": []}))
    if graph.nodes or graph.edges:
        backend.store_reasoning(scoped_project, graph)  # merges into any existing

    return {
        "project": display_name_of(data),
        "imported_workspaces": len(data.get("workspaces", [])),
        "imported_verbatim": len(chunks),
        "imported_nodes": len(graph.nodes),
        "imported_edges": len(graph.edges),
    }


def display_name_of(data: dict) -> str:
    return str(data.get("project", "?"))


# ---------------------------------------------------------------- full transcript (grok-style)
def export_transcript(backend: MemoryBackend, scoped_project: str, display_name: str) -> str:
    """The complete conversation as a clean role-tagged Markdown transcript — the grok-`export`
    equivalent. Because verbatim is stored in order and role-tagged, this reproduces the whole chat."""
    chunks = backend.all_chunks(scoped_project)
    body = "\n\n".join(c.text.strip() for c in chunks if c.text.strip())
    return (
        f"# {display_name} — conversation transcript\n"
        f"_Exported by Continuum · {len(chunks)} segments · provider-neutral._\n\n"
        f"{body}\n"
    )


# ---------------------------------------------------------------- human-readable (markdown)
def export_markdown(backend: MemoryBackend, scoped_project: str, display_name: str) -> str:
    """The whole saved conversation-state as one paste-anywhere document."""
    workspaces = backend.list_workspaces(scoped_project)
    graph = backend.get_reasoning(scoped_project)
    chunks = backend.all_chunks(scoped_project)
    ws = workspaces[-1] if workspaces else None

    out: list[str] = [
        f"# CONTINUUM EXPORT — project: {display_name}",
        "_Paste this into a new chat on any AI to resume exactly where you left off. "
        "It contains the reasoning-state (decisions, rejected options, open questions) and the "
        "full verbatim conversation below._\n",
    ]

    if ws:
        out.append("## Reasoning state (latest checkpoint)")
        if ws.goal:
            out.append(f"- **Goal:** {ws.goal}")
        if ws.current_task:
            out.append(f"- **Was working on:** {ws.current_task}")
        for d in ws.decisions:
            why = f" — because {d.why}" if d.why else ""
            out.append(f"- **Decided:** {d.choice}{why}")
            for r in d.rejected:
                out.append(f"    - rejected: {r.option} — {r.why_rejected}")
        if ws.constraints:
            out.append("- **Constraints:** " + "; ".join(ws.constraints))
        if ws.open_questions:
            out.append("- **Open questions:** " + "; ".join(ws.open_questions))
        if ws.next_steps:
            out.append("- **Next steps:** " + "; ".join(ws.next_steps))
        out.append("")

    rejected = [n for n in graph.nodes if n.kind == "Alternative" or n.status == "rejected"]
    if rejected:
        out.append("## Rejected alternatives (do NOT re-propose)")
        for n in rejected:
            out.append(f"- {n.name}: {n.description}")
        out.append("")

    if chunks:
        out.append("## Full conversation (verbatim, in order)")
        for c in chunks:
            out.append(c.text.strip())
            out.append("")

    out.append("---")
    out.append(f"_Exported by Continuum · {len(chunks)} verbatim chunks · "
               f"{len(graph.nodes)} reasoning nodes._")
    return "\n".join(out)
