from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Type
import os
import json

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockError, BlockException, ErrorCode, create_input_error, create_external_error, wrap_exception
from pydantic import BaseModel, Field, create_model, ConfigDict
from core.plan.logger import export_log
from core.plan.llm_factory import build_chat_llm


def _default_output_schema() -> Dict[str, Any]:
    """デフォルトの出力スキーマ（従来互換）。

    JSON-Schema風の簡易表現:
      - type: object|array|string|integer|number|boolean|any
      - properties: { name: <schema> }
      - items: <schema>
    """

    # 廃止: デフォルト/後方互換は提供しない（プラン指定のみ）
    return {}


_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "str": str,
    "integer": int,
    "int": int,
    "number": float,
    "float": float,
    "boolean": bool,
    "bool": bool,
    "any": Any,
}


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra='forbid')


def _type_from_spec(name: str, spec: Any) -> Any:
    """JSON-Schema風の簡易specからPython型/Pydanticモデルを生成する。

    - object + properties -> 動的Pydanticモデル
    - array + items -> List[item_type]
    - プリミティブ文字列 -> 対応型
    - 未知/未指定 -> Any
    返却値は型（class）そのもの。
    """

    if isinstance(spec, str):
        return _TYPE_MAP.get(spec.lower(), Any)
    if not isinstance(spec, dict):
        return Any

    t = (spec.get("type") or "object").lower()
    if t == "array":
        from typing import List as _List  # pydantic互換のためtyping.Listを使用

        item_spec = spec.get("items")
        item_type = _type_from_spec(f"{name}Item", item_spec) if item_spec is not None else Any
        return _List[item_type]  # type: ignore[index]

    if t == "object":
        props: Dict[str, Any] = spec.get("properties") or {}
        fields: Dict[str, Tuple[Any, Any]] = {}
        for k, v in props.items():
            ty = _type_from_spec(f"{name}_{k}", v)
            # 厳密: すべて必須（Planスキーマ準拠）
            fields[k] = (ty, ...)
        # 空でも additionalProperties: false を満たすため StrictBase を用いる
        return create_model(name, __base__=_StrictBase, **fields)  # type: ignore[call-arg]

    # プリミティブ
    return _TYPE_MAP.get(t, Any)


def _build_output_model_from_schema(schema: Dict[str, Any]) -> Type[BaseModel]:
    """トップレベルはPlanで列挙されたキーのみ定義し、各オブジェクトは additionalProperties:false。"""

    if not isinstance(schema, dict) or not schema:
        raise ValueError("output_schema must be a non-empty object")

    fields: Dict[str, Tuple[Any, Any]] = {}
    for top_key, top_spec in schema.items():
        ty = _type_from_spec(f"Top_{top_key}", top_spec)
        # 厳密: すべて必須
        fields[str(top_key)] = (ty, ...)

    return create_model("StructuredOutputDynamic", __base__=_StrictBase, **fields)  # type: ignore[call-arg]

class ProcessLLMBlock(ProcessingBlock):
    id = "ai.process_llm"
    version = "1.0.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """LLMを利用して処理を行う。

        - 入力ファイルを対象に、必要最小限のメタデータ + 抜粋を整形
        - システム/ユーザープロンプトはPlanから指定可能
        - 出力スキーマはPlanからJSON-Schema風に与え、動的Pydanticで構造化出力
        """


        evidence = inputs.get("evidence_data") or {}
        # プロンプト/インストラクションの扱い: prompt 未指定時は instruction を利用（Spec 準拠）
        instruction_text: str = str(inputs.get("instruction") or "")
        prompt_text: str = str(inputs.get("prompt") or instruction_text)
        system_prompt_override: Optional[str] = inputs.get("system_prompt")
        # 出力スキーマ: Plan指定のみを受け付ける（必須）
        output_schema: Dict[str, Any] = inputs.get("output_schema") or {}
        if not isinstance(output_schema, dict) or not output_schema:
            raise create_input_error(
                field="output_schema",
                expected_type="non-empty object",
                actual_value=output_schema,
                code=ErrorCode.INPUT_REQUIRED_MISSING
            )

        files: List[Dict[str, Any]] = evidence.get("files", []) if isinstance(evidence, dict) else []
        # すべてのファイルを使用（ただし1ファイルあたりの抜粋は制限）
        try:
            per_file_chars = int(inputs.get("per_file_chars") or int(os.getenv("KEIRI_AGENT_PER_FILE_CHARS", "1500")))
        except Exception:
            per_file_chars = 1500

        # 表データ（rows など）も扱うための制限値
        try:
            per_table_rows = int(inputs.get("per_table_rows") or int(os.getenv("KEIRI_AGENT_PER_TABLE_ROWS", "200")))
        except Exception:
            per_table_rows = 200

        # 動的出力モデル（スキーマ準拠）を生成
        DynamicOutModel = _build_output_model_from_schema(output_schema)

        # Fast-path: evidence_data.answer が厳密なJSONでスキーマに適合する場合はLLMを使わず構造化
        answer_text: Optional[str] = None
        if isinstance(evidence, dict) and isinstance(evidence.get("answer"), str):
            answer_text = evidence.get("answer")  # type: ignore[assignment]
        if answer_text:
            try:
                parsed = json.loads(answer_text)
                if isinstance(parsed, dict) and "results" in parsed:
                    results_val = parsed.get("results") or []
                    summary_val = parsed.get("summary") or {}
                elif isinstance(parsed, list):
                    results_val = parsed
                    summary_val = {}
                elif isinstance(parsed, dict):
                    # Single object → wrap as one result
                    results_val = [parsed]
                    summary_val = {}
                else:
                    results_val = []
                    summary_val = {}

                summary = {
                    "files": 0,
                    "tables": 0,
                    "model": "fastpath-json",
                    "temperature": 0,
                    "group_key": inputs.get("group_key"),
                }
                try:
                    keys = list(results_val[0].keys()) if (isinstance(results_val, list) and results_val and isinstance(results_val[0], dict)) else []
                    export_log({"mode": "fastpath", "results_item_keys": keys, "files": 0, "tables": 0}, ctx=ctx, tag="ai.process_llm")
                except Exception:
                    pass
                return {"results": results_val, "summary": summary_val or summary}
            except Exception:
                # fallthrough to LLM path
                pass

        # LLM 実行のみを許容（キー未設定時はエラー）
        have_llm = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
        if not have_llm:
            raise BlockException(BlockError(
                code=ErrorCode.CONFIG_MISSING,
                message="OPENAI/AZURE_OPENAI APIキーが未設定のため、LLM処理を実行できません",
                details={"required_env": ["OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"]},
                hint="環境変数にOPENAI_API_KEYまたはAZURE_OPENAI_API_KEYを設定してください",
                recoverable=False
            ))

        try:
            # 全ファイルを対象に、必要最小限のメタデータ + 抜粋を整形
            docs: List[Dict[str, Any]] = []
            for f in files:
                docs.append(
                    {
                        "name": f.get("name"),
                        "ext": f.get("ext"),
                        "size": f.get("size"),
                        "text_excerpt": (f.get("text_excerpt") or "")[:per_file_chars],
                    }
                )

            # evidence_data 内の表形式データ（rows など）を抽出
            def _as_rows(name: str, value: Any) -> Optional[Dict[str, Any]]:
                """value からテーブル相当を抽出し、行の先頭 N 件とカラム一覧を返す。

                受理パターン:
                  - list[dict]
                  - {"rows": list[dict]}
                  - {"results": list[dict]}  # ai.process_llm の下流出力をそのまま渡した場合
                """

                # list[dict] 形式
                if isinstance(value, list):
                    if value and isinstance(value[0], dict):
                        rows = value
                    else:
                        return None
                elif isinstance(value, dict):
                    if isinstance(value.get("rows"), list) and (not value.get("rows") or isinstance(value["rows"][0], dict)):
                        rows = value.get("rows") or []
                    elif isinstance(value.get("results"), list) and (not value.get("results") or isinstance(value["results"][0], dict)):
                        rows = value.get("results") or []
                    else:
                        return None
                else:
                    return None

                # 列名は行のキーの和集合から推定（最大 200 列に制限）
                columns: List[str] = []
                try:
                    seen = set()
                    for r in rows[: per_table_rows]:
                        if isinstance(r, dict):
                            for k in r.keys():
                                if k not in seen:
                                    seen.add(k)
                                    columns.append(str(k))
                        if len(columns) >= 200:
                            break
                except Exception:
                    pass

                return {
                    "name": name,
                    "total_rows": len(rows),
                    "columns": columns,
                    "rows_excerpt": rows[: per_table_rows],
                }

            tables: List[Dict[str, Any]] = []
            tables_map: Dict[str, Any] = {}
            rows_preview: Optional[List[Dict[str, Any]]] = None
            if isinstance(evidence, dict):
                for k, v in evidence.items():
                    if k == "files":
                        continue
                    tbl = _as_rows(str(k), v)
                    if tbl is not None:
                        tables.append(tbl)
                        tables_map[str(k)] = tbl.get("rows_excerpt", [])
                        if k == "rows":
                            rows_preview = tbl.get("rows_excerpt", [])  # type: ignore[assignment]

            from langchain_core.messages import SystemMessage, HumanMessage

            default_sys_prompt = (
                "あなたは業務文書の情報抽出・照合を行うアシスタントです。"
                "入力の全ファイルのテキスト抜粋を用いて、指定の出力スキーマに厳密準拠したJSONを返してください。"
                "余計な説明やマークダウンは不要です。"
            )
            sys_prompt = system_prompt_override or default_sys_prompt
            human_content = {
                "group_key": inputs.get("group_key"),
                "instruction": instruction_text,
                "prompt": prompt_text,
                "documents": docs,
                "tables": tables,
                "datasets": tables_map,
                "rows": rows_preview,
                "raw_answer": answer_text,
            }
            temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0"))
            llm, model_label = build_chat_llm(temperature=temperature)
            # すでに生成済みの動的出力モデルを使用
            structured_llm = llm.with_structured_output(DynamicOutModel)
            # スキーマもヒントとして渡す（モデル側の自己整合性を高める）
            schema_hint = json.dumps(output_schema, ensure_ascii=False)
            data_obj = structured_llm.invoke(
                [
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content=f"""入力:\n{human_content}\n\n出力スキーマ:\n{schema_hint}"""),
                ]
            )
            # スキーマに完全準拠した構造化結果を results に格納して返す（BlockSpecのoutputsに準拠）
            structured = data_obj.model_dump()
            summary = {
                "files": len(docs),
                "tables": len(tables),
                "model": model_label,
                "temperature": temperature,
                "group_key": inputs.get("group_key"),
            }
            try:
                # 結果の概要（キー/件数のみ）
                keys = list(structured.keys()) if isinstance(structured, dict) else []
                export_log({"mode": "llm", "keys": keys, "files": len(docs), "tables": len(tables)}, ctx=ctx, tag="ai.process_llm")
            except Exception:
                pass
            return {"results": structured, "summary": summary}
        except Exception as e:
            # 失敗時のフォールバックは提供しない（エラーを上位に送出）
            raise wrap_exception(e, ErrorCode.EXTERNAL_API_ERROR, inputs)


