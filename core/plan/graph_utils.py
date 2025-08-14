from __future__ import annotations

from typing import Any

import networkx as nx

from .models import Plan


def build_dependency_graph(plan: Plan) -> nx.DiGraph:
    """Build a dependency DAG for a Plan by scanning placeholder references.

    - Edges are added from a source node to a destination node when the
      destination's inputs (or loop conditions) contain a placeholder of the
      form "${src.alias[...]}", excluding ${vars.*}, ${env.*}, and ${config.*}.
    - Supports placeholders embedded within longer strings.
    - Handles basic foreach/while loop references.
    """

    g = nx.DiGraph()
    for n in plan.graph:
        g.add_node(n.id)

    def _add_edges_from_placeholders(text: str, dest_id: str) -> None:
        i = 0
        while i < len(text):
            if text[i : i + 2] == "${":
                j = text.find("}", i + 2)
                if j == -1:
                    break
                inner = text[i + 2 : j]
                if not inner.startswith(("vars.", "env.", "config.")) and "." in inner:
                    src = inner.split(".", 1)[0]
                    if src:
                        g.add_edge(src, dest_id)
                i = j + 1
            else:
                i += 1

    def _add_edges_from_value(val: Any, dest_id: str) -> None:
        if isinstance(val, str):
            _add_edges_from_placeholders(val, dest_id)
        elif isinstance(val, dict):
            for vv in val.values():
                _add_edges_from_value(vv, dest_id)
        elif isinstance(val, (list, tuple)):
            for vv in val:
                _add_edges_from_value(vv, dest_id)

    for n in plan.graph:
        if getattr(n, "type", None):
            # foreach loop input reference
            if n.type == "loop" and n.foreach and isinstance(n.foreach.get("input"), str):
                _add_edges_from_placeholders(str(n.foreach.get("input")), n.id)
            # while loop condition reference
            if n.type == "loop" and n.while_:
                cond = n.while_.get("condition", {}) if isinstance(n.while_, dict) else {}
                expr = cond.get("expr") if isinstance(cond, dict) else None
                if isinstance(expr, str):
                    _add_edges_from_placeholders(expr, n.id)
            # subflow edges are not analyzed here
            continue
        for v in getattr(n, "inputs", {}).values():
            _add_edges_from_value(v, n.id)

    return g


