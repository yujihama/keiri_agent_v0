from __future__ import annotations

import json
from datetime import datetime, UTC
import base64
from pathlib import Path
from typing import List
import os
import yaml
from contextlib import contextmanager
import tempfile

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional for the main app

import streamlit as st

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan
from core.plan.design_engine import generate_plan, DesignEngineOptions
from core.plan.runner import PlanRunner


def list_designs() -> List[Path]:
    designs_dir = (Path.cwd() / "designs").resolve()
    return sorted(designs_dir.rglob("*.yaml"))


def _clear_ui_widget_state_for_plan(plan) -> None:
    """このPlanに紐づくUIウィジェット用セッションキーを一掃する。

    interactive_input の各ウィジェットは以下のキー接頭辞を使う:
      - file_, files_, folder_, text_, select_, bool_, number_, chat_
      - value_（内部保持用）
      - collect_form_（フォーム本体）
    base_key は node_id を使用しているため、ノードごとに該当接頭辞+node_id で削除する。
    """
    try:
        import streamlit as st
    except Exception:
        return

    widget_prefixes = [
        "file_", "files_", "folder_", "text_", "select_", "bool_", "number_", "chat_",
        "value_", "collect_form_",
    ]
    try:
        nodes = list(getattr(plan, "graph", []) or [])
    except Exception:
        nodes = []

    node_ids = []
    for n in nodes:
        try:
            if getattr(n, "block", None) and str(n.block).startswith("ui."):
                node_ids.append(str(n.id))
        except Exception:
            continue

    keys_to_remove = []
    for key in list(st.session_state.keys()):
        for nid in node_ids:
            for pref in widget_prefixes:
                if key.startswith(f"{pref}{nid}"):
                    keys_to_remove.append(key)
                    break
            # 早期breakはしない（複数prefix一致は稀だが安全側）
    for k in keys_to_remove:
        try:
            del st.session_state[k]
        except Exception:
            pass


@contextmanager
def _disable_headless_for_ui():
    """UI 実行時に一時的にヘッドレスを無効化する。

    Streamlit 上の実行/再開や保留UI描画の間のみ、
    KEIRI_AGENT_HEADLESS を "0" に設定し、終了時に元へ戻す。
    """
    prev = os.environ.get("KEIRI_AGENT_HEADLESS", None)
    try:
        os.environ["KEIRI_AGENT_HEADLESS"] = "0"
        yield
    finally:
        try:
            if prev is None:
                os.environ.pop("KEIRI_AGENT_HEADLESS", None)
            else:
                os.environ["KEIRI_AGENT_HEADLESS"] = prev
        except Exception:
            pass


def _now_tmp_yaml_path() -> Path:
    return Path(tempfile.mkstemp(prefix=".tmp_plan_", suffix=".yaml", dir=str(Path.cwd()))[1])


def validate_and_dryrun(yaml_text: str, registry: BlockRegistry, *, do_dryrun: bool = True):
    """YAMLテキストを一時ファイルに書き、load→validate→(任意)dry_run を一括実行。

    戻り値: (plan, errors_list, dryrun_exception)
    - plan: 読み込めたPlan（検証エラーがあっても返す場合あり）
    - errors_list: 検証エラーのリスト（なければ空）
    - dryrun_exception: ドライラン時の例外（なければNone）
    """
    tmp = _now_tmp_yaml_path()
    try:
        tmp.write_text(yaml_text, encoding="utf-8")
        plan = load_plan(tmp)
        errors = validate_plan(plan, registry)
        dr_err = None
        if not errors and do_dryrun:
            try:
                dry_run_plan(plan, registry)
            except Exception as e:  # noqa: BLE001
                dr_err = e
        return plan, errors or [], dr_err
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def main():
    st.set_page_config(page_title="Keiri Agent", layout="wide")
    st.title("Keiri Agent")

    tabs = st.tabs(["業務設計", "業務実施", "ログ"])
    registry = BlockRegistry()
    registry.load_specs()

    with tabs[0]:
        st.subheader("業務設計")
        st.write("Plan一覧から選択、YAMLを編集して検証/ドライラン/保存できます。")
        plans = list_designs()
        plan_path = st.selectbox(
            "Planを選択",
            plans,
            format_func=lambda p: str(p.relative_to(Path.cwd())) if p.is_absolute() else str(p),
        )
        content = Path(plan_path).read_text(encoding="utf-8")
        yaml_text = st.text_area("Plan YAML", content, height=400)

        with st.expander("ブロックカタログ/スニペット"):
            # ブロックカタログ（id / inputs / outputs / description）
            specs = []
            missing_imports = set()
            for bid, lst in registry.specs_by_id.items():
                spec = lst[-1]
                try:
                    inputs = ",".join(sorted((spec.inputs or {}).keys()))
                    outputs = ",".join(sorted((spec.outputs or {}).keys()))
                except Exception:
                    inputs, outputs = "", ""
                # requirements診断（import可否）
                reqs = []
                try:
                    for r in (spec.requirements or []):
                        reqs.append(r)
                        # env:KEY はスキップ
                        if isinstance(r, str) and not r.startswith("env:"):
                            try:
                                __import__(r)
                            except Exception:
                                missing_imports.add(r)
                except Exception:
                    pass
                specs.append({
                    "id": spec.id,
                    "inputs": inputs,
                    "outputs": outputs,
                    "requirements": ",".join(reqs) if reqs else "",
                    "description": spec.description or "",
                })
            if specs:
                st.dataframe(specs, use_container_width=True, hide_index=True)
            if missing_imports:
                st.warning({"未インストールの可能性": sorted(missing_imports)})

            st.markdown("**YAMLスニペット生成**")
            snippet_kind = st.selectbox("種類", ["when", "foreach", "subflow"], index=0)
            if snippet_kind == "when":
                snippet = (
                    "when:\n"
                    "  expr: \"${match_ai.summary.total_amount} > 1000000\"\n"
                )
            elif snippet_kind == "foreach":
                snippet = (
                    "- id: foreach_data\n"
                    "  type: loop\n"
                    "  foreach:\n"
                    "    input: \"${vars.items}\"\n"
                    "    itemVar: item\n"
                    "    max_concurrency: 4\n"
                    "  body:\n"
                    "    plan:\n"
                    "      id: per_item\n"
                    "      version: 0.0.1\n"
                    "      graph:\n"
                    "        - id: step\n"
                    "          block: ui.confirmation\n"
                    "          in: { message: '処理を続行しますか？', options: ['approve','reject'] }\n"
                    "          out: { approved: approved }\n"
                    "  out:\n"
                    "    collect: results\n"
                )
            else:
                snippet = (
                    "- id: call_subflow\n"
                    "  type: subflow\n"
                    "  call:\n"
                    "    plan_id: common/validate_inputs\n"
                    "    inputs: { results: ${match_ai.match_results} }\n"
                    "  out:\n"
                    "    write_ok: ok\n"
                    "    write_summary: sub_summary\n"
                )
            st.code(snippet, language="yaml")
            if st.button("（自動生成エリアに）スニペットを追記"):
                if "gen_yaml" in st.session_state and isinstance(st.session_state["gen_yaml"], str):
                    st.session_state["gen_yaml"] = (st.session_state["gen_yaml"] or "").rstrip() + "\n\n" + snippet
                    st.success("生成結果エリアに追記しました。『検証/ドライラン』で確認してください。")
                else:
                    st.info("現在の自動生成エリアがありません。上のコードをコピーしてご利用ください。")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("検証"):
                _plan, errors, _ = validate_and_dryrun(yaml_text, registry, do_dryrun=False)
                if errors:
                    st.error("\n".join(errors))
                else:
                    st.success("検証OK")
        with col2:
            if st.button("ドライラン"):
                _plan, errors, dr_err = validate_and_dryrun(yaml_text, registry, do_dryrun=True)
                if errors:
                    st.error("\n".join(errors))
                elif dr_err is not None:
                    st.error(str(dr_err))
                else:
                    st.success("ドライランOK")
        with col3:
            if st.button("保存"):
                Path(plan_path).write_text(yaml_text, encoding="utf-8")
                st.success("保存しました")

        st.divider()
        st.subheader("Plan自動生成")
        has_llm_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
        if not has_llm_key:
            st.error("APIキーが設定されていません。設計の自動生成を行うには OPENAI_API_KEY または AZURE_OPENAI_API_KEY を設定してください。上の『APIキー設定』で保存できます。")
        instr = st.text_area("指示テキスト", value="請求書・入金明細を照合し、Excelに書き出す")
        uploaded_files = st.file_uploader(
            "参考文書をアップロード（任意・複数可: txt/md/pdf/docx/xlsx）",
            type=["txt", "md", "pdf", "docx", "xlsx"],
            accept_multiple_files=True,
        )
        use_when = st.checkbox("開始前に確認ダイアログ（when）を挿入", value=True)
        use_foreach = st.checkbox("foreachループを挿入（デモ）", value=False)
        foreach_var = st.text_input("foreach 入力の vars 名", value="items")
        if st.button("自動生成"):
            try:
                opts = DesignEngineOptions(suggest_when=use_when, suggest_foreach=use_foreach, foreach_var_name=foreach_var)
                # 抽出（軽量）: テキスト抽出はPDF/Docx/Xlsxも対応
                docs_text: List[str] | None = None
                if uploaded_files:
                    try:
                        from core.plan.text_extractor import extract_texts

                        docs_text = extract_texts([(f.name, f.read()) for f in uploaded_files])
                    except Exception:
                        docs_text = None
                try:
                    gen = generate_plan(instr, documents_text=docs_text, registry=registry, options=opts)
                    plan = gen.plan
                    errors = validate_plan(plan, registry)
                    if errors:
                        st.error("検証エラー:\n" + "\n".join(errors))
                    else:
                        try:
                            dry_run_plan(plan, registry)
                            st.success("自動生成→検証/ドライランOK")
                        except Exception as e:
                            st.error(f"ドライランエラー: {str(e)}")
                except Exception as e:
                    st.error(f"プラン生成エラー: {str(e)}")
                    # エラーが発生した場合は、planを設定しない
                    plan = None

                # 生成されたPlanをYAMLで編集→検証/ドライラン→登録
                if plan:
                    st.markdown("**生成結果（YAML, 編集可）**")
                    gen_yaml = yaml.safe_dump(plan.model_dump(by_alias=True), allow_unicode=True, sort_keys=False)
                    # セッションに保持
                    if "gen_yaml" not in st.session_state:
                        st.session_state["gen_yaml"] = gen_yaml
                        st.session_state["gen_ok"] = False
                    else:
                        st.session_state["gen_yaml"] = gen_yaml
            except Exception as e:
                st.error(str(e))

        # 生成済み（または前回の編集）YAMLの編集欄
        if "gen_yaml" in st.session_state:
            st.session_state["gen_yaml"] = st.text_area(
                "Plan YAML（編集して検証/登録できます）",
                value=st.session_state["gen_yaml"],
                height=400,
                key="gen_yaml_area",
            )
            colv, colr = st.columns(2)
            with colv:
                if st.button("検証/ドライラン"):
                    plan2, errors2, dr_err2 = validate_and_dryrun(st.session_state["gen_yaml"], registry, do_dryrun=True)
                    if errors2:
                        st.session_state["gen_ok"] = False
                        st.error("\n".join(errors2))
                    elif dr_err2 is not None:
                        st.session_state["gen_ok"] = False
                        st.error(str(dr_err2))
                    else:
                        st.session_state["gen_ok"] = True
                        st.success("検証/ドライランOK")
            with colr:
                disabled = not bool(st.session_state.get("gen_ok"))
                if st.button("登録", disabled=disabled):
                    plan3, errs, dr_err3 = validate_and_dryrun(st.session_state["gen_yaml"], registry, do_dryrun=True)
                    if errs:
                        st.error("\n".join(errs))
                    elif dr_err3 is not None:
                        st.error(str(dr_err3))
                    else:
                        designs_dir = Path("designs")
                        designs_dir.mkdir(parents=True, exist_ok=True)
                        ts = datetime.now(UTC).strftime("%Y%m%d%H%M")
                        out_path = designs_dir / f"{plan3.id}_{ts}.yaml"
                        data = plan3.model_dump(by_alias=True)
                        out_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
                        st.success(f"登録しました: {out_path}")

    with tabs[1]:
        st.subheader("業務実施")
        plans = list_designs()
        plan_path2 = st.selectbox("実行するPlanを選択", plans, key="exec_select")

        # 選択したプランのタイトルを表示
        plan = load_plan(plan_path2)
        st.markdown(f"> {plan.id}")
        try:
            instr_text = (plan.vars or {}).get("instruction")
        except Exception:
            instr_text = None
        if instr_text:
            st.info(instr_text)
        

        # フロー図プレースホルダ
        dag_area = st.empty()
        try:
            if plan_path2:
                plan_preview_for_dag = load_plan(plan_path2)
                from core.plan.dag_viz import generate_flow_html
                # これまでsuccessになったノードをセッションで永続
                success_key = f"flow_success::{plan_preview_for_dag.id}"
                succ = st.session_state.get(success_key)
                if succ is None:
                    succ = set()
                    st.session_state[success_key] = succ
                elif isinstance(succ, list):
                    succ = set(succ)
                    st.session_state[success_key] = succ
                states0 = {str(nid): "success" for nid in succ}
                html0 = generate_flow_html(plan_preview_for_dag, states0, include_loop_nodes=False)
                dag_area.markdown(html0, unsafe_allow_html=True)
        except Exception:
            pass

        st.divider()

        # 実行前に vars を編集可能にする
        edited_vars = {}
        default_hitl = True
        runner = PlanRunner(registry=registry, default_ui_hitl=default_hitl)
        # 実行結果クリアボタン
        col_actions1, col_actions2 = st.columns([1,1])
        with col_actions1:
            if st.button("実行結果をクリア"):
                # runs/<plan_id> の state.json を削除
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
                # Plan単位のセッションステート/ウィジェットキー/DAG成功状態/再開IDをクリア
                try:
                    from core.ui.session_state import SessionStateManager
                    SessionStateManager(plan.id, "clear").clear_plan_state()
                except Exception:
                    pass
                try:
                    _clear_ui_widget_state_for_plan(plan)
                except Exception:
                    pass
                try:
                    success_key = f"flow_success::{plan.id}"
                    if success_key in st.session_state:
                        del st.session_state[success_key]
                    for k in ["auto_resume_run_id", "last_run_id", "last_pending_ui"]:
                        if k in st.session_state:
                            del st.session_state[k]
                except Exception:
                    pass
                st.success("実行結果をクリアしました。『実行/再開』で最初からやり直せます。")
                st.rerun()
        with col_actions2:
            pass

        # 保留UIの検出と実際のUIブロック描画（手動run_id優先、なければ最新を自動検出）
        try:
            plan_for_pending = load_plan(plan_path2)
        except Exception:
            plan_for_pending = None

        pending = None
        pending_run_id: str | None = None
        if plan_for_pending is not None:
            state_dir = runner._state_dir / plan_for_pending.id
            # 優先: 直近の実行で設定された auto_resume_run_id を優先使用
            auto_rid = st.session_state.get("auto_resume_run_id")
            if auto_rid and state_dir.exists():
                f = state_dir / f"{auto_rid}.state.json"
                if f.exists():
                    try:
                        st_json = json.loads(f.read_text(encoding="utf-8"))
                        cand = st_json.get("pending_ui")
                        if cand and not cand.get("submitted"):
                            pending = cand
                            pending_run_id = auto_rid
                    except Exception:
                        pass
            # フォールバック: 最新の未提出 pending を自動検出
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

        if pending and plan_for_pending is not None and pending_run_id:
            # 実際のUIブロックを描画し、ユーザーの明示操作で保存できるようにする
            try:
                node_id = pending.get("node_id")
                node = next(n for n in plan_for_pending.graph if n.id == node_id)
                block = registry.get(node.block)
                from core.blocks.base import UIBlock, BlockContext
                if isinstance(block, UIBlock):
                    # no-op
                    # フロー図を『実行中(青)』として更新（runner外での保留UI表示時）
                    try:
                        from core.plan.dag_viz import generate_flow_html
                        _states = {n.id: "pending" for n in plan_for_pending.graph}
                        _states[str(node_id)] = "running"
                        # 永続成功ノードを反映
                        success_key = f"flow_success::{plan_for_pending.id}"
                        succ = st.session_state.get(success_key)
                        if isinstance(succ, list):
                            succ = set(succ)
                        if isinstance(succ, set):
                            for nid in succ:
                                _states[str(nid)] = "success"
                        html = generate_flow_html(plan_for_pending, _states, include_loop_nodes=False)
                        dag_area.markdown(html, unsafe_allow_html=True)
                    except Exception:
                        pass
                    # セッション再開IDを記憶（実行/再開ボタンで自動利用）
                    st.session_state["auto_resume_run_id"] = pending_run_id
                    # plan/ノード識別子を UI セッションステートに渡す
                    _vars = dict(plan_for_pending.vars)
                    try:
                        _vars["__plan_id"] = plan_for_pending.id
                        _vars["__node_id"] = str(node_id)
                    except Exception:
                        pass
                    ctx = BlockContext(run_id=pending_run_id, workspace=str(Path.cwd()), vars=_vars)
                    inputs_for_ui = dict(pending.get("inputs", {}) or {})
                    # run_id変化でもUI状態が残るよう、ノードIDベースの固定キーを渡す
                    try:
                        inputs_for_ui.setdefault("widget_key", str(node_id))
                    except Exception:
                        pass
                    with _disable_headless_for_ui():
                        out = block.render(ctx, inputs_for_ui)
                    # 必要出力が揃っているかを判定
                    required_local_keys = list(node.outputs.keys()) if node.outputs else []
                    ready = True
                    for k in required_local_keys:
                        if not isinstance(out, dict) or out.get(k) is None:
                            ready = False
                            break
                    # 入力が揃ったら自動保存（即時rerunはしない）。次回「実行/再開」で続きへ
                    if ready:
                        spath = runner._state_path(plan_for_pending.id, pending_run_id)
                        try:
                            cur = json.loads(spath.read_text(encoding="utf-8")) if spath.exists() else {}
                        except Exception:
                            cur = {}
                        # すでに他方でsubmittedになっていない場合のみ実行
                        # （同一描画サイクル内での二重書き込み抑止のため簡易チェック）
                        already_submitted = bool((cur.get("pending_ui") or {}).get("submitted"))
                        if not already_submitted:
                            pending["submitted"] = True
                            # bytes を JSON 保存用にエンコード
                            def _encode_for_json(v):
                                if isinstance(v, (bytes, bytearray)):
                                    return {"__type": "b64bytes", "data": base64.b64encode(v).decode("ascii")}
                                if isinstance(v, dict):
                                    return {kk: _encode_for_json(vv) for kk, vv in v.items()}
                                if isinstance(v, list):
                                    return [_encode_for_json(x) for x in v]
                                return v
                            pending["outputs"] = _encode_for_json(out)
                            # 併せて累積用マップにも格納（ノードごとに上書き保存）
                            try:
                                node_key = str(node_id)
                            except Exception:
                                node_key = str(pending.get("node_id", ""))
                            ui_outputs = cur.get("ui_outputs") or {}
                            ui_outputs[node_key] = pending["outputs"]
                            cur["ui_outputs"] = ui_outputs
                            cur["pending_ui"] = pending
                            runner._save_state(plan_for_pending, pending_run_id, cur)
                            # フロー図を『完了(緑)』で更新（runnerのui_submit発火前でも視覚反映）
                            try:
                                from core.plan.dag_viz import generate_flow_html
                                _states2 = {n.id: "pending" for n in plan_for_pending.graph}
                                # successノード集合に追加し、反映
                                success_key = f"flow_success::{plan_for_pending.id}"
                                succ = st.session_state.get(success_key)
                                if succ is None:
                                    succ = set()
                                elif isinstance(succ, list):
                                    succ = set(succ)
                                succ.add(str(node_id))
                                st.session_state[success_key] = succ
                                for nid in succ:
                                    _states2[str(nid)] = "success"
                                html2 = generate_flow_html(plan_for_pending, _states2, include_loop_nodes=False)
                                dag_area.markdown(html2, unsafe_allow_html=True)
                            except Exception:
                                pass
                        st.success("入力を保存しました。『実行/再開』を押して続きから再開してください。")
            except StopIteration:
                pass
        else:
            # 初期状態（全ノードpending）で表示
            try:
                from core.plan.dag_viz import generate_flow_html
                states_init = {n.id: "pending" for n in plan_for_pending.graph} if plan_for_pending else {}
                html_init = generate_flow_html(plan_for_pending, states_init, include_loop_nodes=False) if plan_for_pending else ""
                if html_init:
                    dag_area.markdown(html_init, unsafe_allow_html=True)
            except Exception:
                pass

        # 実行関数（再開/新規を切替）
        def _execute_run(resume_id: str | None) -> None:
            plan = load_plan(plan_path2)
            progress = st.progress(0, text="実行中...")
            status_area = st.empty()

            # 直近イベントの簡易ログ（読みやすいメッセージで表示）
            recent_msgs: list[tuple[str, str]] = []  # (severity, message)
            MAX_RECENT = 1

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

            total_estimate = max(1, len(plan.graph))
            done = {"count": 0}
            events_for_dag = []

            def on_event(ev):
                events_for_dag.append(ev)
                et = ev.get("type")
                if et in {"node_start", "node_finish", "node_skip", "error", "ui_wait", "ui_submit", "ui_reuse", "loop_start", "loop_finish", "loop_iter_start"}:
                    try:
                        from core.plan.dag_viz import compute_node_states, generate_flow_html
                        states = compute_node_states(plan, events_for_dag)
                        # 永続成功ノードを反映
                        success_key = f"flow_success::{plan.id}"
                        succ = st.session_state.get(success_key)
                        if succ is None:
                            succ = set()
                        elif isinstance(succ, list):
                            succ = set(succ)
                        # successに遷移したノードを追加
                        for nid, stt in states.items():
                            if stt == "success":
                                succ.add(str(nid))
                        # 一度successになったら常にsuccess
                        for nid in list(succ):
                            states[str(nid)] = "success"
                        st.session_state[success_key] = succ
                        html = generate_flow_html(plan, states, include_loop_nodes=False)
                        dag_area.markdown(html, unsafe_allow_html=True)
                    except Exception:
                        pass
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
                    st.session_state["last_run_id"] = ev.get("run_id")
                if et == "node_finish":
                    sev, msg = _format_event_message(ev)
                    _push_and_render(sev, msg)
                if et == "ui_wait":
                    # 次の描画で即時にUIを出せるようセッションに保持
                    st.session_state["last_pending_ui"] = ev

            with _disable_headless_for_ui():
                results = runner.run(
                    plan,
                    on_event=on_event,
                    vars_overrides=edited_vars or None,
                    resume_run_id=resume_id,
                )
            # UI待機が発生していれば次の描画で保留UI検出ロジックを作動させる
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
                                st.session_state["auto_resume_run_id"] = _rid
                                st.rerun()
                        except Exception:
                            continue
            except Exception:
                pass
            progress.progress(1.0, text="完了")
            with st.expander("結果の詳細(JSON)", expanded=False):
                st.json(results)
            # 出力方法: vars.output_method に従い UI を切り替え
            try:
                output_method = (plan.vars or {}).get("output_method", "download")
            except Exception:
                output_method = "download"

            try:
                # Planの out マッピングで 'workbook_updated'/'updated_workbook' に割り当てられたエイリアスを最優先で収集
                aliases_for_wb: list[str] = []
                try:
                    for n in getattr(plan, "graph", []) or []:
                        outs = getattr(n, "outputs", None)
                        if isinstance(outs, dict):
                            for local_out, alias in outs.items():
                                if local_out in ("workbook_updated", "updated_workbook") and isinstance(alias, str) and alias:
                                    aliases_for_wb.append(alias)
                    # 順序維持で重複排除
                    aliases_for_wb = list(dict.fromkeys(aliases_for_wb))
                except Exception:
                    aliases_for_wb = []

                workbooks: list[dict] = []
                seen_ids: set[int] = set()

                if isinstance(results, dict):
                    # 1) Plan定義のエイリアス名で収集
                    for alias in aliases_for_wb:
                        v = results.get(alias)
                        if isinstance(v, dict) and isinstance(v.get("bytes"), (bytes, bytearray)):
                            if id(v) not in seen_ids:
                                workbooks.append({"value": v, "label": alias})
                                seen_ids.add(id(v))
                    # 2) フォールバック: 代表キー名
                    for key in ("workbook_updated", "updated_workbook"):
                        v = results.get(key)
                        if isinstance(v, dict) and isinstance(v.get("bytes"), (bytes, bytearray)):
                            if id(v) not in seen_ids:
                                workbooks.append({"value": v, "label": key})
                                seen_ids.add(id(v))
                    # 3) 最終: bytes を含む辞書の走査（カスタム名対策）
                    for k_any, v_any in results.items():
                        if isinstance(v_any, dict) and isinstance(v_any.get("bytes"), (bytes, bytearray)):
                            if id(v_any) not in seen_ids:
                                workbooks.append({"value": v_any, "label": str(k_any)})
                                seen_ids.add(id(v_any))

                # 収集できたすべてのワークブックに対してボタンを表示
                if workbooks:
                    for idx, item in enumerate(workbooks):
                        wb_dict = item["value"]
                        label = item["label"]
                        wb_bytes = wb_dict.get("bytes")
                        fname = (wb_dict.get("name") or f"workbook_updated_{idx+1}.xlsx") if isinstance(wb_dict.get("name"), str) else f"workbook_updated_{idx+1}.xlsx"
                        if isinstance(wb_bytes, (bytes, bytearray)):
                            if output_method in ("download", "both"):
                                st.download_button(
                                    f"更新済みExcelをダウンロード: {label}",
                                    data=wb_bytes,
                                    file_name=fname,
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"dl_wb_{idx}",
                                )
                            if output_method in ("save_runs", "both"):
                                if st.button(f"runs フォルダに保存: {label}", key=f"save_wb_{idx}"):
                                    out_dir = Path("runs") / plan.id
                                    out_dir.mkdir(parents=True, exist_ok=True)
                                    run_id = st.session_state.get("last_run_id") or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                                    out_path = out_dir / f"{run_id}_updated_{idx+1}.xlsx"
                                    out_path.write_bytes(wb_bytes)  # type: ignore[arg-type]
                                    st.success(f"保存しました: {out_path}")
            except Exception as _dl_err:
                st.warning(f"Excel出力UIの構築でエラー: {_dl_err}")
            # 代替: base64エンコードの別名もサポート
            try:
                if isinstance(results, dict):
                    # Planの out マッピングで 'workbook_b64'/'updated_workbook_b64' を優先収集
                    aliases_for_b64: list[str] = []
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

                    b64_items: list[tuple[str, str]] = []
                    seen_vals: set[str] = set()

                    # 1) エイリアスで収集
                    for alias in aliases_for_b64:
                        val = results.get(alias)
                        if isinstance(val, str) and val:
                            if val not in seen_vals:
                                b64_items.append((alias, val))
                                seen_vals.add(val)
                    # 2) 代表キー名
                    for key in ("workbook_b64", "updated_workbook_b64"):
                        val = results.get(key)
                        if isinstance(val, str) and val:
                            if val not in seen_vals:
                                b64_items.append((key, val))
                                seen_vals.add(val)
                    # 3) サフィックス一致（_b64）
                    for k_any, v_any in results.items():
                        if isinstance(v_any, str) and str(k_any).endswith("_b64") and v_any:
                            if v_any not in seen_vals:
                                b64_items.append((str(k_any), v_any))
                                seen_vals.add(v_any)

                    if b64_items and output_method in ("download", "both"):
                        import base64 as _b64
                        for idx, (label, b64) in enumerate(b64_items):
                            st.download_button(
                                f"更新済みExcelをダウンロード (b64): {label}",
                                data=_b64.b64decode(b64),
                                file_name=f"workbook_updated_{idx+1}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key=f"dl_wb_b64_{idx}",
                            )
            except Exception:
                pass

        # 実行ボタン
        if st.button("実行/再開"):
            resume_id = st.session_state.get("auto_resume_run_id") or None
            _execute_run(resume_id=resume_id)

    with tabs[2]:
        st.subheader("ログ")
        runs_dir = Path("runs")
        if not runs_dir.exists():
            st.info("まだログがありません")
        else:
            plans = sorted({p.parent.name for p in runs_dir.rglob("*.jsonl")})
            if not plans:
                st.info("まだログがありません")
            else:
                selected = st.selectbox("Plan", plans)
                if selected is None:
                    st.stop()
                files = sorted((runs_dir / selected).glob("*.jsonl"), reverse=True)
                if not files:
                    st.info("選択したPlanのログがありません")
                else:
                    file = st.selectbox("Run", files)
                    if file:
                        try:
                            text = file.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            text = ""
                        lines = text.splitlines()
                        events = []
                        for l in lines:
                            s = str(l).strip()
                            if not s:
                                continue
                            try:
                                events.append(json.loads(s))
                            except Exception:
                                continue

                        # 簡易フィルタ
                        types = sorted({e.get("type") for e in events})
                        sel_types = st.multiselect("イベント種類", options=types, default=types)
                        # 親子run_idでスレッドを追跡
                        parent = st.text_input("parent_run_id フィルタ", value="")
                        filtered = [e for e in events if e.get("type") in sel_types]
                        if parent:
                            filtered = [e for e in filtered if e.get("parent_run_id") == parent or e.get("run_id") == parent]
                        st.write(f"{len(filtered)} events")
                        # サマリ（成功/失敗/スキップ）
                        ok = sum(1 for e in filtered if e.get("type") == "node_finish")
                        err = sum(1 for e in filtered if e.get("type") == "error")
                        skipped = sum(1 for e in filtered if e.get("type") == "node_skip")
                        st.write({"node_finish": ok, "error": err, "node_skip": skipped})
                        # フロー図（線形・色分け）
                        try:
                            from core.plan.loader import load_plan as _load_plan_for_viz
                            from core.plan.dag_viz import compute_node_states, generate_flow_html
                            from core.plan.models import Plan as _PlanModel

                            # 1) designs/<id>.yaml を優先的に読む
                            _plan_viz = None
                            plan_file = Path("designs") / f"{selected}.yaml"
                            if plan_file.exists():
                                _plan_viz = _load_plan_for_viz(plan_file)
                            else:
                                # 2) designs 配下を走査し、id が一致する YAML を探す（タイムスタンプ付きファイル等に対応）
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

                            # 3) それでも見つからない場合、ログ内の start イベントから plan_spec を復元
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
                            st.warning(f"DAG可視化でエラー: {_viz_err}")
                        st.json(filtered)
                        if not filtered and lines:
                            st.info("イベントの解析に失敗したため、Rawログを表示します。")
                            st.text_area("Raw JSONL", value="\n".join(lines), height=200)
                        st.download_button("JSONL ダウンロード", data="\n".join(lines), file_name=file.name, mime="application/jsonl")


if __name__ == "__main__":
    main()


