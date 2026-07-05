"""Refine — the layers that turn Continuum from "reasoning capture" into a *complete* memory system.

- improve() / memify : self-improving reasoning graph (dedup, drop dangling edges, mark superseded).
- distill()          : harvest durable lessons (Insights) for cross-project reuse.
- prune()            : active forgetting — drop low-salience nodes so the index stays lean
                       (verbatim source is never deleted, only the index is trimmed).
- timeline()         : the temporal evolution of the thinking (one row per checkpoint).
"""

from __future__ import annotations

import re

from continuum.engine.salience import rank_nodes
from continuum.models import ReasoningEdge, ReasoningGraph, ReasoningNode, WorkspaceState


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:40] or "x"


# ---------------------------------------------------------------- improve / memify
def improve_graph(graph: ReasoningGraph) -> tuple[ReasoningGraph, dict]:
    """Self-improve: merge near-duplicate nodes (by kind+name), remap/dedup edges, drop
    dangling edges, and mark superseded decisions resolved. Heuristic (no LLM needed)."""
    by_key: dict[tuple[str, str], ReasoningNode] = {}
    remap: dict[str, str] = {}
    for n in graph.nodes:
        key = (n.kind, _norm(n.name))
        if key in by_key:
            keep = by_key[key]
            keep.created_at = min(keep.created_at, n.created_at)  # earliest-seen wins
            keep.status = n.status or keep.status                 # newer status wins
            if len(n.description) > len(keep.description):
                keep.description = n.description
            keep.verbatim_ref = keep.verbatim_ref or n.verbatim_ref
            remap[n.id] = keep.id
        else:
            by_key[key] = n
            remap[n.id] = n.id

    nodes = list(by_key.values())
    node_ids = {n.id for n in nodes}

    seen: set[tuple[str, str, str]] = set()
    edges: list[ReasoningEdge] = []
    for e in graph.edges:
        s = remap.get(e.source_node_id, e.source_node_id)
        t = remap.get(e.target_node_id, e.target_node_id)
        if s in node_ids and t in node_ids and s != t:
            k = (s, e.relation, t)
            if k not in seen:
                seen.add(k)
                e.source_node_id, e.target_node_id = s, t
                edges.append(e)

    superseded = {e.target_node_id for e in edges if e.relation == "supersedes"}
    for n in nodes:
        if n.id in superseded and n.status != "rejected":
            n.status = "resolved"

    improved = ReasoningGraph(nodes=nodes, edges=edges)
    return improved, {
        "nodes_before": len(graph.nodes), "nodes_after": len(nodes),
        "edges_before": len(graph.edges), "edges_after": len(edges),
        "merged": len(graph.nodes) - len(nodes),
    }


# ---------------------------------------------------------------- distill (cross-project lessons)
def distill_lessons(graph: ReasoningGraph, ws: WorkspaceState | None) -> list[str]:
    """Harvest durable, standalone lessons for reuse across projects (the session_distillation
    idea): Insight nodes + accepted decisions' rationale, deduped."""
    lessons: list[str] = [n.description or n.name for n in graph.nodes if n.kind == "Insight"]
    if ws:
        lessons += [f"{d.choice} — because {d.why}" for d in ws.decisions if d.why]
    out, seen = [], set()
    for l in lessons:
        k = _norm(l)[:80]
        if k and k not in seen:
            seen.add(k)
            out.append(l)
    return out[:20]


def lessons_to_graph(lessons: list[str]) -> ReasoningGraph:
    """Turn distilled lesson strings into Insight nodes for the shared lessons store."""
    nodes = [
        ReasoningNode(id=f"insight:{_slug(l)}", name=l[:60], kind="Insight",
                      description=l, status="accepted")
        for l in lessons
    ]
    return ReasoningGraph(nodes=nodes, edges=[])


# ---------------------------------------------------------------- prune (active forgetting)
def prune_graph(graph: ReasoningGraph, keep: int = 60, min_score: float = 0.5) -> tuple[ReasoningGraph, dict]:
    """Keep the top-`keep` most-salient nodes above `min_score`; drop the rest. Goals and open
    questions are always kept. (Only the index is trimmed; verbatim source stays in storage.)"""
    ranked = rank_nodes(graph)
    keep_ids = {n.id for n, s in ranked[:keep] if s >= min_score}
    for n in graph.nodes:
        if n.kind in ("Goal", "OpenQuestion") and n.status != "resolved":
            keep_ids.add(n.id)
    nodes = [n for n in graph.nodes if n.id in keep_ids]
    edges = [e for e in graph.edges
             if e.source_node_id in keep_ids and e.target_node_id in keep_ids]
    return ReasoningGraph(nodes=nodes, edges=edges), {
        "nodes_before": len(graph.nodes), "nodes_after": len(nodes),
        "dropped": len(graph.nodes) - len(nodes),
    }


# ---------------------------------------------------------------- timeline (temporal)
def build_timeline(workspaces: list[WorkspaceState]) -> list[dict]:
    """The evolution of the thinking — one row per checkpoint, oldest→newest."""
    return [
        {
            "checkpoint_id": ws.checkpoint_id,
            "timestamp": ws.timestamp,
            "goal": ws.goal,
            "current_task": ws.current_task,
            "decisions": len(ws.decisions),
            "open_questions": len(ws.open_questions),
        }
        for ws in workspaces
    ]
