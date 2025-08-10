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
            return {"approved": True, "comment": None}
        message = inputs.get("message") or "確認してください"
        options = inputs.get("options") or ["approve", "reject"]
        st.info(message)
        choice = st.selectbox("選択", options=options, key=f"confirm_{ctx.run_id}")
        comment = st.text_input("コメント", value="", key=f"comment_{ctx.run_id}")
        # このブロックはレンダー毎に値を返す。ユーザー入力が確定しない場合は最後の状態
        approved = True if str(choice).lower() == "approve" else False
        return {"approved": approved, "comment": comment}


