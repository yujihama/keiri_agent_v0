from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import os
import base64

import streamlit as st

from core.blocks.registry import BlockRegistry
from core.blocks.base import BlockContext


def render(registry: BlockRegistry) -> None:
    st.subheader("レビュー（証跡検索）")

    # 検索条件入力
    name_contains = st.text_input("名称に含む", value="")
    ext = st.text_input("拡張子(例: .pdf)", value="")
    col1, col2 = st.columns(2)
    with col1:
        min_size = st.number_input("最小サイズ(bytes)", min_value=0, value=0, step=1)
    with col2:
        max_size = st.number_input("最大サイズ(bytes)", min_value=0, value=0, step=1)
    do_hash = st.checkbox("ハッシュ計算", value=False)

    if st.button("検索"):
        search_block = registry.get("evidence.search")
        ctx = BlockContext(run_id="ui", workspace=str(Path.cwd()))
        criteria: Dict[str, Any] = {
            "name_contains": name_contains or None,
            "ext": ext or None,
            "min_size": min_size or None,
            "max_size": max_size or None,
        }
        out = search_block.run(ctx, {"search_criteria": criteria, "compute_hash": do_hash})  # type: ignore[attr-defined]
        st.session_state["review_search_results"] = out.get("search_results") or []

    results: List[Dict[str, Any]] = st.session_state.get("review_search_results", [])  # type: ignore[assignment]
    if results:
        st.dataframe(results, use_container_width=True)

    st.divider()
    st.subheader("詳細")
    sel_name = st.text_input("ファイル名（上表からコピー）")
    verify = st.checkbox("完全性検証（可能なら）", value=True)
    if st.button("取得"):
        retrieve_block = registry.get("evidence.retrieve")
        ctx = BlockContext(run_id="ui", workspace=str(Path.cwd()))
        out = retrieve_block.run(ctx, {"name": sel_name, "verify_integrity": verify})  # type: ignore[attr-defined]
        if not out.get("found"):
            st.error("見つかりませんでした")
        else:
            meta = out.get("metadata") or {}
            st.json(meta)
            data_b64 = out.get("evidence_data_base64")
            if isinstance(data_b64, str):
                try:
                    raw = base64.b64decode(data_b64)
                    st.download_button(
                        "ダウンロード",
                        data=raw,
                        file_name=meta.get("name", "evidence.bin"),
                    )
                except Exception:
                    pass
            st.success(f"integrity_ok={out.get('integrity_ok')}")