from __future__ import annotations

from typing import Any, Dict, Optional
import os
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # fallback for headless tests

from core.blocks.base import BlockContext, UIBlock


class PlaceholderUIBlock(UIBlock):
    id = "ui.placeholder"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        # Headless: return inputs for tests
        if execution_context and getattr(execution_context, 'headless_mode', False):
            return self._headless_response(inputs, execution_context)
        elif st is None:
            return {"value": inputs.get("message", "ok"), "output_method": inputs.get("output_method"), "metadata": {"submitted": True}}
        key_base = str(inputs.get("widget_key") or ctx.run_id)
        msg = inputs.get("message", "Placeholder")
        output_method = inputs.get("output_method")

        sub_key = f"placeholder_submitted_{key_base}"
        snap_key = f"placeholder_snapshot_{key_base}"
        if st.session_state.get(sub_key):
            snap = st.session_state.get(snap_key, {"value": msg, "output_method": output_method})
            # st.write(snap.get("value", msg))
            if snap.get("output_method"):
                st.info(f"Output method: {snap.get('output_method')}")
            return {**snap, "metadata": {"submitted": True}}

        # st.write(msg)
        if output_method:
            st.info(f"Output method: {output_method}")
        decided = st.button("確定", key=f"placeholder_confirm_{key_base}")
        snap = {"value": msg, "output_method": output_method}
        if decided:
            st.session_state[sub_key] = True
            st.session_state[snap_key] = snap
            st.success("表示を固定しました")
            return {**snap, "metadata": {"submitted": True}}
        return {**snap, "metadata": {"submitted": False}}

    def _headless_response(self, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        """プレースホルダーのヘッドレス応答"""
        # 実行コンテキストからモック応答を取得
        if execution_context:
            mock_response = execution_context.get_ui_mock_response(self.id, inputs.get("node_id", ""))
            if mock_response:
                return mock_response
        
        # デフォルト: 入力値をそのまま返す
        return {
            "value": inputs.get("message", "ok"), 
            "output_method": inputs.get("output_method"), 
            "metadata": {"submitted": True}
        }


