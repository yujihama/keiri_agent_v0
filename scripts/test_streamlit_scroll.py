#!/usr/bin/env python3
"""
Streamlitでのスクロール機能をテストするスクリプト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import streamlit as st
    from ui.flow_viz import render_flow_html
    from core.plan.models import Plan, Node

    def create_test_plan():
        """テスト用のプランを作成"""
        plan = Plan(id="test_scroll_plan", version="1.0", graph=[])

        # テストノードを作成
        nodes = []
        for i in range(15):  # 多めのノードでスクロールテスト
            node = Node(
                id=f"test_node_{i}",
                description=f"テストノード {i} - スクロール確認用"
            )
            nodes.append(node)

        plan.graph = nodes
        return plan

    def main():
        st.title("Flow Scroll Test - Streamlit")

        st.write("""
        このページでStreamlit環境でのフロー自動スクロール機能をテストします。
        実行中のノードが自動的に画面中央にスクロールされるはずです。
        """)

        # テストプラン作成
        plan = create_test_plan()

        # ノード状態の選択
        st.subheader("ノード状態設定")
        running_node = st.selectbox(
            "実行中にするノードを選択:",
            [f"test_node_{i}" for i in range(15)],
            index=7  # デフォルトで中央付近のノード
        )

        # ノード状態の作成
        node_states = {}
        for i in range(15):
            node_id = f"test_node_{i}"
            if node_id == running_node:
                node_states[node_id] = "running"
            elif i < int(running_node.split('_')[-1]):
                node_states[node_id] = "success"
            else:
                node_states[node_id] = "pending"

        st.subheader("フロー表示")
        st.write(f"実行中ノード: **{running_node}**")

        # フロー表示（スクロール機能付き）
        render_flow_html(plan, node_states)

        st.info("""
        **期待される動作:**
        - 実行中のノードが青い枠線とアニメーションで強調される
        - 自動的に実行中ノードが画面中央にスクロールされる
        - ブラウザのコンソールにスクロールログが表示される

        スクロールが動作しない場合は、ブラウザの開発者ツールを開いてコンソールを確認してください。
        """)

    if __name__ == "__main__":
        main()

except Exception as e:
    print(f"エラーが発生しました: {e}")
    import traceback
    traceback.print_exc()
