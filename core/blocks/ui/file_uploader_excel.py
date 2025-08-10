from __future__ import annotations

from typing import Any, Dict
import os

import streamlit as st

from core.blocks.base import BlockContext, UIBlock


class ExcelUploader(UIBlock):
    id = "ui.file_uploader.excel"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        if os.getenv("KEIRI_AGENT_HEADLESS", "0") == "1":
            return {"workbook": {"name": "dummy.xlsx"}}
        st.write("Excelファイルをアップロードしてください")
        max_mb = int(inputs.get("max_mb", 20))
        f = st.file_uploader("Excel", type=["xlsx"], key=f"xlsx_{ctx.run_id}")
        if f is None:
            return {"workbook": None}
        if f.size and f.size > max_mb * 1024 * 1024:
            st.error(f"ファイルサイズが上限({max_mb}MB)を超えています")
            return {"workbook": None}
        data = f.read()
        st.caption(f"受領: {f.name} ({len(data)} bytes)")
        # 現段階は bytes を保持
        return {"workbook": {"name": f.name, "bytes": data}}


