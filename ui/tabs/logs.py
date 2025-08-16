from __future__ import annotations

from pathlib import Path

import streamlit as st

from core.plan.loader import load_plan as _load_plan_for_viz
from core.plan.dag_viz import compute_node_states, generate_flow_html
from core.plan.models import Plan as _PlanModel
from ui import logging as ulog
from ui.log_utils import read_jsonl, filter_events


def render() -> None:
    st.subheader("ログ")
    runs_dir = Path("runs")
    if not runs_dir.exists():
        st.info("まだログがありません")
        return

    plans = sorted({p.parent.name for p in runs_dir.rglob("*.jsonl")})
    if not plans:
        st.info("まだログがありません")
        return

    selected = st.selectbox("Plan", plans)
    if selected is None:
        st.stop()
    files = sorted((runs_dir / selected).glob("*.jsonl"), reverse=True)
    if not files:
        st.info("選択したPlanのログがありません")
        return

    file = st.selectbox("Run", files)
    if not file:
        return

    events = read_jsonl(file)

    types = sorted({e.get("type") for e in events})
    sel_types = st.multiselect("イベント種類", options=types, default=types)
    nodes = sorted({e.get("node") for e in events if e.get("node")})
    sel_nodes = st.multiselect("ノード", options=nodes, default=nodes)
    tags = sorted({e.get("tag") for e in events if e.get("tag")})
    sel_tags = st.multiselect("タグ", options=tags, default=tags)
    levels = sorted({e.get("level") for e in events if e.get("level")})
    sel_levels = st.multiselect("レベル", options=levels, default=levels)
    parent = st.text_input("parent_run_id フィルタ", value="")
    q = st.text_input("テキスト検索", value="")

    filtered = filter_events(
        events,
        types=sel_types,
        nodes=sel_nodes,
        tags=sel_tags,
        levels=sel_levels,
        parent_run_id=parent or None,
        query=q or None,
    )

    st.write(f"{len(filtered)} events")
    ok = sum(1 for e in filtered if e.get("type") == "node_finish")
    err = sum(1 for e in filtered if e.get("type") == "error")
    skipped = sum(1 for e in filtered if e.get("type") == "node_skip")
    st.write({"node_finish": ok, "error": err, "node_skip": skipped})

    try:
        _plan_viz = None
        plan_file = Path("designs") / f"{selected}.yaml"
        if plan_file.exists():
            _plan_viz = _load_plan_for_viz(plan_file)
        else:
            try:
                for cand in Path("designs").rglob("*.yaml"):
                    try:
                        _p = _load_plan_for_viz(cand)
                        if _p and getattr(_p, "id", None) == selected:
                            _plan_viz = _p
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if _plan_viz is None:
            start_ev = next((e for e in events if e.get("type") == "start" and e.get("plan") == selected), None)
            if start_ev and isinstance(start_ev.get("plan_spec"), dict):
                try:
                    _plan_viz = _PlanModel.model_validate(start_ev["plan_spec"])  # type: ignore[arg-type]
                except Exception:
                    _plan_viz = None

        if _plan_viz is not None:
            states = compute_node_states(_plan_viz, filtered)
            html = generate_flow_html(_plan_viz, states, include_loop_nodes=False)
            st.markdown(html, unsafe_allow_html=True)
        else:
            st.info("フロー図表示用のPlan定義を見つけられませんでした（designsまたはログ内のplan_specを参照できませんでした）。")
    except Exception as _viz_err:
        ulog.warn("DAG可視化でエラー", _viz_err)

    try:
        import pandas as _pd  # type: ignore
        cols = ["seq", "ts", "type", "node", "tag", "level", "message"]
        df = _pd.DataFrame([{k: e.get(k) for k in cols} for e in filtered])
        st.dataframe(df)
    except Exception as e:
        ulog.warn("ログ表の描画に失敗しました。", e, user=False)

    # raw and download
    try:
        text = (Path(file)).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
    except Exception as e:
        ulog.warn("JSONLの読み込みに失敗しました。", e)
        lines = []
    st.json(filtered)
    if not filtered and lines:
        st.info("イベントの解析に失敗したため、Rawログを表示します。")
        st.text_area("Raw JSONL", value="\n".join(lines), height=200)
    st.download_button("JSONL ダウンロード", data="\n".join(lines), file_name=file.name, mime="application/jsonl")


