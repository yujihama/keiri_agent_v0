from __future__ import annotations

from typing import Any, Dict

from core.blocks.base import BlockContext, UIBlock
import os
try:
    import streamlit as st  # type: ignore
except Exception:
    st = None  # fallback for headless tests


class PlaceholderUIBlock(UIBlock):
    id = "ui.placeholder"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # Headless: return inputs for tests
        if os.getenv("KEIRI_AGENT_HEADLESS", "0") == "1" or st is None:
            return {"value": inputs.get("message", "ok"), "output_method": inputs.get("output_method")}
        # Interactive mode: show info
        st.write(inputs.get("message", "Placeholder"))
        output_method = inputs.get("output_method")
        if output_method:
            st.info(f"Output method: {output_method}")
        return {"value": "ok", "output_method": output_method}


