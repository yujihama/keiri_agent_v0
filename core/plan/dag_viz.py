from __future__ import annotations

from typing import Any, Dict, List, Tuple
import re
import textwrap

import matplotlib

# Use non-interactive backend for headless/test environments
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx  # noqa: E402
import matplotlib.font_manager as fm  # noqa: E402

from .models import Plan, Node
from .graph_utils import build_dependency_graph


def generate_flow_html(plan: Plan, node_states: Dict[str, str] | None = None, include_loop_nodes: bool = False) -> str:
    """Generate HTML/CSS for flow visualization using modern design.

    Note: The returned string must start with a non-indented HTML tag to avoid
    Markdown treating it as a code block. We therefore dedent and strip styles
    and return a concatenated HTML string without leading spaces.
    """
    
    # Build display nodes
    nodes_list = []
    for n in plan.graph:
        if getattr(n, "type", None) == "loop":
            # Add the loop node itself with its description
            nodes_list.append(n)
        elif getattr(n, "type", None) != "loop":
            nodes_list.append(n)
    
    if not nodes_list:
        return "<div>No nodes to display</div>"
    
    node_states = node_states or {n.id: "pending" for n in nodes_list}

    def _slug(s: str) -> str:
        try:
            return re.sub(r"[^A-Za-z0-9_-]+", "-", str(s))
        except Exception:
            return ""

    # CSS styles for modern look
    styles = textwrap.dedent(
        """
        <style>
            .flow-container {
                display: flex;
                flex-wrap: wrap;
                gap: 12px 20px;
                padding: 16px 20px;
                overflow: auto;
                align-items: stretch;
                align-content: flex-start;
                max-height: 220px;
                background: #f8f9fa;
                border-radius: 12px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }

            .flow-node {
                position: relative;
                flex: 0 0 220px;
                min-width: 200px;
                padding: 16px 20px;
                background: white;
                border-radius: 12px;
                box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
                text-align: center;
                transition: all 0.3s ease;
                border: 3px solid #e0e0e0;
            }

            .flow-node.pending {
                border-color: #e0e0e0;
                background: #ffffff;
            }

            .flow-node.running {
                border-color: #2196F3;
                background: #E3F2FD;
                animation: pulse 1.5s ease-in-out infinite;
            }

            .flow-node.success {
                border-color: #4CAF50;
                background: #E8F5E9;
            }

            .flow-node.error {
                border-color: #F44336;
                background: #FFEBEE;
            }

            .flow-node.skipped {
                border-color: #FF9800;
                background: #FFF3E0;
            }

            @keyframes pulse {
                0%, 100% { transform: scale(1); box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1); }
                50% { transform: scale(1.02); box-shadow: 0 4px 20px rgba(33, 150, 243, 0.3); }
            }

            .node-id {
                font-size: 14px;
                font-weight: 600;
                color: #333;
                margin-bottom: 4px;
            }

            .node-description {
                font-size: 12px;
                color: #666;
                line-height: 1.4;
            }

            .flow-arrow {
                position: absolute;
                right: -20px;
                top: 50%;
                transform: translateY(-50%);
                width: 20px;
                height: 2px;
                background: #ddd;
            }

            .flow-arrow::after {
                content: '';
                position: absolute;
                right: -6px;
                top: -4px;
                width: 0;
                height: 0;
                border-left: 8px solid #ddd;
                border-top: 6px solid transparent;
                border-bottom: 6px solid transparent;
            }

            .flow-node:last-child .flow-arrow {
                display: none;
            }

            /* Wrap-friendly: always hide arrows to avoid misalignment across rows */
            .flow-container .flow-arrow { display: none !important; }

            .status-icon {
                position: absolute;
                top: -10px;
                right: -10px;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 14px;
                font-weight: bold;
                color: white;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
            }

            .status-icon.pending { background: #9E9E9E; }
            .status-icon.running { background: #2196F3; }
            .status-icon.success { background: #4CAF50; }
            .status-icon.error { background: #F44336; }
            .status-icon.skipped { background: #FF9800; }
        </style>
        """
    ).strip()
    
    # Generate HTML for nodes
    html_nodes = []
    for i, node in enumerate(nodes_list):
        state = node_states.get(node.id, "pending")
        
        # Status icons
        status_icons = {
            "pending": "⏸",
            "running": "▶",
            "success": "✓",
            "error": "✗",
            "skipped": "➜"
        }
        
        running_attr = ' data-running="1"' if state == "running" else ""
        node_id_safe = _slug(node.id)
        attrs = (
            f'class="flow-node {state}" '
            f'data-node-id="{node.id}" '
            f'data-state="{state}" '
            f'id="flow-node-{node_id_safe}"{running_attr}'
        )
        node_html = (
            f'<div {attrs}>'
            f'<div class="status-icon {state}">{status_icons.get(state, "?")}</div>'
            f'<div class="node-id">{node.id}</div>'
        )
        
        if hasattr(node, "description") and node.description:
            node_html += f'<div class="node-description">{node.description}</div>'
        
        if i < len(nodes_list) - 1:
            node_html += '<div class="flow-arrow"></div>'
        
        node_html += "</div>"
        html_nodes.append(node_html)
    
    # Combine everything
    _plan_id_safe = _slug(getattr(plan, "id", ""))
    container_id = f'flow-container-{_plan_id_safe}'
    return styles + '\n' + f'<div class="flow-container" id="{container_id}">' + ''.join(html_nodes) + '</div>'


# Try to configure a Japanese-capable font to avoid garbled labels
def _setup_japanese_font() -> str | None:
    try:
        candidates = [
            "Yu Gothic UI",
            "Yu Gothic",
            "Meiryo",
            "MS Gothic",
            "MS PGothic",
            "Noto Sans CJK JP",
            "Noto Sans JP",
            "TakaoPGothic",
            "IPAGothic",
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        for name in candidates:
            if name in available:
                matplotlib.rcParams["font.family"] = name
                matplotlib.rcParams["axes.unicode_minus"] = False
                return name
    except Exception:
        pass
    return None


_JP_FONT_NAME = _setup_japanese_font()


def _extract_edges(plan: Plan) -> nx.DiGraph:
    # Delegate to shared graph utility for consistency with runner
    return build_dependency_graph(plan)


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
        # UI/Loopイベントも反映
        if t in {"node_start", "ui_wait", "loop_start", "loop_iter_start"}:
            states[node_id] = "running"
        elif t in {"node_finish", "ui_submit", "ui_reuse", "loop_finish"}:
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


def draw_plan_linear(plan: Plan, node_states: Dict[str, str] | None = None, include_loop_nodes: bool = False):
    """Draw a simple linear flow in plan.graph order with state colors.

    - Order: as defined in plan.graph
    - Colors: running=blue, success=green, error=red, others=pending(gray)
    """
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    # Build display nodes: represent loops by their own description (do not expand body)
    class _DisplayNode:
        def __init__(self, id: str, description: str | None = None):
            self.id = id
            self.description = description
            self.type = None

    def _build_display_nodes(p: Plan) -> List[Node]:
        nodes_list: List[Node] = []
        for n in p.graph:
            if getattr(n, "type", None) == "loop":
                desc = getattr(n, "description", None)
                nodes_list.append(_DisplayNode(n.id, desc))
            else:
                nodes_list.append(n)
        return nodes_list

    nodes = _build_display_nodes(plan)

    # Initialize states for display nodes
    node_states = node_states or {n.id: "pending" for n in nodes}
    if not nodes:
        fig, ax = plt.subplots(figsize=(6, 1.5))
        ax.axis("off")
        ax.text(0.5, 0.5, "表示対象のノードがありません", ha="center", va="center")
        fig.tight_layout()
        return fig
    color_map = {
        "pending": "#9e9e9e",
        "running": "#1e88e5",
        "success": "#4caf50",
        "error": "#e53935",
        "skipped": "#9e9e9e",
    }
    n = len(nodes)
    fig_w = max(6, 1.8 * max(1, n))
    fig, ax = plt.subplots(figsize=(fig_w, 2.6))
    ax.axis("off")

    x = 0.0
    for idx, node in enumerate(nodes):
        state = node_states.get(node.id, "pending")
        color = color_map.get(state, "#9e9e9e")
        # box
        rect = Rectangle((x, 0.35), 1.6, 0.8, linewidth=0, facecolor=color)
        ax.add_patch(rect)
        # label
        label = node.id
        try:
            if getattr(node, "description", None):
                label = f"{node.id}\n{node.description}"
        except Exception:
            pass
        ax.text(x + 0.8, 0.75, label, ha="center", va="center", fontsize=14, color="#ffffff")
        # arrow to next
        if idx < n - 1:
            ax.annotate(
                "",
                xy=(x + 1.7, 0.75),
                xytext=(x + 1.8, 0.75),
                arrowprops=dict(arrowstyle='-|>', color="#757575", lw=1.0),
            )
        x += 1.8

    ax.set_xlim(-0.1, x + 0.3)
    ax.set_ylim(0.2, 1.4)
    fig.tight_layout()
    return fig

