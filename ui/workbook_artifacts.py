from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st


@dataclass
class WorkbookArtifact:
    label: str
    data_bytes: bytes
    file_name: str


def _get_allowed_workbook_aliases(plan) -> set[str] | None:
    """Return a set of alias names that are allowed to be shown as downloadable workbooks.

    Plan YAML can specify vars.final_workbooks: ["alias1", "alias2", ...].
    - If present and non-empty, only these aliases are considered.
    - If missing/empty or not a list of strings, no filtering is applied (return None).
    """
    try:
        vars_dict = getattr(plan, "vars", None) or {}
        val = vars_dict.get("final_workbooks")
        if isinstance(val, (list, tuple)):
            allowed = {str(x) for x in val if isinstance(x, (str, int, float)) and str(x)}
            return allowed if allowed else None
    except Exception:
        pass
    return None


def extract_workbooks_from_results(results: Dict[str, Any] | None, plan) -> List[WorkbookArtifact]:
    if not isinstance(results, dict):
        return []

    # Preferred aliases specified in plan outputs
    aliases_for_wb: List[str] = []
    try:
        for n in getattr(plan, "graph", []) or []:
            outs = getattr(n, "outputs", None)
            if isinstance(outs, dict):
                for local_out, alias in outs.items():
                    if local_out in ("workbook_updated", "updated_workbook") and isinstance(alias, str) and alias:
                        aliases_for_wb.append(alias)
        aliases_for_wb = list(dict.fromkeys(aliases_for_wb))
    except Exception:
        aliases_for_wb = []

    artifacts: List[WorkbookArtifact] = []
    seen_ids: set[int] = set()
    allowed_aliases = _get_allowed_workbook_aliases(plan)

    def _push(v: Dict[str, Any], label: str) -> None:
        nonlocal artifacts, seen_ids
        if not isinstance(v, dict):
            return
        b = v.get("bytes")
        if isinstance(b, (bytes, bytearray)):
            if id(v) in seen_ids:
                return
            seen_ids.add(id(v))
            fname = v.get("name") if isinstance(v.get("name"), str) else None
            artifacts.append(WorkbookArtifact(label=label, data_bytes=bytes(b), file_name=fname or f"workbook_updated_{len(artifacts)+1}.xlsx"))

    # 1) by alias
    for alias in aliases_for_wb:
        if allowed_aliases is not None and alias not in allowed_aliases:
            continue
        v = results.get(alias)
        if isinstance(v, dict):
            _push(v, alias)
    # 2) fallback by common keys
    for key in ("workbook_updated", "updated_workbook"):
        if allowed_aliases is not None and key not in allowed_aliases:
            continue
        v = results.get(key)
        if isinstance(v, dict):
            _push(v, key)
    # 3) generic scan
    for k_any, v_any in results.items():
        if isinstance(v_any, dict):
            k_str = str(k_any)
            if allowed_aliases is not None and k_str not in allowed_aliases:
                continue
            _push(v_any, k_str)

    return artifacts


def extract_b64_workbooks_from_results(results: Dict[str, Any] | None, plan) -> List[Tuple[str, str]]:
    if not isinstance(results, dict):
        return []

    aliases_for_b64: List[str] = []
    try:
        for n in getattr(plan, "graph", []) or []:
            outs = getattr(n, "outputs", None)
            if isinstance(outs, dict):
                for local_out, alias in outs.items():
                    if local_out in ("workbook_b64", "updated_workbook_b64") and isinstance(alias, str) and alias:
                        aliases_for_b64.append(alias)
        aliases_for_b64 = list(dict.fromkeys(aliases_for_b64))
    except Exception:
        aliases_for_b64 = []

    items: List[Tuple[str, str]] = []
    allowed_aliases = _get_allowed_workbook_aliases(plan)
    seen_vals: set[str] = set()

    for alias in aliases_for_b64:
        if allowed_aliases is not None and alias not in allowed_aliases:
            continue
        val = results.get(alias)
        if isinstance(val, str) and val and val not in seen_vals:
            items.append((alias, val))
            seen_vals.add(val)

    for key in ("workbook_b64", "updated_workbook_b64"):
        if allowed_aliases is not None and key not in allowed_aliases:
            continue
        val = results.get(key)
        if isinstance(val, str) and val and val not in seen_vals:
            items.append((key, val))
            seen_vals.add(val)

    for k_any, v_any in results.items():
        if isinstance(v_any, str) and str(k_any).endswith("_b64") and v_any and v_any not in seen_vals:
            k_str = str(k_any)
            if allowed_aliases is not None and k_str not in allowed_aliases:
                continue
            items.append((k_str, v_any))
            seen_vals.add(v_any)

    return items

@st.fragment
def render_workbook_downloads(artifacts: List[WorkbookArtifact], output_method: str, plan_id: str) -> None:
    for idx, art in enumerate(artifacts):
        if output_method in ("download", "both"):
            st.download_button(
                f"更新済みExcelをダウンロード: {art.label}",
                data=art.data_bytes,
                file_name=art.file_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_wb_{idx}",
            )
        if output_method in ("save_runs", "both"):
            if st.button(f"runs フォルダに保存: {art.label}", key=f"save_wb_{idx}"):
                out_dir = Path("runs") / plan_id
                out_dir.mkdir(parents=True, exist_ok=True)
                run_id = st.session_state.get("last_run_id") or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                out_path = out_dir / f"{run_id}_updated_{idx+1}.xlsx"
                out_path.write_bytes(art.data_bytes)
                st.success(f"保存しました: {out_path}")


@st.fragment
def render_b64_downloads(b64_items: List[Tuple[str, str]]) -> None:
    for idx, (label, b64) in enumerate(b64_items):
        st.download_button(
            f"更新済みExcelをダウンロード (b64): {label}",
            data=base64.b64decode(b64),
            file_name=f"workbook_updated_{idx+1}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"dl_wb_b64_{idx}",
        )


