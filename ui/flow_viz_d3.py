"""
D3.jsを使用した高度なフロー図可視化モジュール
"""
from __future__ import annotations

from typing import Dict, List, Optional
import json
import streamlit as st
import streamlit.components.v1 as components

from core.plan.models import Plan, Node


class D3FlowRenderer:
    """D3.jsを使用した対話型フロー図レンダラー"""
    
    @staticmethod
    def prepare_graph_data(plan: Plan, states: Dict[str, str]) -> Dict:
        """
        D3.js用のグラフデータを準備
        
        Returns:
            nodes と links を含む辞書
        """
        # 依存関係グラフを構築
        try:
            from core.plan.graph_utils import build_dependency_graph
            import networkx as nx
            dep_graph = build_dependency_graph(plan)
            
            # 階層レベルを計算（トポロジカルソート）
            node_levels = {}
            try:
                for level, nodes_in_level in enumerate(nx.topological_generations(dep_graph)):
                    for node_id in nodes_in_level:
                        node_levels[node_id] = level
            except (nx.NetworkXError, Exception):
                # エラーの場合は順序で割り当て
                for i, node in enumerate(plan.graph):
                    node_levels[node.id] = 0  # 全て同じレベル
                    
        except Exception:
            # インポートエラーなど
            dep_graph = None
            node_levels = {}
            for i, node in enumerate(plan.graph):
                node_levels[node.id] = 0
        
        nodes = []
        links = []
        node_indices = {}
        
        # ノードデータの準備（階層レベル情報を追加）
        for i, node in enumerate(plan.graph):
            node_indices[node.id] = i
            nodes.append({
                "id": node.id,
                "index": i,
                "label": node.id,
                "description": getattr(node, "description", ""),
                "state": states.get(node.id, "pending"),
                "level": node_levels.get(node.id, 0),  # 階層レベル
                "x": None,  # D3.jsが自動計算
                "y": None
            })
        
        # 依存関係グラフからエッジを追加
        if dep_graph is not None:
            # エッジの重複カウントを計算
            edge_counts = {}
            for src, dst in dep_graph.edges():
                if src in node_indices and dst in node_indices:
                    source_idx = node_indices[src]
                    target_idx = node_indices[dst]
                    
                    # 同じノード間のエッジをカウント
                    edge_key = f"{source_idx}-{target_idx}"
                    if edge_key not in edge_counts:
                        edge_counts[edge_key] = 0
                    
                    links.append({
                        "source": source_idx,
                        "target": target_idx,
                        "edge_index": edge_counts[edge_key],  # 重複回避用インデックス
                        "edge_id": edge_key
                    })
                    
                    edge_counts[edge_key] += 1
        else:
            # フォールバック: シーケンシャルなリンクを作成
            for i in range(len(plan.graph) - 1):
                links.append({
                    "source": i,
                    "target": i + 1,
                    "edge_index": 0,
                    "edge_id": f"{i}-{i+1}"
                })
        
        return {"nodes": nodes, "links": links}
    
    @staticmethod
    def render_interactive(
        plan: Plan,
        states: Dict[str, str],
        width: int = 800,
        height: int = 400,
        placeholder=None
    ) -> None:
        """
        インタラクティブなD3.jsフロー図をレンダリング
        """
        graph_data = D3FlowRenderer.prepare_graph_data(plan, states)
        
        # 文字列生成はf-stringを避け、後段で置換して波括弧の衝突を防ぐ
        graph_json = json.dumps(graph_data)
        plan_id_js = json.dumps(str(getattr(plan, 'id', '')))

        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <script src="https://d3js.org/d3.v7.min.js"></script>
            <script src="https://cdn.jsdelivr.net/npm/elkjs@0.9.2/lib/elk.bundled.js"></script>
            
            <style>
                #graph-container {{
                    width: __WIDTH__px;
                    height: __HEIGHT__px;
                    border: 1px solid #ddd;
                    border-radius: 8px;
                    overflow: hidden;
                    position: relative;
                }}
                
                .node {{
                    cursor: pointer;
                }}
                
                .node-pending {{ fill: #f9f9f9; stroke: #666; stroke-width: 2px; }}
                .node-running {{ fill: #E3F2FD; stroke: #2196F3; stroke-width: 3px; animation: pulse 1.5s infinite; }}
                .node-success {{ fill: #E8F5E9; stroke: #4CAF50; stroke-width: 3px; }}
                .node-error {{ fill: #FFEBEE; stroke: #F44336; stroke-width: 3px; }}
                .node-skipped {{ fill: #FFF3E0; stroke: #FF9800; stroke-width: 3px; }}
                
                @keyframes pulse {{
                    0%, 100% {{ opacity: 1; }}
                    50% {{ opacity: 0.7; }}
                }}
                
                .node-label {{
                    font-family: Arial, sans-serif;
                    font-size: 12px;
                    text-anchor: middle;
                    pointer-events: none;
                }}
                
                .link {{
                    fill: none;
                    stroke: #666;
                    stroke-width: 2.5px;
                    opacity: 0.7;
                    transition: all 0.3s ease;
                    stroke-linecap: round;
                    stroke-linejoin: round;  // 角の丸み復活
                    cursor: pointer;
                }}
                
                .link:hover {{
                    stroke: #2196F3;
                    stroke-width: 4px;
                    opacity: 1;
                    filter: drop-shadow(0 0 6px rgba(33, 150, 243, 0.6));
                }}
                
                .link-multiple {{
                    stroke-width: 2px;  // 複数エッジも適度な太さ
                    opacity: 0.6;
                    stroke-dasharray: 5, 5;  // 複数エッジは破線で区別
                }}
                
                .link-focused {{
                    stroke: #4CAF50;
                    stroke-width: 4px;
                    opacity: 1;
                    filter: drop-shadow(0 0 8px rgba(76, 175, 80, 0.8));
                    z-index: 10;
                }}
                
                .link-animated {{
                    stroke-dasharray: 8, 4;
                    animation: flow-animation 3s linear infinite;
                }}
                
                @keyframes flow-animation {{
                    0% {{ stroke-dashoffset: 0; }}
                    100% {{ stroke-dashoffset: -12; }}
                }}
                
                .tooltip {{
                    position: absolute;
                    text-align: center;
                    padding: 8px;
                    font: 12px sans-serif;
                    background: rgba(0, 0, 0, 0.8);
                    color: white;
                    border-radius: 4px;
                    pointer-events: none;
                    opacity: 0;
                    transition: opacity 0.3s;
                }}
            </style>
        </head>
        <body>
            <div id="graph-container"></div>
            <div class="tooltip"></div>
            
            <script>
                // グラフデータ
                const graphData = __GRAPH_JSON__;
                const planId = __PLAN_ID__;
                const LAYOUT_KEY = `flow_layout_${planId}`;
                function loadLayout() {
                    try { const raw = localStorage.getItem(LAYOUT_KEY); return raw ? JSON.parse(raw) : null; } catch (e) { return null; }
                }
                function saveLayout(obj) { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(obj)); } catch (e) {} }
                function buildSignature() {
                    try {
                        const n = graphData.nodes.map(n => n.id);
                        const e = graphData.links.map(l => `${l.source}-${l.target}-${l.edge_id}`);
                        return JSON.stringify({ n, e });
                    } catch (e) { return ""; }
                }
                
                // SVG設定
                const width = __WIDTH__;
                const height = __HEIGHT__;
                const margin = {{top: 20, right: 20, bottom: 20, left: 20}};
                
                // SVG要素の作成
                const svg = d3.select("#graph-container")
                    .append("svg")
                    .attr("width", width)
                    .attr("height", height);
                
                // ズーム機能の追加
                const g = svg.append("g");
                // saveTransform は無効（位置自動保存なし）だが呼び出し互換のためダミー
                function saveTransform(_) {}
                const zoom = d3.zoom()
                    .scaleExtent([0.5, 3])
                    .on("zoom", (event) => {
                        g.attr("transform", event.transform);
                        saveTransform(event.transform);
                    });
                svg.call(zoom);
                
                // 矢印マーカーは削除（シンプルな線のみ使用）
                
                // レイアウト・描画パラメータ（コード内で定義）
                const nodeWidth = 100;
                const nodeHeight = 50;
                const elkLayerSpacing = 30;
                const elkNodeNodeSpacing = 30;
                const lineGen = d3.line().x(p => p.x).y(p => p.y).curve(d3.curveLinear);
                function applyStateStyles() {
                    node.select('rect').attr('class', d => `node-${d.state}`);
                    link.each(function(d) {
                        const sIdx = (typeof d.source === 'object') ? d.source.index : d.source;
                        const tIdx = (typeof d.target === 'object') ? d.target.index : d.target;
                        const sourceState = graphData.nodes[sIdx]?.state;
                        const targetState = graphData.nodes[tIdx]?.state;
                        const isRunning = sourceState === 'running' || targetState === 'running';
                        const hasMultiple = (d.edge_index || 0) > 0;
                        d3.select(this)
                          .classed('link-animated', isRunning)
                          .classed('link-multiple', hasMultiple)
                          .style('stroke', isRunning ? '#2196F3' : '#999');
                    });
                }
                
                // リンクの描画（矢印なしの曲線）
                const link = g.append("g")
                    .selectAll("path")
                    .data(graphData.links)
                    .enter().append("path")
                    .attr("class", "link")
                    .attr("fill", "none")
                    .attr("stroke", "#999")
                    .attr("stroke-width", 2);
                
                // ノードグループの作成
                const node = g.append("g")
                    .selectAll("g")
                    .data(graphData.nodes)
                    .enter().append("g")
                    .attr("class", "node");
                
                // ノードの矩形を追加（サイズを大きくして重複を避ける）
                node.append("rect")
                    .attr("width", 100)  // 幅を増加
                    .attr("height", 50)  // 高さを増加
                    .attr("x", -50)      // 中央揃え
                    .attr("y", -25)      // 中央揃え
                    .attr("rx", 10)
                    .attr("ry", 10)
                    .attr("class", d => `node-${{d.state}}`);
                
                // ノードラベルを追加
                node.append("text")
                    .attr("class", "node-label")
                    .attr("dy", 4)
                    .style("font-size", "12px")
                    .style("font-weight", "bold")
                    .style("text-anchor", "middle")
                    .text(d => {{
                        // 長いテキストを省略
                        const maxLength = 12;
                        return d.label.length > maxLength ? 
                            d.label.substring(0, maxLength) + '...' : 
                            d.label;
                    }});
                
                // ツールチップの設定
                const tooltip = d3.select(".tooltip");
                node.on("mouseover", function(event, d) {{
                    tooltip.transition().duration(200).style("opacity", .9);
                    tooltip.html(`<strong>${{d.label}}</strong><br/>${{d.description || 'No description'}}`)
                        .style("left", (event.pageX + 10) + "px")
                        .style("top", (event.pageY - 28) + "px");
                }})
                .on("mouseout", function(d) {{
                    tooltip.transition().duration(500).style("opacity", 0);
                }});
                
                // 差分描画 + ELK座標キャッシュ
                const signature = buildSignature();
                const cached = loadLayout();

                function drawLinksFromSectionsMap(sectionsMap) {
                    link.attr('d', d => {
                        const pts = sectionsMap && sectionsMap[d.edge_id];
                        if (!pts) return null;
                        return lineGen(pts);
                    });
                }

                if (cached && cached.signature === signature && cached.positions) {
                    try {
                        const positions = cached.positions || {};
                        graphData.nodes.forEach(n => {
                            const p = positions[String(n.index)];
                            if (p) { n.x = p.x; n.y = p.y; }
                        });
                        node.attr('transform', d => `translate(${d.x},${d.y})`);
                        if (cached.requiredWidth && cached.requiredWidth > width) {
                            d3.select('#graph-container svg').attr('width', cached.requiredWidth);
                        }
                        drawLinksFromSectionsMap(cached.sections || {});
                        applyStateStyles();
                    } catch (e) {
                        runElkAndRender();
                    }
                } else {
                    runElkAndRender();
                }

                function runElkAndRender() {
                    const elk = new ELK();
                    const elkGraph = {
                        id: 'root',
                        layoutOptions: {
                            'elk.algorithm': 'layered',
                            'elk.direction': 'RIGHT',
                            'elk.edgeRouting': 'ORTHOGONAL',
                            'elk.spacing.nodeNode': String(elkNodeNodeSpacing),
                            'elk.layered.spacing.nodeNodeBetweenLayers': String(elkLayerSpacing),
                            'elk.layered.considerModelOrder': 'true'
                        },
                        children: graphData.nodes.map(n => ({ id: String(n.index), width: nodeWidth, height: nodeHeight })),
                        edges: graphData.links.map(l => ({ id: l.edge_id, sources: [String(l.source)], targets: [String(l.target)] }))
                    };
                    elk.layout(elkGraph).then(layout => {
                        const childIndex = Object.fromEntries((layout.children || []).map(c => [c.id, c]));
                        graphData.nodes.forEach(n => {
                            const c = childIndex[String(n.index)];
                            if (c) { n.x = c.x + c.width / 2; n.y = c.y + c.height / 2; }
                        });
                        node.attr('transform', d => `translate(${d.x},${d.y})`);
                        const edgeIndex = Object.fromEntries((layout.edges || []).map(e => [e.id, e]));
                        const sectionsMap = {};
                        link.attr('d', d => {
                            const e = edgeIndex[d.edge_id];
                            if (!e || !e.sections || !e.sections.length) return null;
                            const s = e.sections[0];
                            const pts = [s.startPoint].concat(s.bendPoints || [], [s.endPoint]);
                            sectionsMap[d.edge_id] = pts;
                            return lineGen(pts);
                        });
                        applyStateStyles();
                        let requiredWidth = width;
                        try {
                            const xs = graphData.nodes.map(n => n.x);
                            const ys = graphData.nodes.map(n => n.y);
                            if (xs.length && ys.length) {
                                const minX = Math.min(...xs) - (nodeWidth/2 + 40);
                                const maxX = Math.max(...xs) + (nodeWidth/2 + 40);
                                requiredWidth = Math.max(width, maxX - minX + 40);
                                if (requiredWidth > width) {
                                    d3.select('#graph-container svg').attr('width', requiredWidth);
                                }
                            }
                        } catch (e) {}
                        try {
                            const positions = {};
                            graphData.nodes.forEach(n => { positions[String(n.index)] = { x: n.x, y: n.y }; });
                            saveLayout({ signature, positions, sections: sectionsMap, requiredWidth });
                        } catch (e) {}
                    });
                }
                
                // ノードクリック時に関連エッジをハイライト
                let selectedNode = null;
                
                node.on("click", function(event, d) {{
                    // 前回の選択をクリア
                    link.classed("link-focused", false);
                    node.selectAll("rect").style("stroke-width", d => d.state === "running" ? "3px" : "2px");
                    
                    if (selectedNode === d.id) {{
                        // 同じノードを再クリックした場合は選択解除
                        selectedNode = null;
                    }} else {{
                        // 新しいノードを選択
                        selectedNode = d.id;
                        
                        // 関連エッジをハイライト
                        link.classed("link-focused", linkData => {{
                            const sIdx = (typeof linkData.source === 'object') ? linkData.source.index : linkData.source;
                            const tIdx = (typeof linkData.target === 'object') ? linkData.target.index : linkData.target;
                            const sourceId = graphData.nodes[sIdx]?.id;
                            const targetId = graphData.nodes[tIdx]?.id;
                            return sourceId === d.id || targetId === d.id;
                        }});
                        
                        // 選択ノードをハイライト
                        d3.select(this).select("rect").style("stroke-width", "4px");
                    }}
                }})
                .on("dblclick", function(event, d) {{
                    // ダブルクリックで詳細表示
                    const connectedNodes = [];
                    link.each(linkData => {{
                        const sIdx = (typeof linkData.source === 'object') ? linkData.source.index : linkData.source;
                        const tIdx = (typeof linkData.target === 'object') ? linkData.target.index : linkData.target;
                        const sourceId = graphData.nodes[sIdx]?.id;
                        const targetId = graphData.nodes[tIdx]?.id;
                        if (sourceId === d.id) connectedNodes.push(targetId);
                        if (targetId === d.id) connectedNodes.push(sourceId);
                    }});
                    
                    alert(`Node: ${{d.label}}\\nState: ${{d.state}}\\nDescription: ${{d.description || 'N/A'}}\\nConnected to: ${{connectedNodes.join(', ') || 'None'}}`);
                }});
                
            </script>
        </body>
        </html>
        """

        # 置換: 幅・高さ
        html_content = (
            html_template
            .replace("__WIDTH__", str(width))
            .replace("__HEIGHT__", str(height))
        )
        # f-string衝突回避のため、二重波括弧を単一に変換
        html_content = html_content.replace("{{", "{").replace("}}", "}")
        # 最後にグラフJSON/PlanIDを注入
        html_content = html_content.replace("__GRAPH_JSON__", graph_json)
        html_content = html_content.replace("__PLAN_ID__", plan_id_js)
        
        if placeholder:
            # プレースホルダーをクリアしてから描画
            placeholder.empty()
            with placeholder.container():
                components.html(html_content, height=height + 100, scrolling=True)
        else:
            components.html(html_content, height=height + 100, scrolling=True)


