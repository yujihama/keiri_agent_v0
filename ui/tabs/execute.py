from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from ui.flow_viz import persist_success_nodes, render_flow_html, init_success_nodes_namespace
from ui import logging as ulog
from ui.pending_ui import render_and_maybe_submit_pending_ui
from ui.runtime_env import disable_headless_for_ui
from ui.state_keys import SessionKeys
from ui.workbook_artifacts import (
    extract_b64_workbooks_from_results,
    extract_workbooks_from_results,
    render_b64_downloads,
    render_workbook_downloads,
)
from ui.widget_utils import clear_ui_widget_state_for_plan
from core.plan.logger import get_log_path_for_run
from ui.log_utils import read_jsonl, build_summary_input_text, summarize_with_llm


def _format_event_message(ev: dict) -> tuple[str, str]:
    et = ev.get("type")
    node = ev.get("node")
    if et == "loop_start":
        return "info", f"ループ開始: ノード {node}"
    if et == "loop_finish":
        return "success", f"ループ完了: ノード {node}"
    if et == "loop_iter_start":
        return "info", f"イテレーション開始: ノード {node}"
    if et == "loop_iter_finish":
        return "success", f"イテレーション完了: ノード {node}"
    if et == "subflow_start":
        return "info", "サブフロー開始"
    if et == "node_finish":
        ms = ev.get("elapsed_ms")
        att = ev.get("attempts")
        detail: list[str] = []
        if ms is not None:
            detail.append(f"{ms} ms")
        if att is not None:
            detail.append(f"試行 {att}")
        suffix = f"（{', '.join(detail)}）" if detail else ""
        return "success", f"完了: ノード {node}{suffix}"
    if et == "error":
        msg = ev.get("message") or ev.get("error") or ""
        return "error", f"エラー: ノード {node} {msg}"
    return "info", f"{et}: ノード {node}"


def _execute_run(plan_path, registry: BlockRegistry, *, edited_vars: dict | None, dag_area) -> None:
    plan = load_plan(plan_path)
    # Enrich structured-logging context
    try:
        ulog.set_context(plan_id=getattr(plan, "id", None))
    except Exception:
        pass
    progress = st.progress(0, text="実行中...")
    status_area = st.empty()

    recent_msgs: list[tuple[str, str]] = []
    MAX_RECENT = 1

    def _push_and_render(severity: str, message: str) -> None:
        recent_msgs.append((severity, message))
        if len(recent_msgs) > MAX_RECENT:
            del recent_msgs[0 : len(recent_msgs) - MAX_RECENT]
        with status_area.container():
            for sev, msg in recent_msgs:
                if sev == "error":
                    st.error(msg)
                elif sev == "success":
                    st.success(msg)
                else:
                    st.info(msg)

    runner = PlanRunner(registry=registry, default_ui_hitl=True)
    total_estimate = max(1, len(plan.graph))
    done = {"count": 0}
    events_for_dag = []
    # Use the provided placeholder for all DAG rendering to avoid duplicate diagrams

    def on_event(ev):
        events_for_dag.append(ev)
        et = ev.get("type")
        if et in {"node_start", "node_finish", "node_skip", "error", "ui_wait", "ui_submit", "ui_reuse", "loop_start", "loop_finish", "loop_iter_start", "loop_iter_finish", "finish"}:
            try:
                from core.plan.dag_viz import compute_node_states
                states = compute_node_states(plan, events_for_dag)
                succ = persist_success_nodes(plan.id, states)
                for nid in list(succ):
                    states[str(nid)] = "success"
                # Throttle updates to reduce flicker; force final render on finish
                throttle = None if et == "finish" else 250
                render_flow_html(
                    plan,
                    states,
                    include_loop_nodes=False,
                    placeholder=dag_area,
                    throttle_ms=throttle,
                )
            except Exception as e:
                ulog.warn("DAG描画の更新に失敗しました。", e, user=False)
        if et in {"node_finish", "loop_finish", "subflow_finish", "ui_submit", "ui_reuse"}:
            done["count"] += 1
            progress.progress(min(1.0, done["count"] / total_estimate), text=f"{done['count']}/{total_estimate}")
        if et in {"loop_start", "loop_finish", "loop_iter_start", "loop_iter_finish", "subflow_start"}:
            sev, msg = _format_event_message(ev)
            _push_and_render(sev, msg)
        if et == "error":
            sev, msg = _format_event_message(ev)
            _push_and_render(sev, msg)
        if et == "start":
            rid = ev.get("run_id")
            st.session_state[SessionKeys.last_run_id] = rid
            try:
                ulog.set_context(run_id=rid)
            except Exception:
                pass
        if et == "node_finish":
            sev, msg = _format_event_message(ev)
            _push_and_render(sev, msg)

    st.session_state[SessionKeys.run_in_progress] = True
    with disable_headless_for_ui():
        results = runner.run(
            plan,
            on_event=on_event,
            vars_overrides=edited_vars or None,
            resume_run_id=st.session_state.get(SessionKeys.auto_resume_run_id) or None,
        )

    try:
        state_dir = runner._state_dir / plan.id
        if state_dir.exists():
            files = sorted(state_dir.glob("*.state.json"), reverse=True)
            for f in files:
                try:
                    st_json = json.loads(f.read_text(encoding="utf-8"))
                    cand = st_json.get("pending_ui")
                    if cand and not cand.get("submitted"):
                        _rid = f.stem.replace(".state", "")
                        st.session_state[SessionKeys.auto_resume_run_id] = _rid
                        st.session_state[SessionKeys.execute_requested] = False
                        st.session_state[SessionKeys.allow_pending_ui_render] = True
                        st.session_state[SessionKeys.run_in_progress] = False
                        st.rerun()
                except Exception as e:
                    ulog.warn("pending_uiの自動検出に失敗しました。", e, user=False)
                    continue
    except Exception as e:
        ulog.warn("stateディレクトリの走査に失敗しました。", e, user=False)

    progress.progress(1.0, text="完了")
    with st.expander("結果の詳細(JSON)", expanded=False):
        st.json(results, expanded=False)

    st.session_state[SessionKeys.execute_requested] = False
    st.session_state[SessionKeys.allow_pending_ui_render] = True
    st.session_state[SessionKeys.run_in_progress] = False
    try:
        ulog.clear_context()
    except Exception:
        pass

    try:
        output_method = (plan.vars or {}).get("output_method", "download")
    except Exception:
        output_method = "download"

    try:
        artifacts = extract_workbooks_from_results(results if isinstance(results, dict) else None, plan)
        if artifacts:
            render_workbook_downloads(artifacts, output_method, plan.id)
    except Exception as _dl_err:
        st.warning(f"Excel出力UIの構築でエラー: {_dl_err}")

    try:
        b64_items = extract_b64_workbooks_from_results(results if isinstance(results, dict) else None, plan)
        if b64_items and output_method in ("download", "both"):
            render_b64_downloads(b64_items)
    except Exception as e:
        ulog.warn("base64成果物の描画に失敗しました。", e, user=False)

    # --- 実行結果サマリー（ログ要約） ---
    try:
        st.divider()
        st.subheader("実行結果サマリー")

        rid = st.session_state.get(SessionKeys.last_run_id)
        log_path = None
        if rid:
            try:
                log_path = get_log_path_for_run(rid)
            except Exception:
                log_path = None
        if not log_path:
            try:
                plan_dir = (runner.runs_dir / plan.id)
                # run_id に一致するファイルを優先
                if rid:
                    cand = plan_dir / f"{rid}.jsonl"
                    if cand.exists():
                        log_path = cand
                if not log_path and plan_dir.exists():
                    files = sorted(plan_dir.glob("*.jsonl"), reverse=True)
                    if files:
                        log_path = files[0]
            except Exception:
                log_path = None

        if log_path and Path(log_path).exists():
            events = read_jsonl(Path(log_path))
            summary_input = build_summary_input_text(events, results if isinstance(results, dict) else None)
            try:
                summary = summarize_with_llm(summary_input)
                st.markdown(f"**概要**: {summary.overview}")
                if getattr(summary, "highlights", None):
                    st.markdown("**ハイライト**")
                    for item in summary.highlights:
                        st.write(f"- {item}")
                if getattr(summary, "errors", None):
                    if summary.errors:
                        st.markdown("**エラー**")
                        try:
                            items = [e.model_dump() for e in summary.errors]  # pydantic v2
                        except Exception:
                            try:
                                items = [e.dict() for e in summary.errors]  # pydantic v1 fallback
                            except Exception:
                                items = summary.errors  # 最後の手段
                        st.json(items)
                if getattr(summary, "next_actions", None):
                    if summary.next_actions:
                        st.markdown("**次のアクション**")
                        for item in summary.next_actions:
                            st.write(f"- {item}")
            except Exception as _sum_err:
                ulog.warn("要約生成に失敗しました。整形ログを表示します。", _sum_err, user=False)
                st.text_area("要約入力（ログ+結果テキスト抜粋）", value=summary_input, height=240)

            # with st.expander("要約入力（ログ+結果テキスト）", expanded=False):
            #     st.text_area("summary_input", value=summary_input, height=160)
        else:
            st.info("ログファイルが見つからないため、サマリーを表示できません。")
    except Exception as _e:
        ulog.warn("実行サマリーの生成に失敗しました。", _e, user=False)


def render(registry: BlockRegistry) -> None:
    st.subheader("業務実施")
    plans = list((Path.cwd() / "designs").resolve().rglob("*.yaml"))
    plan_path = st.selectbox("実行するPlanを選択", plans, key="exec_select")

    plan = load_plan(plan_path)
    st.markdown(f"> {plan.id}")
    try:
        instr_text = (plan.vars or {}).get("instruction")
    except Exception:
        instr_text = None
    if instr_text:
        st.info(instr_text)

    dag_area = st.empty()
    try:
        # 実行要求中や実行中は初期プレビューを描画しない（実行開始時のランニングノード表示を優先）
        if plan_path and not st.session_state.get(SessionKeys.execute_requested) and not st.session_state.get(SessionKeys.run_in_progress):
            plan_preview_for_dag = load_plan(plan_path)
            succ = init_success_nodes_namespace(plan_preview_for_dag.id)
            states0 = {str(nid): "success" for nid in succ}
            render_flow_html(plan_preview_for_dag, states0, include_loop_nodes=False, placeholder=dag_area)
    except Exception:
        st.warning("フロー図の表示に失敗しました。")

    st.divider()

    edited_vars: dict = {}

    runner = PlanRunner(registry=registry, default_ui_hitl=True)

    def _on_run_click() -> None:
        st.session_state[SessionKeys.execute_requested] = True
        st.session_state[SessionKeys.allow_pending_ui_render] = False

    col_actions1, col_actions2 = st.columns([1, 1])
    with col_actions1:
        st.button("実行/再開", on_click=_on_run_click)
    with col_actions2:
        if st.button("実行結果をクリア"):
            try:
                state_dir = runner._state_dir / plan.id
                if state_dir.exists():
                    for f in state_dir.glob("*.state.json"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
            except Exception:
                pass
            try:
                from core.ui.session_state import SessionStateManager
                SessionStateManager(plan.id, "clear").clear_plan_state()
            except Exception:
                pass
            try:
                clear_ui_widget_state_for_plan(plan)
            except Exception:
                pass
            try:
                success_key = SessionKeys.flow_success(plan.id)
                keys = [success_key, SessionKeys.auto_resume_run_id, SessionKeys.last_run_id, SessionKeys.execute_requested, SessionKeys.allow_pending_ui_render, SessionKeys.run_in_progress]
                for k in keys:
                    if k in st.session_state:
                        del st.session_state[k]
            except Exception:
                pass
            st.success("実行結果をクリアしました。『実行/再開』で最初からやり直せます。")
            st.rerun()

    render_and_maybe_submit_pending_ui(plan_path, registry, runner, placeholder=dag_area)

    if st.session_state.get(SessionKeys.execute_requested):
        _execute_run(plan_path, registry, edited_vars=edited_vars, dag_area=dag_area)


