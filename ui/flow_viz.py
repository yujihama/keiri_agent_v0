from __future__ import annotations

from typing import Any, Dict, Iterable
import re
import time

import streamlit as st

from ui.state_keys import SessionKeys


def init_success_nodes_namespace(plan_id: str) -> set[str]:
    key = SessionKeys.flow_success(plan_id)
    succ = st.session_state.get(key)
    if succ is None:
        succ = set()
        st.session_state[key] = succ
    elif isinstance(succ, list):
        succ = set(succ)
        st.session_state[key] = succ
    return succ


def persist_success_nodes(plan_id: str, states: Dict[str, str]) -> set[str]:
    succ = init_success_nodes_namespace(plan_id)
    for nid, stt in states.items():
        if stt == "success":
            succ.add(str(nid))
    st.session_state[SessionKeys.flow_success(plan_id)] = succ
    return succ


def mark_success_on_states(states: Dict[str, str], success_nodes: Iterable[str]) -> Dict[str, str]:
    # running を上書きしないようにする（表示の瞬断防止）
    for nid in list(success_nodes):
        key = str(nid)
        if states.get(key) != "running":
            states[key] = "success"
    return states


def render_flow_html_legacy(
    plan,
    states: Dict[str, str],
    *,
    include_loop_nodes: bool = False,
    placeholder=None,
    throttle_ms: int | None = None,
) -> None:
    from core.plan.dag_viz import generate_flow_html

    # Optional throttling to avoid frequent full re-renders (reduces flicker)
    if throttle_ms is not None:
        try:
            key = f"{SessionKeys.flow_last_render(getattr(plan, 'id', ''))}"
            now = time.time()
            last = st.session_state.get(key, 0.0)
            if (now - float(last)) < (float(throttle_ms) / 1000.0):
                return
            st.session_state[key] = now
        except Exception:
            # Best-effort; never block rendering on throttling errors
            pass

    # Find running node for auto-scroll positioning
    running_node_id = None
    for node_id, state in states.items():
        if state == "running":
            running_node_id = node_id
            break

    # If no running node, find the last success node
    if not running_node_id:
        success_nodes = [(node_id, i) for i, (node_id, state) in enumerate(states.items()) if state == "success"]
        if success_nodes:
            running_node_id = success_nodes[-1][0]  # Last success node

    html = generate_flow_html(plan, states, include_loop_nodes=include_loop_nodes)
    area = placeholder or st

    # Debug: Check HTML structure (disabled)
    # print(f"[flow] Generated HTML length: {len(html)}")
    # print(f"[flow] Running node ID: {running_node_id}")
    # print(f"[flow] HTML preview: {html[:200]}...")

    # Add minimal auto-scroll functionality without breaking layout
    if running_node_id:
        # Add a simple script that runs after DOM is ready
        auto_scroll_script = f'''
        <script>
        // Minimal auto-scroll implementation
        function scrollToRunningNode() {{
            const runningNode = document.querySelector('.flow-node.running');
            if (runningNode) {{
                console.log('[flow] Found running node, scrolling...');
                runningNode.scrollIntoView({{
                    behavior: 'smooth',
                    block: 'center',
                    inline: 'center'
                }});
            }}
        }}

        // Run once after page load
        if (document.readyState === 'complete') {{
            setTimeout(scrollToRunningNode, 500);
        }} else {{
            window.addEventListener('load', function() {{
                setTimeout(scrollToRunningNode, 500);
            }});
        }}
        </script>
        '''
        final_html = html + auto_scroll_script
    else:
        final_html = html

    # Debug: Check final HTML (disabled)
    # print(f"[flow] Final HTML length: {len(final_html)}")
    # print(f"[flow] Final HTML preview: {final_html[:300]}...")

    area.markdown(final_html, unsafe_allow_html=True)


def render_flow_html(
    plan,
    states: Dict[str, str],
    *,
    include_loop_nodes: bool = False,
    placeholder=None,
    throttle_ms: int | None = None,
) -> None:
    """
    D3.js専用のフロー図レンダリング
    """
    from ui.flow_viz_config import get_flow_config, is_dev_mode
    import os
    
    # レガシー表示への一時的な切り替え
    use_legacy = os.getenv("KEIRI_USE_LEGACY_FLOW", "false").lower() == "true"
    if use_legacy:
        render_flow_html_legacy(
            plan, states, 
            include_loop_nodes=include_loop_nodes,
            placeholder=placeholder,
            throttle_ms=throttle_ms
        )
        return
    
    # D3.js表示を使用
    try:
        from ui.flow_viz_d3 import D3FlowRenderer
        
        config = get_flow_config()
        
        # 成功ノード管理
        plan_id = getattr(plan, 'id', '')
        success_nodes = init_success_nodes_namespace(plan_id)
        states = mark_success_on_states(states, success_nodes)
        persist_success_nodes(plan_id, states)
        
        # D3.jsでレンダリング
        D3FlowRenderer.render_interactive(
            plan, states,
            width=config["width"],
            height=config["height"],
            placeholder=placeholder
        )
    except Exception as e:
        # エラーの場合はレガシー実装にフォールバック
        print(f"[flow] D3.js実装でエラー: {e}")
        render_flow_html_legacy(
            plan, states,
            include_loop_nodes=include_loop_nodes,
            placeholder=placeholder,
            throttle_ms=throttle_ms
        )

