"""Salience scoring — the "what's worth keeping / loading" layer.

Reasoning-state grows unbounded on disk; the resume package must NOT. Salience ranks what to
include so the package stays bounded (the ENGRAM active-forgetting principle) and the context
math stays a net win. Signals: node kind, status, recency, and reference-frequency.
"""

from __future__ import annotations

from continuum.models import ReasoningGraph, ReasoningNode

# How intrinsically resume-worthy each kind is.
_KIND = {
    "Goal": 1.0,
    "OpenQuestion": 0.92,
    "Constraint": 0.88,
    "Decision": 0.85,
    "Hypothesis": 0.78,
    "Task": 0.72,
    "Insight": 0.72,
    "Alternative": 0.70,  # rejected alts are the differentiator — keep them
    "Evidence": 0.55,
    "CodeRef": 0.45,
}

# Active/unresolved matters more for *resuming*.
_STATUS = {
    "active": 1.0,
    "in_progress": 1.0,
    "blocked": 0.95,
    None: 0.8,
    "accepted": 0.8,
    "rejected": 0.65,  # keep, but below active work
    "resolved": 0.4,
}


def score_node(node: ReasoningNode, recency: float = 1.0, ref_count: int = 0) -> float:
    """0..~1.2. Higher = more resume-worthy. `recency` in [0,1], newest = 1."""
    kind = _KIND.get(node.kind, 0.5)
    status = _STATUS.get(node.status, 0.8)
    return 0.45 * kind + 0.30 * status + 0.20 * recency + 0.05 * min(ref_count, 5)


def rank_nodes(graph: ReasoningGraph) -> list[tuple[ReasoningNode, float]]:
    """Nodes sorted by salience (desc). Recency approximated by position (later = newer)."""
    n = len(graph.nodes) or 1
    ref_counts: dict[str, int] = {}
    for e in graph.edges:
        ref_counts[e.target_node_id] = ref_counts.get(e.target_node_id, 0) + 1
        ref_counts[e.source_node_id] = ref_counts.get(e.source_node_id, 0) + 1
    scored = [
        (node, score_node(node, recency=(i + 1) / n, ref_count=ref_counts.get(node.id, 0)))
        for i, node in enumerate(graph.nodes)
    ]
    return sorted(scored, key=lambda t: t[1], reverse=True)
