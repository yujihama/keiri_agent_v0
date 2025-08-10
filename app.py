from __future__ import annotations

import json
from datetime import datetime, UTC
import base64
from pathlib import Path
from typing import List
import os
import yaml

import streamlit as st

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan
from core.plan.design_engine import generate_plan, DesignEngineOptions
from core.plan.runner import PlanRunner


def list_designs() -> List[Path]:
    designs_dir = (Path.cwd() / "designs").resolve()
    return sorted(designs_dir.rglob("*.yaml"))


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
                try:
                    tmp = Path(".tmp_plan.yaml")
                    tmp.write_text(yaml_text, encoding="utf-8")
                    plan = load_plan(tmp)
                    errors = validate_plan(plan, registry)
                    if errors:
                        st.error("\n".join(errors))
                    else:
                        st.success("検証OK")
                finally:
                    if tmp.exists():
                        tmp.unlink()
        with col2:
            if st.button("ドライラン"):
                try:
                    tmp = Path(".tmp_plan.yaml")
                    tmp.write_text(yaml_text, encoding="utf-8")
                    plan = load_plan(tmp)
                    dry_run_plan(plan, registry)
                    st.success("ドライランOK")
                except Exception as e:
                    st.error(str(e))
                finally:
                    if tmp.exists():
                        tmp.unlink()
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
                gen = generate_plan(instr, documents_text=docs_text, registry=registry, options=opts)
                plan = gen.plan
                errors = validate_plan(plan, registry)
                if errors:
                    st.error("\n".join(errors))
                else:
                    try:
                        dry_run_plan(plan, registry)
                        st.success("自動生成→検証/ドライランOK")
                    except Exception as e:
                        st.error(str(e))

                # 生成されたPlanをYAMLで編集→検証/ドライラン→登録
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
                    try:
                        tmp = Path(".tmp_generated_plan.yaml")
                        tmp.write_text(st.session_state["gen_yaml"], encoding="utf-8")
                        plan2 = load_plan(tmp)
                        errors2 = validate_plan(plan2, registry)
                        if errors2:
                            st.session_state["gen_ok"] = False
                            st.error("\n".join(errors2))
                        else:
                            dry_run_plan(plan2, registry)
                            st.session_state["gen_ok"] = True
                            st.success("検証/ドライランOK")
                    except Exception as e:
                        st.session_state["gen_ok"] = False
                        st.error(str(e))
                    finally:
                        if 'tmp' in locals() and tmp.exists():
                            tmp.unlink()
            with colr:
                disabled = not bool(st.session_state.get("gen_ok"))
                if st.button("登録", disabled=disabled):
                    try:
                        tmp = Path(".tmp_generated_plan.yaml")
                        tmp.write_text(st.session_state["gen_yaml"], encoding="utf-8")
                        plan3 = load_plan(tmp)
                        # 念のためもう一度チェック
                        errs = validate_plan(plan3, registry)
                        if errs:
                            st.error("\n".join(errs))
                        else:
                            dry_run_plan(plan3, registry)
                            designs_dir = Path("designs")
                            designs_dir.mkdir(parents=True, exist_ok=True)
                            ts = datetime.now(UTC).strftime("%Y%m%d%H%M")
                            out_path = designs_dir / f"{plan3.id}_{ts}.yaml"
                            data = plan3.model_dump(by_alias=True)
                            out_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
                            st.success(f"登録しました: {out_path}")
                    except Exception as e:
                        st.error(str(e))
                    finally:
                        if 'tmp' in locals() and tmp.exists():
                            tmp.unlink()

    with tabs[1]:
        st.subheader("業務実施")
        plans = list_designs()
        plan_path2 = st.selectbox("実行するPlanを選択", plans, key="exec_select")
        # ウィジェット生成前に初期値をセッションへ設定（既にユーザーが入力している場合は尊重）
        if not st.session_state.get("resume_run_id_input"):
            st.session_state["resume_run_id_input"] = st.session_state.get("auto_resume_run_id", "")
        run_id_for_resume = st.text_input("再開する run_id (任意)", key="resume_run_id_input")
        # 実行前に vars を編集可能にする
        if plan_path2:
            with st.expander("vars を編集"):
                plan_preview = load_plan(plan_path2)
                edited_vars = {}
                for k, v in (plan_preview.vars or {}).items():
                    if isinstance(v, (int, float)):
                        edited_vars[k] = st.number_input(f"vars.{k}", value=float(v))
                    elif isinstance(v, bool):
                        edited_vars[k] = st.checkbox(f"vars.{k}", value=v)
                    else:
                        edited_vars[k] = st.text_input(f"vars.{k}", value=str(v))
        # APIキーの入力（セッションに格納）
        with st.expander("APIキー設定"):
            openai_key = st.text_input("OPENAI_API_KEY", type="password")
            azure_key = st.text_input("AZURE_OPENAI_API_KEY", type="password")
            if st.button("保存（セッション）"):
                if openai_key:
                    os.environ["OPENAI_API_KEY"] = openai_key
                if azure_key:
                    os.environ["AZURE_OPENAI_API_KEY"] = azure_key
                st.success("保存しました")

        # UIノードを既定でHITLにするオプション（既定で有効）
        default_hitl = st.checkbox("UIノードを既定で人手待機(HITL)にする", value=True)
        runner = PlanRunner(registry=registry, default_ui_hitl=default_hitl)

        # 保留UIの検出と実際のUIブロック描画（手動run_id優先、なければ最新を自動検出）
        try:
            plan_for_pending = load_plan(plan_path2)
        except Exception:
            plan_for_pending = None

        pending = None
        pending_run_id: str | None = None
        if plan_for_pending is not None:
            # 1) ユーザー指定run_idの保留状態
            if run_id_for_resume:
                sp = runner._state_path(plan_for_pending.id, run_id_for_resume)
                if sp.exists():
                    try:
                        st_json = json.loads(sp.read_text(encoding="utf-8"))
                        cand = st_json.get("pending_ui")
                        if cand and not cand.get("submitted"):
                            pending = cand
                            pending_run_id = run_id_for_resume
                    except Exception:
                        pass
            # 2) 自動検出（最新の保留UI）
            if pending is None:
                state_dir = runner._state_dir / plan_for_pending.id
                if state_dir.exists():
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
            # 実際のUIブロックを描画して出力が揃えばstateに保存
            try:
                node_id = pending.get("node_id")
                node = next(n for n in plan_for_pending.graph if n.id == node_id)
                block = registry.get(node.block)
                from core.blocks.base import UIBlock, BlockContext
                if isinstance(block, UIBlock):
                    st.info(f"待機中のUIがあります: node={node_id}")
                    # セッション再開IDを記憶（実行/再開ボタンで自動利用）
                    st.session_state["auto_resume_run_id"] = pending_run_id
                    ctx = BlockContext(run_id=pending_run_id, workspace=str(Path.cwd()), vars=dict(plan_for_pending.vars))
                    inputs_for_ui = pending.get("inputs", {})
                    out = block.render(ctx, inputs_for_ui)
                    # 必要出力が揃ったら保存
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
                        except Exception:
                            cur = {}
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
                        st.success("入力を保存しました。ページを再描画します。『実行/再開』を押して続きから再開してください。")
                        st.rerun()
            except StopIteration:
                pass

        # （デバッグUIは削除）

        if st.button("実行/再開"):
            plan = load_plan(plan_path2)
            progress = st.progress(0, text="実行中...")
            status_area = st.empty()

            total_estimate = max(1, len(plan.graph))
            done = {"count": 0}

            def on_event(ev):
                et = ev.get("type")
                if et in {"node_finish", "loop_finish", "subflow_finish"}:
                    done["count"] += 1
                    progress.progress(min(1.0, done["count"] / total_estimate), text=f"{done['count']}/{total_estimate}")
                if et in {"loop_start", "loop_finish", "loop_iter_start", "loop_iter_finish", "subflow_start"}:
                    status_area.write(ev)
                if et == "error":
                    status_area.error(ev)
                if et == "start":
                    st.session_state["last_run_id"] = ev.get("run_id")
                if et == "node_finish":
                    ms = ev.get("elapsed_ms")
                    att = ev.get("attempts")
                    if ms is not None or att is not None:
                        status_area.write({"node": ev.get("node"), "elapsed_ms": ms, "attempts": att})
                if et == "ui_wait":
                    # 次の描画で即時にUIを出せるようセッションに保持
                    st.session_state["last_pending_ui"] = ev

            # env表示/編集（簡易）
            with st.expander("環境変数 (read-only)"):
                st.json({k: v for k, v in os.environ.items() if k.startswith("OPENAI") or k.startswith("AZURE")})
            # 設定プレビュー
            with st.expander("設定 (config/*) プレビュー"):
                try:
                    from core.plan.config_store import get_store
                    store = get_store()
                    store.load_all()
                    st.json({ns: list(data.keys())[:10] for ns, data in getattr(store, "_data_by_ns", {}).items()})
                except Exception as e:
                    st.warning(f"設定の読み込みに失敗: {e}")

            # 手動run_id > 自動検出run_id > 新規
            resume_id = run_id_for_resume or st.session_state.get("auto_resume_run_id") or None
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
            st.json(results)
            # 出力方法: vars.output_method に従い UI を切り替え
            try:
                output_method = (plan.vars or {}).get("output_method", "download")
            except Exception:
                output_method = "download"

            try:
                # results は alias ベース。YAMLで out alias を設定している場合はそちらも参照
                wb_upd = None
                if isinstance(results, dict):
                    wb_upd = results.get("workbook_updated") or results.get("updated_workbook")
                if isinstance(wb_upd, dict):
                    wb_bytes = wb_upd.get("bytes")
                    fname = wb_upd.get("name") or "workbook_updated.xlsx"
                    if isinstance(wb_bytes, (bytes, bytearray)):
                        if output_method in ("download", "both"):
                            st.download_button(
                                "更新済みExcelをダウンロード",
                                data=wb_bytes,
                                file_name=fname,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            )
                        if output_method in ("save_runs", "both"):
                            if st.button("runs フォルダに保存"):
                                out_dir = Path("runs") / plan.id
                                out_dir.mkdir(parents=True, exist_ok=True)
                                run_id = st.session_state.get("last_run_id") or datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                                out_path = out_dir / f"{run_id}_updated.xlsx"
                                out_path.write_bytes(wb_bytes)  # type: ignore[arg-type]
                                st.success(f"保存しました: {out_path}")
            except Exception as _dl_err:
                st.warning(f"Excel出力UIの構築でエラー: {_dl_err}")
            # 代替: base64エンコードの別名もサポート
            try:
                if isinstance(results, dict):
                    b64 = results.get("workbook_b64") or results.get("updated_workbook_b64")
                    if isinstance(b64, str) and b64 and output_method in ("download", "both"):
                        import base64 as _b64
                        st.download_button(
                            "更新済みExcelをダウンロード (b64)",
                            data=_b64.b64decode(b64),
                            file_name="workbook_updated.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        )
            except Exception:
                pass

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
                        lines = file.read_text(encoding="utf-8").splitlines()
                        events = [json.loads(l) for l in lines if l.strip()]
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
                        # DAG可視化（色分け）
                        try:
                            from core.plan.loader import load_plan as _load_plan_for_viz
                            from core.plan.dag_viz import compute_node_states, draw_plan_dag

                            plan_file = Path("designs") / f"{selected}.yaml"
                            if plan_file.exists():
                                _plan_viz = _load_plan_for_viz(plan_file)
                                states = compute_node_states(_plan_viz, filtered)
                                fig = draw_plan_dag(_plan_viz, states)
                                st.pyplot(fig)
                        except Exception as _viz_err:
                            st.warning(f"DAG可視化でエラー: {_viz_err}")
                        st.json(filtered)
                        st.download_button("JSONL ダウンロード", data="\n".join(lines), file_name=file.name, mime="application/jsonl")


if __name__ == "__main__":
    main()


