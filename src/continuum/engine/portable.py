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
from typing import Optional

from continuum.memory.base import Chunk, MemoryBackend
from continuum.models import ReasoningGraph, WorkspaceState

BUNDLE_VERSION = 1


def _toks(s: str) -> int:
    return max(1, len(s) // 4)


# ---------------------------------------------------------------- lossless bundle (json)
def export_bundle(
    backend: MemoryBackend,
    scoped_project: str,
    display_name: str,
    since: Optional[float] = None,
    include_verbatim: bool = True,
) -> dict:
    """Serialize a whole project (verbatim + workspaces + reasoning) to a portable dict.

    `since` (unix ts) makes it an INCREMENTAL snapshot — only checkpoints newer than `since`,
    so a machine can pull just the delta instead of re-reading months of history. When set,
    verbatim defaults off (the reasoning delta is the point); pass include_verbatim=True to keep it.
    """
    workspaces = backend.list_workspaces(scoped_project)
    if since is not None:
        workspaces = [w for w in workspaces if w.timestamp > since]
        include_verbatim = include_verbatim and since is None  # incremental = reasoning delta
    graph = backend.get_reasoning(scoped_project)
    chunks = backend.all_chunks(scoped_project) if include_verbatim else []
    return {
        "continuum_bundle": BUNDLE_VERSION,
        "project": display_name,
        "exported_at": time.time(),
        "since": since,
        "incremental": since is not None,
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
def export_markdown(
    backend: MemoryBackend,
    scoped_project: str,
    display_name: str,
    max_tokens: Optional[int] = None,
    since: Optional[float] = None,
) -> str:
    """The whole saved conversation-state as one paste-anywhere document.

    `max_tokens` bounds the output so it always fits the next context window — the reasoning-state
    (decisions/rejected/open questions) is kept first, then as much verbatim as the budget allows.
    `since` includes only verbatim/checkpoints newer than a timestamp (an incremental doc).
    """
    workspaces = backend.list_workspaces(scoped_project)
    if since is not None:
        workspaces = [w for w in workspaces if w.timestamp > since]
    graph = backend.get_reasoning(scoped_project)
    chunks = backend.all_chunks(scoped_project)
    ws = workspaces[-1] if workspaces else None

    head: list[str] = [
        f"# CONTINUUM EXPORT — project: {display_name}",
        "_Paste this into a new chat on any AI to resume exactly where you left off. "
        "It contains the reasoning-state (decisions, rejected options, open questions) and the "
        "verbatim conversation below._\n",
    ]

    if ws:
        head.append("## Reasoning state (latest checkpoint)")
        if ws.goal:
            head.append(f"- **Goal:** {ws.goal}")
        if ws.current_task:
            head.append(f"- **Was working on:** {ws.current_task}")
        for d in ws.decisions:
            why = f" — because {d.why}" if d.why else ""
            head.append(f"- **Decided:** {d.choice}{why}")
            for r in d.rejected:
                head.append(f"    - rejected: {r.option} — {r.why_rejected}")
        if ws.constraints:
            head.append("- **Constraints:** " + "; ".join(ws.constraints))
        if ws.open_questions:
            head.append("- **Open questions:** " + "; ".join(ws.open_questions))
        if ws.next_steps:
            head.append("- **Next steps:** " + "; ".join(ws.next_steps))
        head.append("")

    rejected = [n for n in graph.nodes if n.kind == "Alternative" or n.status == "rejected"]
    if rejected:
        head.append("## Rejected alternatives (do NOT re-propose)")
        for n in rejected:
            head.append(f"- {n.name}: {n.description}")
        head.append("")

    # Verbatim fills whatever budget remains (reasoning-state above is always kept).
    body: list[str] = []
    budget = None if max_tokens is None else max_tokens - _toks("\n".join(head))
    if chunks and (budget is None or budget > 0):
        body.append("## Full conversation (verbatim, in order)")
        truncated = False
        for c in chunks:
            block = c.text.strip()
            if budget is not None and _toks("\n".join(body) + block) > budget:
                truncated = True
                break
            body.append(block)
            body.append("")
        if truncated:
            body.append("_(verbatim truncated to fit the token budget — "
                        "use `export -f json` for the lossless bundle.)_")

    tail = ["---", f"_Exported by Continuum · {len(chunks)} verbatim chunks · "
            f"{len(graph.nodes)} reasoning nodes._"]
    return "\n".join(head + body + tail)


# ---------------------------------------------------------------- hierarchical digest
def export_digest(
    backend: MemoryBackend,
    scoped_project: str,
    display_name: str,
    recent: int = 5,
    budget_tokens: int = 6000,
) -> str:
    """Compress a long project into a bounded digest: the `recent` checkpoints in full detail,
    everything older collapsed to one line each (task + decision/question counts). This is how a
    month (or a year) of work stays paste-able in a few thousand tokens instead of exploding the
    context window."""
    workspaces = backend.list_workspaces(scoped_project)
    if not workspaces:
        return f"# CONTINUUM DIGEST — {display_name}\n_(no checkpoints yet)_"

    out: list[str] = [
        f"# CONTINUUM DIGEST — project: {display_name}",
        f"_{len(workspaces)} checkpoints compressed to fit ~{budget_tokens} tokens. "
        f"Recent work in full; older work summarized._\n",
    ]
    old, new = workspaces[:-recent], workspaces[-recent:]

    if old:
        out.append(f"## Earlier history ({len(old)} checkpoints, summarized)")
        for w in old:
            when = _ymd(w.timestamp)
            what = w.current_task or w.goal or (", ".join(w.topics[:2]) if w.topics else "—")
            out.append(f"- {when} · {what[:90]} "
                       f"({len(w.decisions)} decisions, {len(w.open_questions)} open)")
        out.append("")

    out.append(f"## Recent work ({len(new)} checkpoints, full detail)")
    for w in new:
        out.append(f"### {_ymd(w.timestamp)} — {w.current_task or w.goal or w.checkpoint_id}")
        for d in w.decisions:
            why = f" — because {d.why}" if d.why else ""
            out.append(f"- **Decided:** {d.choice}{why}")
        if w.open_questions:
            out.append("- **Open:** " + "; ".join(w.open_questions))
        out.append("")

    # Bound it: keep trimming the earliest 'recent' detail until under budget.
    text = "\n".join(out)
    while _toks(text) > budget_tokens and len(out) > 6:
        del out[3:5]  # peel from the earlier-history section first
        text = "\n".join(out)
    return text


def _ymd(ts: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
