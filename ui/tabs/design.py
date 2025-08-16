from __future__ import annotations

import os
from datetime import datetime, UTC
from pathlib import Path
from typing import List

import streamlit as st
import yaml

from core.blocks.registry import BlockRegistry
from core.plan.design_engine import generate_plan, DesignEngineOptions
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan
from ui.plan_utils import list_designs, validate_and_dryrun_yaml


def render(registry: BlockRegistry) -> None:
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
        specs = []
        missing_imports = set()
        for bid, lst in registry.specs_by_id.items():
            spec = lst[-1]
            try:
                inputs = ",".join(sorted((spec.inputs or {}).keys()))
                outputs = ",".join(sorted((spec.outputs or {}).keys()))
            except Exception:
                inputs, outputs = "", ""
            reqs = []
            try:
                for r in (spec.requirements or []):
                    reqs.append(r)
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
            _plan, errors, _ = validate_and_dryrun_yaml(yaml_text, registry, do_dryrun=False)
            if errors:
                st.error("\n".join(errors))
            else:
                st.success("検証OK")
    with col2:
        if st.button("ドライラン"):
            _plan, errors, dr_err = validate_and_dryrun_yaml(yaml_text, registry, do_dryrun=True)
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
                plan = None

            if plan:
                st.markdown("**生成結果（YAML, 編集可）**")
                gen_yaml = yaml.safe_dump(plan.model_dump(by_alias=True), allow_unicode=True, sort_keys=False)
                if "gen_yaml" not in st.session_state:
                    st.session_state["gen_yaml"] = gen_yaml
                    st.session_state["gen_ok"] = False
                else:
                    st.session_state["gen_yaml"] = gen_yaml
        except Exception as e:
            st.error(str(e))

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
                plan2, errors2, dr_err2 = validate_and_dryrun_yaml(st.session_state["gen_yaml"], registry, do_dryrun=True)
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
                plan3, errs, dr_err3 = validate_and_dryrun_yaml(st.session_state["gen_yaml"], registry, do_dryrun=True)
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


