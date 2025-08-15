from __future__ import annotations

from typing import Any, Dict, List, Optional
import os
import json
from datetime import datetime

import streamlit as st

from core.blocks.base import BlockContext, UIBlock
from core.ui.session_state import SessionStateManager, NodeStateContext
from typing import Optional as _Optional
from core.plan.logger import export_log

# LLM 連携（既存の ai.process_llm に合わせた依存）
try:  # 遅延インポートに近い扱い（環境未設定時でもUIは描画）
    from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
    from pydantic import BaseModel, Field, ConfigDict, create_model  # type: ignore
    from core.plan.llm_factory import build_chat_llm  # type: ignore
except Exception:  # pragma: no cover - LLM未設定環境での型/依存の安全確保
    build_chat_llm = None  # type: ignore
    SystemMessage = None  # type: ignore
    HumanMessage = None  # type: ignore
    BaseModel = object  # type: ignore
    def Field(*args, **kwargs):  # type: ignore
        return None


class InteractiveInputBlock(UIBlock):
    """汎用インタラクティブ入力UIブロック
    
    様々なモードで動作し、ファイルアップロード、フォーム入力、
    チャット形式での情報収集を統合的に提供する
    """
    
    id = "ui.interactive_input"
    version = "0.1.0"

    def render(self, ctx: BlockContext, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        # ヘッドレスモードの処理（引数ベース）
        if execution_context and getattr(execution_context, 'headless_mode', False):
            # node_id を付与してモック応答の選択を正確化
            _inputs = dict(inputs)
            _inputs.setdefault("node_id", ctx.vars.get("__node_id", ""))
            return self._headless_response(_inputs, execution_context)
        
        mode = inputs.get("mode", "collect")
        message = inputs.get("message", "")
        requirements = inputs.get("requirements", [])
        context = inputs.get("context", {})
        base_key = str(inputs.get("widget_key") or ctx.run_id)
        
        # メッセージ表示
        if message:
            st.info(message)
        
        # コンテキスト情報の表示（あれば）
        if context:
            with st.expander("コンテキスト情報", expanded=False):
                st.json(context)
        
        # モードに応じた処理
        if mode == "collect":
            return self._render_collect_mode(ctx, requirements, base_key)
        elif mode == "confirm":
            return self._render_confirm_mode(ctx, message, context)
        elif mode == "inquire":
            return self._render_inquire_mode(ctx, requirements, message, context, base_key)
        elif mode == "mixed":
            return self._render_mixed_mode(ctx, requirements, message, context, base_key)
        else:
            raise ValueError(f"Unknown mode: {mode}")
    
    def _render_collect_mode(self, ctx: BlockContext, requirements: List[Dict], base_key: str) -> Dict[str, Any]:
        """データ収集モード（フォーム確定方式）。

        - 画面のクリアを防ぐため、確定ボタンを押下するまで出力を返さない
        - 各ウィジェット値はセッションステートで維持
        """
        # Use unified session state management
        state_manager = SessionStateManager(ctx.vars.get("__plan_id", "default"), ctx.run_id)
        node_id = ctx.vars.get("__node_id", base_key)
        
        with NodeStateContext(ctx.vars.get("__plan_id", "default"), ctx.run_id, node_id, self.version) as state:
            # 既に確定済みならサマリー表示を残す
            if state.get("submitted", False):
                snapshot = state.get("snapshot", {})
                st.success("入力が確定しました")
                with st.expander("入力内容", expanded=True):
                    st.json(snapshot)
                return {
                    "collected_data": snapshot,
                    "approved": True,
                    "response": None,
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "mode": "collect",
                        "submitted": True,
                    },
                }

            collected_data: Dict[str, Any] = {}

            form_key = f"collect_form_{base_key}"
            with st.form(key=form_key, clear_on_submit=False):
                for req in requirements:
                    field_id = req.get("id")
                    field_type = req.get("type")
                    label = req.get("label", field_id)
                    description = req.get("description", "")
                    hint = req.get("hint", "")
                    required = req.get("required", True)

                    # hintがある場合は説明に追加
                    full_description = description
                    if hint:
                        full_description = f"{description}\n💡 ヒント: {hint}" if description else f"💡 ヒント: {hint}"

                    # フィールドタイプに応じた入力UI
                    if field_type == "file":
                        value = self._render_file_input(base_key, field_id, label, full_description, req.get("accept"), required)
                    elif field_type == "files":
                        value = self._render_files_input(base_key, field_id, label, full_description, req.get("accept"), required)
                    elif field_type == "folder":
                        value = self._render_folder_input(base_key, field_id, label, full_description, req.get("accept"), required)
                    elif field_type == "text":
                        value = self._render_text_input(base_key, field_id, label, full_description, required)
                    elif field_type == "select":
                        value = self._render_select_input(base_key, field_id, label, full_description, req.get("options", []), required)
                    elif field_type == "boolean":
                        value = self._render_boolean_input(base_key, field_id, label, full_description)
                    elif field_type == "number":
                        value = self._render_number_input(base_key, field_id, label, full_description, required)
                    elif field_type == "chat":
                        value = self._render_chat_input(base_key, field_id, label, full_description)
                    else:
                        st.warning(f"Unknown field type: {field_type}")
                        value = None

                    # 値をセッションに保持し、未入力時は保持値を使用
                    vkey = f"value_{base_key}_{field_id}"
                    if value is not None:
                        st.session_state[vkey] = value
                    value_eff = st.session_state.get(vkey)
                    if value_eff is not None:
                        collected_data[field_id] = value_eff

                submitted = st.form_submit_button("確定")

            if not submitted:
                # 確定前は出力を返さず、依存ノードの実行を抑止
                return {
                    "approved": False,
                    "response": None,
                    "metadata": {
                        "timestamp": datetime.now().isoformat(),
                        "mode": "collect",
                        "submitted": False,
                    },
                }

            # バリデーション
            validation_errors = self._validate_data(collected_data, requirements)
            if validation_errors:
                for error in validation_errors:
                    st.error(error)

            # スナップショット保存（以降のrerunで常に表示継続）
            state.set("submitted", True)
            state.set("snapshot", dict(collected_data))
            # ログ: 入力の概要（フィールドと型/サイズのみ）
            try:
                inputs_summary = []
                for k, v in collected_data.items():
                    item: Dict[str, Any] = {"id": k}
                    if isinstance(v, (bytes, bytearray)):
                        item.update({"type": "bytes", "len": len(v)})
                    elif isinstance(v, list) and v and isinstance(v[0], (bytes, bytearray)):
                        item.update({"type": "bytes[]", "count": len(v)})
                    else:
                        item.update({"type": type(v).__name__})
                    inputs_summary.append(item)
                export_log({"mode": "collect", "inputs": inputs_summary}, ctx=ctx, tag="ui.collect_submitted")
            except Exception:
                pass

            return {
                "collected_data": collected_data,
                "approved": len(validation_errors) == 0,
                "response": None,
                "metadata": {
                    "timestamp": datetime.now().isoformat(),
                    "mode": "collect",
                    "submitted": True,
                },
            }
    
    def _render_confirm_mode(self, ctx: BlockContext, message: str, context: Dict) -> Dict[str, Any]:
        """確認モード（HITL）"""
        col1, col2 = st.columns(2)
        approval_key = f"approval_{ctx.run_id}"
        with col1:
            if st.button("承認", key=f"approve_{ctx.run_id}"):
                st.session_state[approval_key] = True
        with col2:
            if st.button("却下", key=f"reject_{ctx.run_id}"):
                st.session_state[approval_key] = False
        # 直近の選択状態を参照（未操作時はNoneのまま）
        approved = st.session_state.get(approval_key, None)
        
        # コメント入力
        comment = st.text_area("コメント（任意）", key=f"comment_{ctx.run_id}")
        # ログ: 承認結果（コメントの長さのみ）
        try:
            export_log({"mode": "confirm", "approved": approved, "comment_len": len(comment or "")}, ctx=ctx, tag="ui.confirm")
        except Exception:
            pass
        
        return {
            "collected_data": {"comment": comment} if comment else {},
            "approved": approved,
            "response": comment,
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "mode": "confirm"
            }
        }
    
    def _render_inquire_mode(
        self,
        ctx: BlockContext,
        requirements: List[Dict],
        message: str,
        context: Dict,
        base_key: str,
    ) -> Dict[str, Any]:
        """問い合わせモード（チャット形式 + LLM主導の情報収集）

        - requirements をもとに LLM が質問を生成
        - ユーザー回答から値を抽出し、required を満たすまで繰り返し
        - file/files/folder 型はアップローダを併用
        """

        # セッション内のチャット履歴
        chat_key = f"chat_history_{ctx.run_id}"
        if chat_key not in st.session_state:
            st.session_state[chat_key] = []
        
        # ノード単位の状態管理（収集データや進行状況の保持）
        node_id = ctx.vars.get("__node_id", base_key)
        with NodeStateContext(ctx.vars.get("__plan_id", "default"), ctx.run_id, node_id, self.version) as state:
            collected_data: Dict[str, Any] = state.get("collected_data", {})
            submitted: bool = bool(state.get("submitted", False))

            # 要件なしの場合は従来チャット挙動
            if not requirements:
                for msg in st.session_state[chat_key]:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                user_input = st.chat_input("メッセージを入力...")
                if user_input:
                    st.session_state[chat_key].append({"role": "user", "content": user_input})
                    st.session_state[chat_key].append({"role": "assistant", "content": f"了解しました: {user_input}"})
                    try:
                        export_log({"mode": "inquire", "event": "chat_freeform", "message": user_input[:200]}, ctx=ctx, tag="ui.inquire")
                    except Exception:
                        pass
                return {
                    "collected_data": {"chat_history": st.session_state.get(chat_key, [])},
                    "approved": True,
                    "response": st.session_state.get(chat_key, [])[-1]["content"] if st.session_state.get(chat_key) else None,
                    "metadata": {"timestamp": datetime.now().isoformat(), "mode": "inquire", "done": False},
                }

            # 既に完了している場合は結果を表示
            if submitted:
                for msg in st.session_state[chat_key]:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                with st.expander("収集済みデータ", expanded=True):
                    st.json(collected_data)
                return {
                    "collected_data": collected_data,
                    "approved": True,
                    "response": "収集完了",
                    "metadata": {"timestamp": datetime.now().isoformat(), "mode": "inquire", "done": True},
                }

            # ユーティリティ関数
            def _get_missing_fields() -> List[str]:
                """未充足の必須フィールドを取得"""
                missing = []
                for req in requirements:
                    field_id = req.get("id")
                    if not field_id or not req.get("required", True):
                        continue
                    
                    value = collected_data.get(field_id)
                    if value is None or value == "":
                        missing.append(field_id)
                        continue
                        
                    # select型の場合はoptionsに含まれるかチェック
                    if req.get("type") == "select":
                        options = req.get("options", [])
                        if value not in options:
                            missing.append(field_id)
                
                return missing

            def _normalize_select_value(field_id: str, raw: Any, options: List[str]) -> Any:
                """select型の値を正規化"""
                if raw in options:
                    return raw
                
                text = str(raw).strip()
                # 年度は4桁抽出
                if field_id in {"fiscal_year", "year", "年度", "会計年度"}:
                    import re
                    m = re.search(r"(\d{4})", text)
                    if m and m.group(1) in options:
                        return m.group(1)
                
                # 四半期の正規化
                if field_id in {"quarter", "四半期"}:
                    import re
                    text_upper = text.upper().replace("Ｑ", "Q")
                    # Q1-Q4パターン
                    m = re.search(r"Q\s*([1-4])", text_upper)
                    if m:
                        q = f"Q{m.group(1)}"
                        if q in options:
                            return q
                
                # 部分一致
                for opt in options:
                    if str(opt).lower() in text.lower():
                        return opt
                
                return raw

            # LLM未設定チェック
            have_llm = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")) and build_chat_llm is not None
            if not have_llm:
                st.error("LLMのAPIキーが未設定のため、このUIは実行できません。")
                raise RuntimeError("LLM key is required for inquire mode")

            # チャット履歴表示
            for msg in st.session_state[chat_key]:
                with st.chat_message(msg["role"]):
                    st.write(msg["content"])

            # ユーザー入力
            user_input = st.chat_input("メッセージを入力...")
            
            # 初回質問生成 or ユーザー入力処理
            need_llm_call = False
            if len(st.session_state[chat_key]) == 0:
                # 初回質問
                need_llm_call = True
                user_message = None
            elif user_input:
                # ユーザーからの新しい入力
                st.session_state[chat_key].append({"role": "user", "content": user_input})
                try:
                    export_log({"mode": "inquire", "event": "chat_user", "message": user_input[:200]}, ctx=ctx, tag="ui.inquire")
                except Exception:
                    pass
                need_llm_call = True
                user_message = user_input
            else:
                # 入力待ち状態
                try:
                    export_log({"mode": "inquire", "event": "chat_update", "message": (user_input or "")[:200]}, ctx=ctx, tag="ui.inquire")
                except Exception:
                    pass
                return {
                    "approved": False,
                    "response": None,
                    "metadata": {"timestamp": datetime.now().isoformat(), "mode": "inquire", "done": False},
                }

            if need_llm_call:
                # LLM呼び出し
                missing_fields = _get_missing_fields()
                
                # Structured Output定義
                class UpdatedValue(BaseModel):
                    field_id: str = Field(description="更新するフィールドID")
                    value: str = Field(description="抽出された値")

                class LLMResponse(BaseModel):
                    extracted_values: List[UpdatedValue] = Field(default_factory=list, description="ユーザーの回答から抽出した値")
                    next_question: Optional[str] = Field(default=None, description="次にユーザーに質問する内容（完了時はnull）")
                    is_complete: bool = Field(default=False, description="すべての必須情報が収集できたか")

                model_name = os.getenv("KEIRI_AGENT_LLM_MODEL", "gpt-4.1")
                temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0.2"))
                llm, _model_label = build_chat_llm(temperature=temperature)
                structured_llm = llm.with_structured_output(LLMResponse)

                # システムプロンプト
                sys_prompt = """あなたは情報収集アシスタントです。以下のrequirementsに基づいて、ユーザーから必要な情報を収集してください。

ルール:
1. ユーザーの回答から値を抽出し、extracted_valuesに設定
2. select型の場合は、optionsに含まれる値のみを返す
3. まだ不足している情報がある場合は、自然な質問をnext_questionに設定
4. すべての必須情報が揃ったらis_completeをtrueに設定し、next_questionはnullにする
5. 1回に1つの質問のみ行う
6. 文脈を踏まえた自然な会話を心がける
7. 各フィールドにhintが設定されている場合は、質問時にヒントを参考にして分かりやすい説明を含める

Requirements:
{requirements}

現在収集済みのデータ:
{collected_data}

不足している必須フィールド:
{missing_fields}

チャット履歴:
{chat_history}

注意: 各requirementのhintフィールドには、ユーザーが回答しやすくするための追加情報が含まれています。質問時にこの情報を活用してください。"""

                # LLM呼び出し
                with st.spinner("回答を確認中..."):
                    try:
                        payload = {
                            "requirements": requirements,
                            "collected_data": collected_data,
                            "missing_fields": missing_fields,
                            "chat_history": st.session_state[chat_key],
                            "user_message": user_message
                        }
                        
                        response = structured_llm.invoke([
                            SystemMessage(content=sys_prompt.format(**payload)),
                            HumanMessage(content=f"ユーザーメッセージ: {user_message or '初回質問をお願いします'}")
                        ])
                        # LLMが生成した次の質問/状態をデバッグ出力
                        try:
                            export_log({
                                "mode": "inquire",
                                "event": "chat_llm",
                                "next_question": (response.next_question or "")[:200],
                                "is_complete": bool(response.is_complete),
                                "extracted_count": len(response.extracted_values or []),
                            }, ctx=ctx, tag="ui.inquire")
                        except Exception:
                            pass
                        
                        # 抽出された値を更新
                        for update in response.extracted_values:
                            field_id = update.field_id
                            value = update.value
                            
                            # requirement情報を取得
                            req = next((r for r in requirements if r.get("id") == field_id), None)
                            if req:
                                if req.get("type") == "select":
                                    options = req.get("options", [])
                                    value = _normalize_select_value(field_id, value, options)
                                    if value in options:
                                        collected_data[field_id] = value
                                else:
                                    collected_data[field_id] = value
                        
                        # データを保存
                        state.set("collected_data", dict(collected_data))
                        try:
                            export_log({
                                "mode": "inquire",
                                "event": "extracted",
                                "updated_fields": [u.field_id for u in response.extracted_values],
                                "missing_after": _get_missing_fields(),
                            }, ctx=ctx, tag="ui.inquire")
                        except Exception:
                            pass
                        
                        # 完了チェック
                        if response.is_complete or not _get_missing_fields():
                            completion_msg = "必要な情報の収集が完了しました。ありがとうございました。"
                            st.session_state[chat_key].append({"role": "assistant", "content": completion_msg})
                            try:
                                export_log({"mode": "inquire", "event": "chat_assistant", "message": completion_msg[:200]}, ctx=ctx, tag="ui.inquire")
                            except Exception:
                                pass
                            state.set("submitted", True)
                            st.rerun()
                        else:
                            # 次の質問を追加
                            if response.next_question:
                                st.session_state[chat_key].append({"role": "assistant", "content": response.next_question})
                                try:
                                    export_log({"mode": "inquire", "event": "chat_assistant", "message": (response.next_question or "")[:200]}, ctx=ctx, tag="ui.inquire")
                                except Exception:
                                    pass
                                st.rerun()
                            else:
                                # 質問がない場合は不足フィールドから自動生成
                                missing = _get_missing_fields()
                                if missing:
                                    auto_question = f"次に{missing[0]}について教えてください。"
                                    st.session_state[chat_key].append({"role": "assistant", "content": auto_question})
                                    try:
                                        export_log({"mode": "inquire", "event": "chat_auto_question", "message": auto_question[:200]}, ctx=ctx, tag="ui.inquire")
                                    except Exception:
                                        pass
                                    st.rerun()
                                
                    except Exception as e:
                        st.error(f"LLM呼び出しに失敗しました: {e}")
                        raise

            # 収集状況のサマリー表示
            if collected_data:
                with st.expander("収集済みデータ", expanded=False):
                    st.json(collected_data)

            return {
                "approved": False,
                "response": None,
                "metadata": {"timestamp": datetime.now().isoformat(), "mode": "inquire", "done": False},
            }
    
    def _render_mixed_mode(self, ctx: BlockContext, requirements: List[Dict], message: str, context: Dict, base_key: str) -> Dict[str, Any]:
        """混合モード（収集＋確認）"""
        # データ収集部分
        collect_result = self._render_collect_mode(ctx, requirements, f"{base_key}_mixed")
        
        # 確認部分
        st.markdown("---")
        st.subheader("確認")
        
        # 収集したデータの表示
        if collect_result["collected_data"]:
            with st.expander("収集されたデータ", expanded=True):
                st.json(collect_result["collected_data"])
        
        # 承認ボタン
        col1, col2 = st.columns(2)
        with col1:
            approved = st.button("承認して次へ", key=f"approve_mixed_{ctx.run_id}")
        with col2:
            rejected = st.button("キャンセル", key=f"reject_mixed_{ctx.run_id}")
        
        if rejected:
            approved = False
        
        collect_result["approved"] = approved
        return collect_result
    
    # 各種入力フィールドのレンダリング関数
    def _render_file_input(self, base_key: str, field_id: str, label: str, description: str, accept: Optional[str], required: bool) -> Optional[Any]:
        if description:
            st.markdown(f"> {description}")
        
        uploaded_file = st.file_uploader(
            label,
            key=f"file_{base_key}_{field_id}",
            accept_multiple_files=False,
            type=accept.split(",") if accept else None
        )
        
        # if required and not uploaded_file:
        #     st.error(f"{label}は必須項目です")
        
        return uploaded_file.read() if uploaded_file else None
    
    def _render_files_input(self, base_key: str, field_id: str, label: str, description: str, accept: Optional[str], required: bool) -> Optional[List[Any]]:
        if description:
            st.caption(description)
        
        uploaded_files = st.file_uploader(
            label,
            key=f"files_{base_key}_{field_id}",
            accept_multiple_files=True,
            type=accept.split(",") if accept else None
        )
        
        # if required and not uploaded_files:
        #     st.error(f"{label}は必須項目です")
        
        return [f.read() for f in uploaded_files] if uploaded_files else None
    
    def _render_folder_input(self, base_key: str, field_id: str, label: str, description: str, accept: Optional[str], required: bool) -> Optional[Any]:
        # フォルダ（ZIP）アップロード
        if description:
            st.caption(description)
        
        uploaded_file = st.file_uploader(
            f"{label} (ZIPファイル)",
            key=f"folder_{base_key}_{field_id}",
            accept_multiple_files=False,
            type=["zip"]
        )
        
        # if required and not uploaded_file:
        #     st.error(f"{label}は必須項目です")
        
        return uploaded_file.read() if uploaded_file else None
    
    def _render_text_input(self, base_key: str, field_id: str, label: str, description: str, required: bool) -> Optional[str]:
        value = st.text_input(label, key=f"text_{base_key}_{field_id}", help=description)
        
        # if required and not value:
        #     st.error(f"{label}は必須項目です")
        
        return value if value else None
    
    def _render_select_input(self, base_key: str, field_id: str, label: str, description: str, options: List[str], required: bool) -> Optional[str]:
        if not options:
            st.error(f"{label}の選択肢が定義されていません")
            return None
        
        # selectbox は内部で rerun されるため、セッションステートに保持して画面のクリアを防ぐ
        sel_key = f"select_{base_key}_{field_id}"
        if sel_key not in st.session_state:
            st.session_state[sel_key] = options[0] if options else None
        value = st.selectbox(label, options=options, key=sel_key, help=description)
        return value
    
    def _render_boolean_input(self, base_key: str, field_id: str, label: str, description: str) -> bool:
        return st.checkbox(label, key=f"bool_{base_key}_{field_id}", help=description)
    
    def _render_number_input(self, base_key: str, field_id: str, label: str, description: str, required: bool) -> Optional[float]:
        value = st.number_input(label, key=f"number_{base_key}_{field_id}", help=description)
        
        # if required and value is None:
        #     st.error(f"{label}は必須項目です")
        
        return value
    
    def _render_chat_input(self, base_key: str, field_id: str, label: str, description: str) -> Optional[str]:
        # シンプルなテキストエリアとして実装
        return st.text_area(label, key=f"chat_{base_key}_{field_id}", help=description)
    
    def _validate_data(self, data: Dict[str, Any], requirements: List[Dict]) -> List[str]:
        """データのバリデーション"""
        errors = []
        
        for req in requirements:
            field_id = req.get("id")
            required = req.get("required", True)
            validation = req.get("validation", {})
            
            if required and field_id not in data:
                errors.append(f"{req.get('label', field_id)}は必須項目です")
            
            # カスタムバリデーションルールの適用
            if field_id in data and validation:
                value = data[field_id]
                
                # 最小・最大長
                if "min_length" in validation and len(str(value)) < validation["min_length"]:
                    errors.append(f"{req.get('label', field_id)}は{validation['min_length']}文字以上必要です")
                
                if "max_length" in validation and len(str(value)) > validation["max_length"]:
                    errors.append(f"{req.get('label', field_id)}は{validation['max_length']}文字以下にしてください")
                
                # パターンマッチング
                if "pattern" in validation:
                    import re
                    if not re.match(validation["pattern"], str(value)):
                        errors.append(f"{req.get('label', field_id)}の形式が正しくありません")
        
        return errors
    
    def _headless_response(self, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
        """ヘッドレスモード用のレスポンス（設定ベース）"""
        # 実行コンテキストからモック応答を取得
        if execution_context:
            mock_response = execution_context.get_ui_mock_response(self.id, inputs.get("node_id", ""))
            if mock_response:
                # モックに auto_resolve 指示がある場合はファイルを実体化
                try:
                    resp = dict(mock_response)
                    cd = resp.get("collected_data")
                    if isinstance(cd, dict):
                        realized: Dict[str, Any] = {}
                        for fid, val in cd.items():
                            if val == "auto_resolve":
                                try:
                                    data = execution_context.resolve_file_input(fid)
                                    realized[fid] = data if data is not None else None
                                except Exception:
                                    realized[fid] = None
                            else:
                                realized[fid] = val
                        resp["collected_data"] = realized
                    return resp
                except Exception:
                    return mock_response
        
        # フォールバック: 既存のダミーデータ
        mode = inputs.get("mode", "collect")
        
        if mode in ("collect", "inquire"):
            # 実行コンテキストからファイル入力を自動解決
            if execution_context:
                from core.plan.file_handler import FileInputHandler
                file_handler = FileInputHandler(execution_context)
                collected_data = file_handler.auto_resolve_file_inputs(inputs.get("requirements", []))
                
                # 残りのフィールドはデフォルト値で埋める
                for req in inputs.get("requirements", []):
                    field_id = req.get("id")
                    field_type = req.get("type")
                    if not field_id or field_id in collected_data:
                        continue
                    
                    if field_type == "text":
                        collected_data[field_id] = f"auto_{field_id}"
                    elif field_type == "select":
                        opts = req.get("options") or []
                        default_val = req.get("default")
                        if default_val is not None:
                            collected_data[field_id] = default_val
                        else:
                            collected_data[field_id] = (opts[0] if isinstance(opts, list) and opts else None)
                    elif field_type == "boolean":
                        collected_data[field_id] = True
                    elif field_type == "number":
                        collected_data[field_id] = 42
                    else:
                        collected_data[field_id] = f"auto_{field_id}"
            else:
                # フォールバック: 既存のダミーデータ
                collected_data: Dict[str, Any] = {}
                for req in inputs.get("requirements", []):
                    field_id = req.get("id")
                    field_type = req.get("type")
                    if not field_id:
                        continue
                    if field_type == "file":
                        collected_data[field_id] = b"dummy file content"
                    elif field_type == "files":
                        collected_data[field_id] = [b"dummy file content"]
                    elif field_type == "folder":
                        collected_data[field_id] = b"dummy zip content"
                    elif field_type == "text":
                        collected_data[field_id] = f"dummy_{field_id}"
                    elif field_type == "select":
                        opts = req.get("options") or []
                        default_val = req.get("default")
                        if default_val is not None:
                            collected_data[field_id] = default_val
                        else:
                            collected_data[field_id] = (opts[0] if isinstance(opts, list) and opts else None)
                    elif field_type == "boolean":
                        collected_data[field_id] = True
                    elif field_type == "number":
                        collected_data[field_id] = 42
                    else:
                        collected_data[field_id] = f"dummy_{field_id}"
            
            return {
                "collected_data": collected_data,
                "approved": True,
                "response": None,
                "metadata": {"timestamp": datetime.now().isoformat(), "mode": mode}
            }
        
        elif mode == "confirm":
            return {
                "collected_data": {},
                "approved": True,
                "response": "Approved in headless mode",
                "metadata": {"timestamp": datetime.now().isoformat(), "mode": mode}
            }
        
        else:
            return {
                "collected_data": {},
                "approved": True,
                "response": "OK",
                "metadata": {"timestamp": datetime.now().isoformat(), "mode": mode}
            }
