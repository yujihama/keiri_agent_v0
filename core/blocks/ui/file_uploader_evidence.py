from __future__ import annotations

from typing import Any, Dict
import os

import streamlit as st

from core.blocks.base import BlockContext, UIBlock


class EvidenceZipUploader(UIBlock):
    id = "ui.file_uploader.evidence_zip"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # ヘッドレス（CI等）ではスタブで返す
        if os.getenv("KEIRI_AGENT_HEADLESS", "0") == "1":
            return {"evidence_zip": b""}
        st.write("証跡ZIPファイルをアップロードしてください")
        max_mb = int(inputs.get("max_mb", 50))
        f = st.file_uploader("ZIPファイル", type=["zip"], key=f"zip_{ctx.run_id}")
        if f is None:
            return {"evidence_zip": None}
        if f.size and f.size > max_mb * 1024 * 1024:
            st.error(f"ファイルサイズが上限({max_mb}MB)を超えています")
            return {"evidence_zip": None}
        data = f.read()
        # 簡易プレビュー: 先頭数KBのヘッダ/サイズ
        st.caption(f"受領: {f.name} ({len(data)} bytes)")
        return {"evidence_zip": data}


