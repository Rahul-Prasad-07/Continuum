"""Salience scoring tests — active/unresolved reasoning outranks resolved."""

from continuum.engine.salience import rank_nodes, score_node
from continuum.models import ReasoningEdge, ReasoningGraph, ReasoningNode


def test_active_goal_outranks_resolved_coderef():
    goal = ReasoningNode(id="g", name="Goal", kind="Goal", description="ship auth", status="active")
    code = ReasoningNode(id="c", name="file", kind="CodeRef", description="x.py", status="resolved")
    assert score_node(goal) > score_node(code)


def test_rank_orders_by_salience_and_uses_refs():
    g = ReasoningGraph(
        nodes=[
            ReasoningNode(id="d", name="decision", kind="Decision", description="jwt", status="active"),
            ReasoningNode(id="e", name="ev", kind="Evidence", description="bench", status="resolved"),
        ],
        edges=[ReasoningEdge(source_node_id="e", target_node_id="d", relation="supported_by")],
    )
    ranked = rank_nodes(g)
    assert ranked[0][0].id == "d"  # the active decision ranks first
    assert len(ranked) == 2
