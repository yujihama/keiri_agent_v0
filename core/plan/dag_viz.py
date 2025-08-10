from __future__ import annotations

from typing import Any, Dict, List, Tuple

import matplotlib

# Use non-interactive backend for headless/test environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402

from .models import Plan, Node


def _extract_edges(plan: Plan) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in plan.graph:
        g.add_node(n.id)

    def add_edges_from_placeholder(value: Any, dest_id: str) -> None:
        if not isinstance(value, str):
            return
        if not (value.startswith("${") and value.endswith("}")):
            return
        inner = value[2:-1]
        if inner.startswith(("vars.", "env.", "config.")):
            return
        if "." not in inner:
            return
        src = inner.split(".", 1)[0]
        if src:
            g.add_edge(src, dest_id)

    for n in plan.graph:
        if n.type:
            # loop/subflow edges: best-effort
            if n.type == "loop" and n.foreach and isinstance(n.foreach.get("input"), str):
                add_edges_from_placeholder(n.foreach.get("input"), n.id)
            if n.type == "loop" and n.while_:
                cond = n.while_.get("condition", {}) if isinstance(n.while_, dict) else {}
                expr = cond.get("expr") if isinstance(cond, dict) else None
                if isinstance(expr, str):
                    add_edges_from_placeholder(expr, n.id)
            continue
        for v in n.inputs.values():
            add_edges_from_placeholder(v, n.id)
    return g


def compute_node_states(plan: Plan, events: List[Dict[str, Any]]) -> Dict[str, str]:
    """Compute node states from runner events.

    Returns mapping: node_id -> state ('pending'|'running'|'success'|'skipped'|'error').
    """

    states: Dict[str, str] = {n.id: "pending" for n in plan.graph}
    for ev in events:
        t = ev.get("type")
        node_id = ev.get("node")
        if not node_id or node_id not in states:
            continue
        if t == "node_start":
            states[node_id] = "running"
        elif t == "node_finish":
            states[node_id] = "success"
        elif t == "node_skip":
            states[node_id] = "skipped"
        elif t == "error":
            states[node_id] = "error"
    return states


def draw_plan_dag(plan: Plan, node_states: Dict[str, str] | None = None):
    """Draw a simple DAG figure with node state colors.

    Returns a matplotlib Figure object.
    """

    node_states = node_states or {n.id: "pending" for n in plan.graph}
    g = _extract_edges(plan)
    pos = nx.spring_layout(g, seed=42) if len(g) > 1 else {n: (0.0, 0.0) for n in g.nodes}

    color_map = {
        "pending": "#9e9e9e",
        "running": "#1e88e5",
        "success": "#4caf50",
        "skipped": "#fbc02d",
        "error": "#e53935",
    }
    node_colors = [color_map.get(node_states.get(n, "pending"), "#9e9e9e") for n in g.nodes]

    fig, ax = plt.subplots(figsize=(6, 4))
    nx.draw_networkx_nodes(g, pos, node_color=node_colors, node_size=900, ax=ax)
    nx.draw_networkx_labels(g, pos, labels={n: n for n in g.nodes}, font_size=8, ax=ax)
    nx.draw_networkx_edges(g, pos, arrows=True, arrowstyle="-|>", ax=ax)
    ax.axis("off")
    fig.tight_layout()
    return fig


