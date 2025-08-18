from __future__ import annotations

import os
from datetime import datetime, UTC
import json
from pathlib import Path
from typing import List, Optional

import streamlit as st
import yaml


from core.blocks.registry import BlockRegistry
from core.plan.design_engine import (
    generate_business_overview,
    generate_plan_skeleton,
    generate_detail_plan,
    DesignEngineOptions,
)
from core.plan.templates import load_all_templates
# Design QA は使用しないためインポートを無効化
# from core.plan.design_requirements import (
#     build_requirements_from_plan_or_errors,
#     build_requirements_from_overview_dict,
#     build_requirements_from_skeleton_dict,
# )
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan
from ui.plan_utils import list_designs, validate_and_dryrun_yaml


def _iterate_business_overview(
    instr_with_answers: str,
    docs_text: List[str] | None,
    input_key_prefix: str,
    show_unresolved_error: bool = False,
) -> None:
    try:
        ov = generate_business_overview(instr_with_answers, docs_text)
        st.session_state["dg_overview"] = ov.model_dump()

    except Exception as e:
        st.error(str(e))


def _render_open_points_inputs(
    open_points: list,
    input_key_prefix: str,
    show_warning: bool = True,
) -> tuple[list[str], bool]:
    answers: list[str] = []
    for op in open_points:
        res_op = st.text_input(op, value="", key=f"{input_key_prefix}_{op}")
        answers.append(f"{op} → 回答： {res_op}")
    all_filled = all(ans.split("：", 1)[-1].strip() for ans in answers)
    return answers, all_filled


# def _render_skeleton_vars_inputs(
#     skeleton: dict,
#     input_key_prefix: str,
#     show_warning: bool = True,
# ) -> tuple[dict, bool]:
#     try:
#         var_refs = (skeleton.get("vars_placeholders") or []) if isinstance(skeleton, dict) else []
#         var_keys = [r[5:] if isinstance(r, str) and r.startswith("vars.") else r for r in var_refs if isinstance(r, str)]
#         var_keys = [k for k in var_keys if k]
#     except Exception:
#         var_keys = []
#     if show_warning and var_keys:
#         st.warning("追加の前提事項が必要です。下記項目に回答してください。")
#     filled: dict = {}
#     for k in var_keys:
#         val = st.text_input(f"変数 {k}", value="", key=f"{input_key_prefix}_{k}")
#         filled[k] = val
#     all_filled = all(str(v).strip() for v in filled.values()) if var_keys else True
#     return filled, all_filled


def _iterate_plan_skeleton(
    overview_dict: dict,
    registry: BlockRegistry,
    selected_templates: list[str] | None,
    res_qa: Optional[str] = None,
) -> None:
    try:
        from core.plan.design_engine import BusinessOverview as _BO
        ov = _BO.model_validate(overview_dict)
        sk = generate_plan_skeleton(ov, registry, selected_templates=selected_templates, res_qa=res_qa)
        st.session_state["dg_skeleton"] = sk.model_dump()
    except Exception as e:
        st.error(str(e))

def _iterate_detail_plan(
    skeleton: dict,
    registry: BlockRegistry,
    selected_templates: list[str] | None,
    res_qa: Optional[str] = None,
) -> None:
    try:
        from core.plan.design_engine import PlanSkeleton as _PS
        sk = _PS.model_validate(skeleton)
        gen = generate_detail_plan(sk, registry, selected_templates=selected_templates, res_qa=res_qa)
        st.session_state["dg_detail"] = gen.model_dump()
    except Exception as e:
        st.error(str(e))

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

    with st.expander("ブロックカタログ"):
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

        # スニペット機能は段階生成方針により撤廃

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
    st.subheader("段階生成（概要→スケルトン→詳細→登録）")
    has_llm_key = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
    if not has_llm_key:
        st.error("APIキーが設定されていません。自動生成には OPENAI_API_KEY または AZURE_OPENAI_API_KEY が必要です。")

    # Step 1: Business Overview
    st.markdown("**1) 業務概要作成**")
    instr = st.text_area("指示テキスト", value="請求書・入金明細を照合し、Excelに書き出す")
    uploaded_files = st.file_uploader(
        "参考文書（任意・複数可: txt/md/pdf/docx/xlsx）",
        type=["txt", "md", "pdf", "docx", "xlsx"],
        accept_multiple_files=True,
        key="dg_files",
    )
        
    if st.button("業務概要を生成"):
        docs_text: List[str] | None = None
        if uploaded_files:
            try:
                from core.plan.text_extractor import extract_texts

                docs_text = extract_texts([(f.name, f.read()) for f in uploaded_files])
            except Exception:
                docs_text = None
        st.session_state["dg_docs_text"] = docs_text
        st.session_state["dg_open_points_key_prefix"] = "op"

        _iterate_business_overview(instr, docs_text, input_key_prefix="op", show_unresolved_error=False)

    if "dg_overview" in st.session_state:
        open_points = st.session_state["dg_overview"].get("open_points", [])
        open_points_answers = []
        _prefix = st.session_state.get("dg_open_points_key_prefix", "op2")
        if len(open_points) > 0: 
            open_points_answers, _ = _render_open_points_inputs(open_points, _prefix)

        if open_points:
            if st.button("業務概要を再生成"):
                instr_with_answers = instr + "\n # 補足事項\n ## " + "\n ## ".join(open_points_answers)
                st.session_state["dg_overview_qa"] = instr_with_answers
                st.session_state["dg_open_points_key_prefix"] = "op3"
                _iterate_business_overview(
                    instr_with_answers,
                    st.session_state["dg_docs_text"],
                    input_key_prefix="op3",
                    show_unresolved_error=True,
                )
                st.rerun()

        if st.session_state["dg_overview"].get("open_points", []) == []:
            st.success("業務概要を生成しました。内容を適宜編集して概要プラン作成に進んでください。")
            st.text_area("業務概要(編集可)", value=json.dumps(st.session_state["dg_overview"], ensure_ascii=False, indent=2), height=220, key="dg_overview_area")
            with st.expander("問い合わせ履歴"):
                st.text(st.session_state["dg_overview_qa"])

    # Step 2: Plan Skeleton
    st.markdown("**2) 概要プラン生成**")
    tpl_ids = []
    try:
        all_tpl = load_all_templates()
        tpl_ids = sorted(all_tpl.keys())
    except Exception:
        tpl_ids = []
    selected_tpl = st.multiselect("テンプレート選択（任意）", options=tpl_ids, key="dg_tpls")

    if st.button("プラン概要を生成"):
        st.session_state["dg_skeleton_key_prefix"] = "sk"

        _iterate_plan_skeleton(
            st.session_state["dg_overview"],
            registry,
            selected_templates=selected_tpl
        )

    if "dg_skeleton" in st.session_state:
        open_points = st.session_state["dg_skeleton"].get("open_points", [])
        open_points_answers = []
        _prefix = st.session_state.get("dg_skeleton_key_prefix", "sk2")
        if len(open_points) > 0:
            open_points_answers, _ = _render_open_points_inputs(open_points, _prefix)

        if open_points:
            if st.button("プラン概要を再生成"):
                instr_with_answers = "# 補足事項\n ## " + "\n ## ".join(open_points_answers)
                st.session_state["dg_skeleton_qa"] = instr_with_answers
                st.session_state["dg_skeleton_key_prefix"] = "sk3"
                _iterate_plan_skeleton(
                    st.session_state["dg_overview"],
                    registry,
                    selected_templates=selected_tpl,
                    res_qa=st.session_state["dg_skeleton_qa"]
                )
                st.rerun()

        if st.session_state["dg_skeleton"].get("open_points", []) == []:
            st.success("プラン概要を生成しました。内容を適宜編集して詳細プラン生成に進んでください。")
            st.text_area("プラン概要(編集可)", value=json.dumps(st.session_state["dg_skeleton"], ensure_ascii=False, indent=2), height=220, key="dg_skeleton_area")
            with st.expander("問い合わせ履歴"):
                st.text(st.session_state.get("dg_skeleton_qa", ""))


    # Step 3: Detailing
    st.markdown("**3) 詳細プラン作成**")
    if st.button("詳細プラン生成"):
        if "dg_skeleton" not in st.session_state:
            st.error("先に概要プランを生成してください。")
        st.session_state["dg_detail_key_prefix"] = "dt"

        _iterate_detail_plan(
            st.session_state["dg_skeleton"],
            registry,
            selected_templates=selected_tpl
            )

    if "dg_detail" in st.session_state:
        open_points = st.session_state["dg_detail"].get("open_points", [])
        open_points_answers = []
        _prefix = st.session_state.get("dg_detail_key_prefix", "dt2")
        if len(open_points) > 0:
            open_points_answers, _ = _render_open_points_inputs(open_points, _prefix)

        if open_points:
            if st.button("詳細プランを再生成"):
                instr_with_answers = "# 補足事項\n ## " + "\n ## ".join(open_points_answers)
                st.session_state["dg_detail_qa"] = instr_with_answers
                st.session_state["dg_detail_key_prefix"] = "dt3"
                _iterate_detail_plan(
                    st.session_state["dg_skeleton"],
                    registry,
                    selected_templates=selected_tpl,
                    res_qa=st.session_state["dg_detail_qa"]
                )
                st.rerun()

        if st.session_state["dg_detail"].get("open_points", []) == []:
            st.success("詳細プランを生成しました。内容を適宜編集して登録に進んでください。")
            st.text_area("詳細プラン(編集可)", value=json.dumps(st.session_state["dg_detail"], ensure_ascii=False, indent=2), height=220, key="dg_detail_area")
            with st.expander("問い合わせ履歴"):
                st.text(st.session_state.get("dg_detail_qa", ""))

            try:
                validate_and_dryrun_yaml(str(st.session_state["dg_detail"]), registry, do_dryrun=True)
            except Exception as e:
                st.error(f"ドライランエラー: {str(e)}")
        
    if "dg_detail" in st.session_state:
        st.session_state["gen_yaml"] = st.text_area(
            "Plan YAML（編集して検証/登録できます）",
            value=st.session_state["dg_detail"],
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


