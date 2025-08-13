from __future__ import annotations

from typing import Any, Dict
import os

import streamlit as st

from core.blocks.base import BlockContext, UIBlock


class ConfirmationUIBlock(UIBlock):
    id = "ui.confirmation"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # HITLで待機するケースもあるが、通常実行では即時UI表示
        if os.getenv("KEIRI_AGENT_HEADLESS", "0") == "1":
            return {"approved": True, "comment": None, "metadata": {"submitted": True}}
        message = inputs.get("message") or "確認してください"
        options = inputs.get("options") or ["approve", "reject"]
        key_base = str(inputs.get("widget_key") or ctx.run_id)

        # 既に確定済みならサマリー表示のみ
        sub_key = f"confirm_submitted_{key_base}"
        snap_key = f"confirm_snapshot_{key_base}"
        if st.session_state.get(sub_key):
            snap = st.session_state.get(snap_key, {})
            st.success("確認済み")
            with st.expander("確認内容", expanded=True):
                st.json(snap)
            return {**snap, "metadata": {"submitted": True}}

        st.info(message)
        choice_key = f"confirm_sel_{key_base}"
        comment_key = f"confirm_comment_{key_base}"
        choice = st.selectbox("選択", options=options, key=choice_key)
        comment = st.text_input("コメント", value=st.session_state.get(comment_key, ""), key=comment_key)
        approved = True if str(choice).lower() == "approve" else False
        decided = st.button("決定", key=f"confirm_decide_{key_base}")
        if decided:
            snap = {"approved": approved, "comment": comment}
            st.session_state[sub_key] = True
            st.session_state[snap_key] = snap
            st.success("確認しました")
            with st.expander("確認内容", expanded=True):
                st.json(snap)
            return {**snap, "metadata": {"submitted": True}}
        # 未確定時は暫定値（submitted=False）を返す
        return {"approved": approved, "comment": comment, "metadata": {"submitted": False}}


