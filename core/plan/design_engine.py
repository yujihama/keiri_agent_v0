from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args, **kwargs):
        return False

# Load environment variables from .env if present
load_dotenv()

from core.blocks.registry import BlockRegistry
from .models import Plan
from .validator import validate_plan


class GeneratedPlan(BaseModel):
    """Container for generated plan and auxiliary metadata."""

    plan: Plan
    reasoning: Optional[str] = None


@dataclass
class DesignEngineOptions:
    """Options to guide LLM generation with optional structural hints."""

    suggest_when: bool = False
    suggest_foreach: bool = False
    foreach_var_name: str = "sample_list"


# Heuristic generation has been removed. LLM-only mode is enforced.


# --- LLM based generation ----------------------------------------------------

class LLMNodeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    block: Optional[str] = None
    type: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict, alias="in")
    outputs: Dict[str, str] = Field(default_factory=dict, alias="out")
    when: Optional[Dict[str, Any]] = None
    foreach: Optional[Dict[str, Any]] = None
    while_: Optional[Dict[str, Any]] = Field(default=None, alias="while")
    body: Optional[Dict[str, Any]] = None
    call: Optional[Dict[str, Any]] = None


class LLMDesignModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    version: str = "0.1.0"
    vars: Dict[str, Any] = Field(default_factory=dict)
    policy: Optional[Dict[str, Any]] = None
    ui: Optional[Dict[str, Any]] = None
    graph: List[LLMNodeModel] = Field(default_factory=list)


def _have_llm_key() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))


def _extract_json(text: str) -> str:
    # Prefer fenced code blocks
    import re as _re

    m = _re.search(r"```(?:json)?\n([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    # Fallback to first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _normalize_documents_text(docs: Optional[List[str]]) -> List[str]:
    """Lightweight normalization and summarization for input documents.

    - Collapse whitespace
    - Trim each doc to ~1000 chars
    - Keep up to 5 docs
    """
    if not docs:
        return []
    out: List[str] = []
    for d in docs[:5]:
        try:
            s = str(d)
            # collapse whitespace
            s = " ".join(s.split())
            # keep first 1000 chars
            if len(s) > 1000:
                s = s[:1000]
            out.append(s)
        except Exception:
            continue
    return out


def _build_fallback_plan(
    instruction: str,
    registry: BlockRegistry,
    options: Optional[DesignEngineOptions] = None,
) -> GeneratedPlan:
    """LLMが使えない/不正出力時の安全なデフォルトPlanを生成する。

    - 既存の `designs/invoice_reconciliation.yaml` に準拠したシーケンシャル構成
    - suggest_foreach が有効な場合、簡易 foreach ノードを追加
    """
    opts = options or DesignEngineOptions()

    vars_obj: Dict[str, Any] = {
        "instruction": instruction or "請求書・入金明細を照合し差異を出力",
        "output_config": {"sheet": "Results", "start_row": 2, "columns": ["A", "B", "C"]},
    }

    graph: List[Dict[str, Any]] = [
        {"id": "upload_evidence", "block": "ui.file_uploader.evidence_zip", "out": {"evidence_zip": "evidence_zip"}},
        {
            "id": "parse_zip",
            "block": "file.parse_zip_2tier",
            "in": {"zip_bytes": "${upload_evidence.evidence_zip}"},
            "out": {"evidence": "evidence"},
        },
        {"id": "upload_excel", "block": "ui.file_uploader.excel", "out": {"workbook": "workbook"}},
        {
            "id": "ai_match",
            "block": "ai.invoice_payment_match",
            "in": {"evidence_data": "${parse_zip.evidence}", "instruction": "${vars.instruction}"},
            "out": {"results": "match_results", "summary": "match_summary"},
        },
        {
            "id": "excel_write",
            "block": "excel.write_results",
            "in": {
                "workbook": "${upload_excel.workbook}",
                "data": "${ai_match.match_results}",
                "output_config": "${vars.output_config}",
            },
            "out": {
                "write_summary": "write_summary",
                "workbook_updated": "updated_workbook",
                "workbook_b64": "updated_workbook_b64",
            },
        },
    ]

    if opts.suggest_foreach:
        # foreach の入力となる配列を vars に用意
        vars_obj[opts.foreach_var_name] = [
            {"name": "sample1", "text_excerpt": "100, 200"},
            {"name": "sample2", "text_excerpt": "300"},
        ]
        foreach_node = {
            "id": "foreach_data",
            "type": "loop",
            "foreach": {"input": f"${{vars.{opts.foreach_var_name}}}", "itemVar": "item", "max_concurrency": 2},
            "body": {
                "plan": {
                    "id": "per_item",
                    "version": "0.0.1",
                    "graph": [
                        {
                            "id": "per_item_match",
                            "block": "ai.invoice_payment_match",
                            "in": {"evidence_data": "${vars.item}", "instruction": "${vars.instruction}"},
                            "out": {"results": "item_result", "summary": "item_summary"},
                        }
                    ],
                }
            },
            "out": {"collect": "item_result_list"},
        }
        graph.insert(3, foreach_node)  # ai_match の前に配置

    plan_dict = {
        "apiVersion": "v1",
        "id": "generated_plan",
        "version": "0.1.0",
        "vars": vars_obj,
        "policy": {"on_error": "continue", "retries": 0},
        "ui": {"layout": ["upload_evidence", "upload_excel"]},
        "graph": graph,
    }
    plan = Plan.model_validate(plan_dict)
    return GeneratedPlan(plan=plan, reasoning="fallback")


def _generate_plan_llm(
    instruction: str,
    documents_text: Optional[List[str]],
    registry: BlockRegistry,
    options: Optional[DesignEngineOptions] = None,
) -> GeneratedPlan:
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
    except Exception as e:  # pragma: no cover
        raise RuntimeError("LangChain/OpenAI libraries not available") from e

    opts = options or DesignEngineOptions()

    # Build compact catalog of blocks for the model to choose from
    catalog: List[Dict[str, Any]] = []
    for bid, specs in registry.specs_by_id.items():
        # Use the last spec (roughly latest)
        spec = specs[-1]
        catalog.append(
            {
                "id": spec.id,
                "inputs": sorted((spec.inputs or {}).keys()),
                "outputs": sorted((spec.outputs or {}).keys()),
                "description": spec.description or "",
            }
        )

    # Normalize/limit documents (lightweight summarization)
    norm_docs = _normalize_documents_text(documents_text)
    docs_joined = "\n\n".join(norm_docs)
    if len(docs_joined) > 4000:
        docs_joined = docs_joined[:4000]

    system_prompt = (
        "あなたは業務設計エンジンです。利用可能なブロック一覧を基に、Plan(JSON)を生成してください。"
        "出力は厳密にJSONのみ、余計な説明やマークダウンは不要です。"
        "各ノードは存在するblock idのみを使用し、in/outキー名はブロックスペックのキーと一致させてください。"
        "UIブロックを最低1つ含め、DAGで循環が無いようにしてください。"
    )

    hints: List[str] = []
    if opts.suggest_when:
        hints.append("処理開始前に 'ui.confirmation' を挿入し、whenでフローをガードする")
    if opts.suggest_foreach:
        hints.append(f"'foreach' で vars.{opts.foreach_var_name} を反復処理するループノードを追加する")
    hints_str = "\n- ".join(hints)

    human_prompt = f"""
指示:
{instruction}

参考文書(要約):
{docs_joined}

利用可能なブロック一覧（id, inputs, outputs, description）:
{json.dumps(catalog, ensure_ascii=False)}

ヒント:
- {hints_str}

要求仕様:
- JSONスキーマに従うこと: {{
  "id": str,
  "version": str,
  "vars": object,
  "ui": {{"layout": [str]}} | null,
  "policy": object | null,
  "graph": [{{
    "id": str,
    "block": str | null,
    "type": str | null,
    "in": object,
    "out": object,
    "when": object | null,
    "foreach": object | null,
    "while": object | null,
    "body": object | null,
    "call": object | null
  }}]
}}

制約:
- outのキーはブロックのoutputsに存在するキーを使う
- inのキーはブロックのinputsに存在するキーを使う
- 参照は ${{node_id.alias}} または ${{vars.key}} 形式
    """

    model_name = os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1"
    temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0"))
    llm = ChatOpenAI(model=model_name, temperature=temperature)
    # Prefer structured output to enforce strict JSON
    design: LLMDesignModel | None = None
    try:
        llm_structured = llm.with_structured_output(LLMDesignModel, method="function_calling")
        design = llm_structured.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
    except Exception:
        # Fallback to free-form JSON extraction
        res = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
        text = res.content if isinstance(res.content, str) else str(res.content)
        json_text = _extract_json(text)
        data = json.loads(json_text)
        design = LLMDesignModel.model_validate(data)
    ui_layout = []
    if design.ui and isinstance(design.ui, dict):
        ui_layout = list(design.ui.get("layout") or [])

    plan_dict = {
        "apiVersion": "v1",
        "id": design.id or "generated_plan",
        "version": design.version or "0.1.0",
        "vars": design.vars or {"instruction": instruction},
        "policy": design.policy or {"on_error": "continue", "retries": 0},
        "ui": {"layout": ui_layout},
        "graph": [
            {
                "id": n.id,
                **({"block": n.block} if n.block else {}),
                **({"type": n.type} if n.type else {}),
                "in": n.inputs or {},
                "out": n.outputs or {},
                **({"when": n.when} if n.when else {}),
                **({"foreach": n.foreach} if n.foreach else {}),
                **({"while": n.while_} if n.while_ else {}),
                **({"body": n.body} if n.body else {}),
                **({"call": n.call} if n.call else {}),
            }
            for n in design.graph
        ],
    }

    plan = Plan.model_validate(plan_dict)
    # LLM出力の静的検証に失敗したらフォールバック
    if validate_plan(plan, registry):
        return _build_fallback_plan(instruction, registry, options)
    reasoning = "LLM生成 (LangChain + OpenAI)"
    return GeneratedPlan(plan=plan, reasoning=reasoning)


def generate_plan(
    instruction: str,
    documents_text: Optional[List[str]],
    registry: BlockRegistry,
    options: Optional[DesignEngineOptions] = None,
) -> GeneratedPlan:
    """Generate plan using LLM only. API key is required.

    Raises:
        RuntimeError: when no OPENAI/AZURE API key is set.
    """

    if not _have_llm_key():
        # キーが無い環境では決定的なフォールバックPlanを返す
        return _build_fallback_plan(instruction, registry, options)

    gen = _generate_plan_llm(instruction, documents_text, registry, options)
    # 念のためここでも検証し、失敗ならフォールバック
    if validate_plan(gen.plan, registry):
        return _build_fallback_plan(instruction, registry, options)

    # 強制ヒント: foreach 指定があるのに生成に含まれない場合、フォールバックの foreach を差し込む
    opts = options or DesignEngineOptions()
    try:
        if opts.suggest_foreach and not any((n.type == "loop" and n.foreach) for n in gen.plan.graph):
            plan_dict: Dict[str, Any] = gen.plan.model_dump(by_alias=True)
            loop_node = {
                "id": "foreach_data",
                "type": "loop",
                "foreach": {"input": f"${{vars.{opts.foreach_var_name}}}", "itemVar": "item", "max_concurrency": 2},
                "body": {
                    "plan": {
                        "id": "per_item",
                        "version": "0.0.1",
                        "graph": [
                            {
                                "id": "per_item_match",
                                "block": "ai.invoice_payment_match",
                                "in": {"evidence_data": "${vars.item}", "instruction": "${vars.instruction}"},
                                "out": {"results": "item_result", "summary": "item_summary"},
                            }
                        ],
                    }
                },
                "out": {"collect": "item_result_list"},
            }
            # 既存グラフの先頭に挿入
            plan_dict.setdefault("graph", [])
            plan_dict["graph"].insert(0, loop_node)
            from .models import Plan as _Plan

            patched = _Plan.model_validate(plan_dict)
            # 最終チェックに通らなければフォールバック
            if validate_plan(patched, registry):
                return _build_fallback_plan(instruction, registry, options)
            return GeneratedPlan(plan=patched, reasoning=(gen.reasoning or "") + "+foreach_hinted")
    except Exception:
        # 差し込みに失敗しても安全にフォールバック
        return _build_fallback_plan(instruction, registry, options)

    return gen


