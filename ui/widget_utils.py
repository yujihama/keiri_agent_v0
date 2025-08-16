from __future__ import annotations

import streamlit as st


def clear_ui_widget_state_for_plan(plan) -> None:
    """Remove Streamlit widget states associated with UI nodes of the plan."""
    widget_prefixes = [
        "file_", "files_", "folder_", "text_", "select_", "bool_", "number_", "chat_",
        "value_", "collect_form_",
    ]
    try:
        nodes = list(getattr(plan, "graph", []) or [])
    except Exception:
        nodes = []

    node_ids: list[str] = []
    for n in nodes:
        try:
            if getattr(n, "block", None) and str(n.block).startswith("ui."):
                node_ids.append(str(n.id))
        except Exception:
            continue

    keys_to_remove: list[str] = []
    for key in list(st.session_state.keys()):
        for nid in node_ids:
            for pref in widget_prefixes:
                if key.startswith(f"{pref}{nid}"):
                    keys_to_remove.append(key)
                    break
        if key.startswith(f"chat_history::{plan.id}::"):
            keys_to_remove.append(key)
    for k in keys_to_remove:
        try:
            del st.session_state[k]
        except Exception:
            pass


