"""
フロー図表示の問題をデバッグするスクリプト
"""
import sys
import traceback
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=== フロー図表示デバッグ ===")

# 1. 基本的なインポートテスト
print("\n1. 基本インポートテスト")
try:
    from core.plan.loader import load_plan
    print("✓ load_plan インポート成功")
except Exception as e:
    print(f"✗ load_plan インポートエラー: {e}")
    traceback.print_exc()

try:
    from ui.flow_viz import init_success_nodes_namespace, render_flow_html
    print("✓ flow_viz インポート成功")
except Exception as e:
    print(f"✗ flow_viz インポートエラー: {e}")
    traceback.print_exc()

# 2. プランロードテスト
print("\n2. プランロードテスト")
try:
    designs_dir = project_root / "designs"
    plan_files = list(designs_dir.glob("*.yaml"))
    
    if plan_files:
        test_plan_path = plan_files[0]
        print(f"テストプラン: {test_plan_path}")
        
        plan = load_plan(test_plan_path)
        print(f"✓ プランロード成功: {plan.id}")
        print(f"  ノード数: {len(plan.graph)}")
        
        # ノード情報を表示
        for i, node in enumerate(plan.graph[:3]):  # 最初の3つのノードのみ
            print(f"  Node {i}: {node.id}")
            
    else:
        print("✗ テスト用プランファイルが見つかりません")
        
except Exception as e:
    print(f"✗ プランロードエラー: {e}")
    traceback.print_exc()

# 3. 依存関係グラフテスト
print("\n3. 依存関係グラフテスト")
try:
    from core.plan.graph_utils import build_dependency_graph
    import networkx as nx
    
    if 'plan' in locals():
        dep_graph = build_dependency_graph(plan)
        print(f"✓ 依存関係グラフ構築成功")
        print(f"  ノード数: {len(dep_graph.nodes)}")
        print(f"  エッジ数: {len(dep_graph.edges)}")
        
        # トポロジカルソート テスト
        try:
            levels = list(nx.topological_generations(dep_graph))
            print(f"✓ トポロジカルソート成功: {len(levels)} レベル")
        except nx.NetworkXError as e:
            print(f"! トポロジカルソートエラー (循環依存): {e}")
        
except Exception as e:
    print(f"✗ 依存関係グラフエラー: {e}")
    traceback.print_exc()

# 4. D3.jsレンダラーのテスト
print("\n4. D3.jsレンダラーテスト")

try:
    from ui.flow_viz_d3 import D3FlowRenderer
    print("✓ D3.js レンダラー インポート成功")
    
    if 'plan' in locals():
        states = {node.id: "pending" for node in plan.graph}
        # 実行中ノードを1つ設定
        if plan.graph:
            states[plan.graph[0].id] = "running"
            
        graph_data = D3FlowRenderer.prepare_graph_data(plan, states)
        print(f"✓ D3データ準備成功")
        print(f"  ノード数: {len(graph_data['nodes'])}")
        print(f"  エッジ数: {len(graph_data['links'])}")
        
        # 各ノードの情報を表示
        for i, node_data in enumerate(graph_data['nodes'][:5]):  # 最初の5つだけ
            print(f"  Node {i}: {node_data['id']} ({node_data['state']})")
        
        # エッジ情報も表示
        for i, link_data in enumerate(graph_data['links'][:5]):  # 最初の5つだけ
            print(f"  Link {i}: {link_data['source']} -> {link_data['target']}")
            
except Exception as e:
    print(f"✗ D3.js レンダラーエラー: {e}")
    traceback.print_exc()

# 5. レガシーレンダラーのテスト（フォールバック用）
print("\n5. レガシーレンダラーテスト（フォールバック確認）")
try:
    from ui.flow_viz import render_flow_html_legacy
    print("✓ legacy レンダラー インポート成功")
except Exception as e:
    print(f"✗ legacy レンダラーエラー: {e}")
    traceback.print_exc()

print("\n=== デバッグ完了 ===")

# 推奨事項
print("\n推奨事項:")
print("1. エラーがある場合は、該当部分の修正が必要です")
print("2. 全て成功の場合は、Streamlitアプリの問題の可能性があります")
print("3. 環境変数 KEIRI_USE_LEGACY_FLOW=true で一時回避できます")
