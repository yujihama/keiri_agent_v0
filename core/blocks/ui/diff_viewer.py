from __future__ import annotations

from typing import Any, Dict, Optional
import json

import streamlit as st

from core.blocks.base import BlockContext, UIBlock


def _json_diff(a: Any, b: Any, path: str = "") -> list[dict]:
    diffs: list[dict] = []
    if type(a) != type(b):
        diffs.append({"path": path or "$", "type": "type_change", "from": str(type(a).__name__), "to": str(type(b).__name__)})
        return diffs
    if isinstance(a, dict):
        keys = set(a.keys()) | set(b.keys())
        for k in sorted(keys):
            pa = path + ("." if path else "") + str(k)
            if k not in a:
                diffs.append({"path": pa, "type": "added", "to": b[k]})
            elif k not in b:
                diffs.append({"path": pa, "type": "removed", "from": a[k]})
            else:
                diffs.extend(_json_diff(a[k], b[k], pa))
    elif isinstance(a, list):
        # naive: compare by index
        ln = max(len(a), len(b))
        for i in range(ln):
            pa = path + f"[{i}]"
            if i >= len(a):
                diffs.append({"path": pa, "type": "added", "to": b[i]})
            elif i >= len(b):
                diffs.append({"path": pa, "type": "removed", "from": a[i]})
            else:
                diffs.extend(_json_diff(a[i], b[i], pa))
    else:
        if a != b:
            diffs.append({"path": path or "$", "type": "changed", "from": a, "to": b})
    return diffs


class DiffViewerUIBlock(UIBlock):
    id = "ui.diff_viewer"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        if execution_context and getattr(execution_context, 'headless_mode', False):
            return self._headless_response(inputs, execution_context)

        before = inputs.get("before")
        after = inputs.get("after")
        message = inputs.get("message") or "変更内容を確認してください"
        key_base = str(inputs.get("widget_key") or ctx.run_id)

        st.info(message)
        diffs = _json_diff(before, after)
        with st.expander("差分", expanded=True):
            st.json(diffs)
        approve = st.button("承認", key=f"diff_ok_{key_base}")
        reject = st.button("差戻し", key=f"diff_ng_{key_base}")
        approved = bool(approve) and not bool(reject)
        submitted = approve or reject
        return {"diffs": diffs, "approved": approved, "metadata": {"submitted": submitted}}

    def _headless_response(self, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        before = inputs.get("before")
        after = inputs.get("after")
        diffs = _json_diff(before, after)
        # default approve in headless
        return {"diffs": diffs, "approved": True, "metadata": {"submitted": True, "headless": True}}


