from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import streamlit as st

from core.blocks.base import UIBlock, BlockContext
from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from ui.flow_viz import render_flow_html, init_success_nodes_namespace
from ui import logging as ulog
from ui.runtime_env import disable_headless_for_ui
from ui.state_keys import SessionKeys


def find_pending_ui_for_plan(plan_id: str, runner: PlanRunner) -> Tuple[Dict[str, Any] | None, str | None]:
    state_dir = runner._state_dir / plan_id
    pending = None
    pending_run_id = None

    auto_rid = st.session_state.get(SessionKeys.auto_resume_run_id)
    if auto_rid and state_dir.exists():
        f = state_dir / f"{auto_rid}.state.json"
        if f.exists():
            try:
                st_json = json.loads(f.read_text(encoding="utf-8"))
                cand = st_json.get("pending_ui")
                if cand and not cand.get("submitted"):
                    pending = cand
                    pending_run_id = auto_rid
            except Exception as e:
                ulog.warn("pending_uiの取得でエラーになりました。", e)

    if pending is None and state_dir.exists():
        files = sorted(state_dir.glob("*.state.json"), reverse=True)
        for f in files:
            try:
                st_json = json.loads(f.read_text(encoding="utf-8"))
                cand = st_json.get("pending_ui")
                if cand and not cand.get("submitted"):
                    pending = cand
                    pending_run_id = f.stem.replace(".state", "")
                    break
            except Exception:
                continue

    return pending, pending_run_id


def encode_for_json(value: Any):
    if isinstance(value, (bytes, bytearray)):
        return {"__type": "b64bytes", "data": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {k: encode_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [encode_for_json(x) for x in value]
    return value


def render_and_maybe_submit_pending_ui(plan_path, registry: BlockRegistry, runner: PlanRunner, *, placeholder=None) -> None:
    try:
        plan_for_pending = load_plan(plan_path)
    except Exception:
        plan_for_pending = None

    if plan_for_pending is None:
        return

    pending, pending_run_id = find_pending_ui_for_plan(plan_for_pending.id, runner)

    can_render_pending = (
        (not st.session_state.get(SessionKeys.execute_requested))
        and (not st.session_state.get(SessionKeys.run_in_progress))
        and st.session_state.get(SessionKeys.allow_pending_ui_render, True)
    )

    if not (can_render_pending and pending and pending_run_id):
        from core.plan.dag_viz import generate_flow_html
        try:
            states_init = {n.id: "pending" for n in plan_for_pending.graph} if plan_for_pending else {}
            if plan_for_pending:
                render_flow_html(plan_for_pending, states_init, include_loop_nodes=False, placeholder=placeholder or st)
        except Exception:
            pass
        return

    try:
        node_id = pending.get("node_id")
        node = next(n for n in plan_for_pending.graph if n.id == node_id)
        block = registry.get(node.block)
        if isinstance(block, UIBlock):
            from core.plan.dag_viz import generate_flow_html
            try:
                _states = {n.id: "pending" for n in plan_for_pending.graph}
                _states[str(node_id)] = "running"
                succ = init_success_nodes_namespace(plan_for_pending.id)
                for nid in succ:
                    _states[str(nid)] = "success"
                render_flow_html(plan_for_pending, _states, include_loop_nodes=False, placeholder=placeholder or st)
            except Exception as e:
                ulog.warn("フロー図の表示に失敗しました。", e)

            st.session_state[SessionKeys.auto_resume_run_id] = pending_run_id

            _vars = dict(plan_for_pending.vars)
            try:
                _vars["__plan_id"] = plan_for_pending.id
                _vars["__node_id"] = str(node_id)
            except Exception:
                pass
            ctx = BlockContext(run_id=pending_run_id, workspace=str(Path.cwd()), vars=_vars)
            inputs_for_ui = dict(pending.get("inputs", {}) or {})
            try:
                inputs_for_ui.setdefault("widget_key", str(node_id))
            except Exception:
                pass
            with disable_headless_for_ui():
                try:
                    out = block.render(ctx, inputs_for_ui)
                except Exception as e:
                    ulog.error("UIブロックのレンダリングに失敗しました。", e)
                    raise

            required_local_keys = list(node.outputs.keys()) if node.outputs else []
            ready = True
            for k in required_local_keys:
                if not isinstance(out, dict) or out.get(k) is None:
                    ready = False
                    break
            if ready:
                spath = runner._state_path(plan_for_pending.id, pending_run_id)
                try:
                    cur = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}
                except Exception as e:
                    ulog.warn("stateファイルの読み込みに失敗しました。", e)
                    cur = {}
                already_submitted = bool((cur.get("pending_ui") or {}).get("submitted"))
                if not already_submitted:
                    pending["submitted"] = True
                    pending["outputs"] = encode_for_json(out)
                    try:
                        node_key = str(node_id)
                    except Exception:
                        node_key = str(pending.get("node_id", ""))
                    ui_outputs = cur.get("ui_outputs") or {}
                    ui_outputs[node_key] = pending["outputs"]
                    cur["ui_outputs"] = ui_outputs
                    cur["pending_ui"] = pending
                    runner._save_state(plan_for_pending, pending_run_id, cur)
                    try:
                        from core.plan.dag_viz import generate_flow_html
                        _states2 = {n.id: "pending" for n in plan_for_pending.graph}
                        succ = init_success_nodes_namespace(plan_for_pending.id)
                        succ.add(str(node_id))
                        st.session_state[SessionKeys.flow_success(plan_for_pending.id)] = succ
                        for nid in succ:
                            _states2[str(nid)] = "success"
                        render_flow_html(plan_for_pending, _states2, include_loop_nodes=False, placeholder=placeholder or st)
                    except Exception:
                        pass
                st.success("入力を保存しました。『実行/再開』を押して続きから再開してください。")
    except StopIteration:
        pass


