from __future__ import annotations

from typing import Any, Dict, Iterable

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
    for nid in list(success_nodes):
        states[str(nid)] = "success"
    return states


def render_flow_html(plan, states: Dict[str, str], *, include_loop_nodes: bool = False, placeholder=None) -> None:
    from core.plan.dag_viz import generate_flow_html

    html = generate_flow_html(plan, states, include_loop_nodes=include_loop_nodes)
    area = placeholder or st
    area.markdown(html, unsafe_allow_html=True)


