"""The reasoning ontology.

This is the schema an LLM extracts INTO (schema-constrained generation), and — in the
Cognee backend — the `graph_model` passed to `cognify()`. It captures *reasoning-state*
(decisions, rejected alternatives, hypotheses), not just entity-relationship knowledge.

Ancestor: Truth Maintenance Systems (Doyle, 1979) — beliefs + justifications + retractions.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field

NodeKind = Literal[
    "Goal",  # what we're trying to achieve
    "Decision",  # a choice that was made
    "Alternative",  # an option that was considered (often rejected)
    "Hypothesis",  # a belief being tested
    "Evidence",  # something supporting/refuting a hypothesis
    "Constraint",  # a limit we must respect
    "OpenQuestion",  # unresolved
    "Task",  # a unit of work
    "CodeRef",  # a file/function/snippet reference
    "Insight",  # a durable learning
]

NodeStatus = Literal["active", "accepted", "rejected", "resolved", "blocked", "in_progress"]

EdgeRelation = Literal[
    "chosen_because",  # Decision -> Evidence/Constraint
    "rejected_because",  # Alternative -> Evidence/Constraint
    "depends_on",  # Task/Decision -> Task/Decision
    "supported_by",  # Hypothesis -> Evidence
    "invalidated_by",  # Hypothesis/Decision -> Evidence
    "supersedes",  # Decision -> Decision (newer replaces older)
    "blocks",  # X -> Task
    "answers",  # Evidence/Decision -> OpenQuestion
    "relates_to",  # generic
]


class ReasoningNode(BaseModel):
    """An entity in the reasoning graph (a decision, alternative, hypothesis, ...)."""

    id: str = Field(description="Stable, human-readable id, e.g. 'decision:jwt-over-oauth'.")
    name: str = Field(description="Short display name.")
    kind: NodeKind
    description: str = Field(description="1-2 sentences, using concrete names.")
    status: Optional[NodeStatus] = None
    # HYBRID: pointer back to the exact source text this was extracted from.
    verbatim_ref: Optional[str] = Field(
        default=None,
        description="Chunk id of the verbatim source, so we can inject exact words on resume.",
    )
    # TEMPORAL: when this node first appeared, so we can reconstruct the *evolution of thinking*
    # (thought -> rejected -> superseded) and rank by recency. Preserved (earliest-wins) on merge.
    created_at: float = Field(default_factory=lambda: time.time())


class ReasoningEdge(BaseModel):
    """A directed relationship between two reasoning nodes."""

    source_node_id: str
    target_node_id: str
    relation: EdgeRelation
    description: Optional[str] = Field(
        default=None, description="Concrete one-sentence fact this edge expresses."
    )


class ReasoningGraph(BaseModel):
    """The reasoning graph extracted from a conversation. Cognee `graph_model`."""

    nodes: list[ReasoningNode] = Field(default_factory=list)
    edges: list[ReasoningEdge] = Field(default_factory=list)

    def merge(self, other: "ReasoningGraph") -> "ReasoningGraph":
        """Merge another graph in, de-duplicating nodes by id (latest wins) and edges by triple.

        Temporal: a node's `created_at` keeps the EARLIEST value across merges (first-seen),
        while all other fields take the newer version — so status changes (e.g. active ->
        rejected) are captured without losing when the idea first appeared.
        """
        nodes = {n.id: n for n in self.nodes}
        for n in other.nodes:
            prev = nodes.get(n.id)
            if prev is not None:
                n.created_at = min(prev.created_at, n.created_at)
            nodes[n.id] = n
        seen = {(e.source_node_id, e.relation, e.target_node_id) for e in self.edges}
        edges = list(self.edges)
        for e in other.edges:
            key = (e.source_node_id, e.relation, e.target_node_id)
            if key not in seen:
                seen.add(key)
                edges.append(e)
        return ReasoningGraph(nodes=list(nodes.values()), edges=edges)
