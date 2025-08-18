from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Dict, List, Optional, Tuple, Annotated
import numpy as _np
import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, model_validator
from langchain_core.messages import SystemMessage, HumanMessage

from dotenv import load_dotenv
load_dotenv()

from core.blocks.registry import BlockRegistry, BlockSpec
from core.plan.llm_factory import build_chat_llm
from .templates import load_all_templates, summarize_templates, TemplateSpec
from .models import Plan
from .validator import validate_plan

# Pydantic constrained string (non-empty)
NonEmptyStr = Annotated[str, Field(min_length=1)]



class GeneratedPlan(BaseModel):
    """Container for generated plan and auxiliary metadata."""

    plan: Plan
    reasoning: Optional[str] = None
    # Optional: logs for UI to display what happened during validation/repair
    initial_errors: Optional[List[str]] = None
    repair_log: Optional[List[Dict[str, Any]]] = None


class BusinessInput(BaseModel):
    id: str
    channel: str  # file|chat|api
    count: str  # one|many
    kinds: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class BusinessProcess(BaseModel):
    id: str
    description: str
    rules: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    when: Optional[Dict[str, Any]] = Field(default=None, description="条件分岐（expr など）")
    foreach: Optional[Dict[str, Any]] = Field(default=None, description="反復処理（item/in など）")
    while_: Optional[Dict[str, Any]] = Field(default=None, alias="while", description="繰り返し条件（expr など）")


class BusinessOutput(BaseModel):
    id: str
    type: str  # ui|excel|json|pdf
    description: str
    sheet: Optional[str] = None


class BusinessOverview(BaseModel):
    title: Optional[str] = None
    inputs: Optional[List[BusinessInput]] = Field(default_factory=list, description="当該業務の詳細なインプット（例：ファイル、データ、指示）。")
    processes: Optional[List[BusinessProcess]] = Field(default_factory=list, description="当該業務の詳細なプロセス（例：データの加工、ファイルの作成、データ更新など）。")
    outputs: Optional[List[BusinessOutput]] = Field(default_factory=list, description="当該業務の詳細なアウトプット(例：ファイル、データ、UIへの表示)。")
    open_points: List[str] = Field(default_factory=list, description="整理のために必要な前提事項")

class SkeletonNode(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: NonEmptyStr = Field(description="ノードID※このノードの処理を表現する名称（空不可）")
    block: Optional[NonEmptyStr] = Field(default=None, description="使用するブロックID※実在するIDのみ選択可能（空不可）")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="このノードの想定される入力データ")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="このノードの想定される出力データ")
    description: Optional[NonEmptyStr] = Field(default=None, description="このノードの詳細な説明")
    when: Optional[Dict[str, Any]] = Field(default=None, description="条件分岐")
    foreach: Optional[Dict[str, Any]] = Field(default=None, description="繰り返し")
    while_: Optional[Dict[str, Any]] = Field(default=None, description="繰り返し条件")

    @model_validator(mode="after")
    def _validate_reason_and_block(self):
        # require description if inputs or outputs are empty
        inputs_empty = not bool(self.inputs)
        outputs_empty = not bool(self.outputs)
        if inputs_empty or outputs_empty:
            if not self.description or not str(self.description).strip():
                raise ValueError("inputs または outputs が空の場合は description に理由を記載してください。")

        # require non-empty block
        if not self.block or not str(self.block).strip():
            raise ValueError("block は必須です（空不可）。")
        return self


class PlanSkeleton(BaseModel):
    ui: Dict[str, List[str]] = Field(default_factory=lambda: {"layout": []}, description="UIレイアウト")
    graph: List[SkeletonNode] = Field(default_factory=list, description="ノードグラフ")
    open_points: List[str] = Field(default_factory=list, description="生成のために必要な確認事項")


class FixPatch(BaseModel):
    target: str  # node.id:path
    op: str      # set|add|remove
    value: Any | None = None


@dataclass
class DesignEngineOptions:
    """Options for staged plan generation."""

    # Retrieval/LLM control
    topk_per_category: int = 6
    max_docs_chars: int = 4000
    # Template application mode: currently only "hint"
    apply_mode: str = "hint"
    selected_templates: Optional[List[str]] = None
    # Self-repair attempts when validation fails
    max_self_repair_attempts: int = 2


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


def _validate_skeleton(skeleton: "PlanSkeleton", registry: BlockRegistry) -> List[str]:
    errors: List[str] = []
    seen: set[str] = set()
    for n in (skeleton.graph or []):
        node_id = (n.id or "").strip()
        if not node_id:
            errors.append("Empty node id in skeleton")
            continue
        if node_id in seen:
            errors.append(f"Duplicate node id in skeleton: {node_id}")
        seen.add(node_id)
        block_id = ((n.block or "").strip()) if isinstance(n.block, str) or n.block is None else str(n.block)
        if not block_id:
            errors.append(f"Missing block in skeleton node {node_id}")
        elif block_id not in registry.specs_by_id:
            errors.append(f"Unknown block in skeleton node {node_id}: {block_id}")
    try:
        layout = list((skeleton.ui or {}).get("layout") or [])
    except Exception:
        layout = []
    for nid in layout:
        if nid not in seen:
            errors.append(f"UI layout references unknown node id in skeleton: {nid}")
    return errors


def _compute_block_catalog(registry: BlockRegistry) -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
    
    def _compact_io_schema(io: Dict[str, Any]) -> Dict[str, Any]:
        """Return a compact schema map keeping only essential fields.

        Keeps: type, enum, description (if present).
        """
        out: Dict[str, Any] = {}
        for k, v in (io or {}).items():
            try:
                v_dict = dict(v or {}) if isinstance(v, dict) else {}
            except Exception:
                v_dict = {}
            compact: Dict[str, Any] = {}
            if "type" in v_dict and v_dict.get("type") is not None:
                compact["type"] = v_dict.get("type")
            if "enum" in v_dict and v_dict.get("enum") is not None:
                compact["enum"] = v_dict.get("enum")
            if "description" in v_dict and v_dict.get("description"):
                compact["description"] = v_dict.get("description")
            out[k] = compact
        return out

    # ui配下（idが"ui."で始まるもの）を先に、その他（processing等）は後でcatalogに追加する
    ui_specs = []
    processing_specs = []
    for bid, specs in registry.specs_by_id.items():
        spec = specs[-1]
        if spec.id.startswith("ui."):
            ui_specs.append(spec)
        else:
            processing_specs.append(spec)
    for spec in ui_specs + processing_specs:
        catalog.append(
            {
                "id": spec.id,
                "inputs": sorted((spec.inputs or {}).keys()),
                "outputs": sorted((spec.outputs or {}).keys()),
                # schema-aware hints
                "inputs_schema": _compact_io_schema(spec.inputs or {}),
                "outputs_schema": _compact_io_schema(spec.outputs or {}),
                "description": spec.description or "",
                "category": getattr(spec, "category", None),
                "tags": getattr(spec, "tags", None),
            }
        )
    return catalog


def _score_blocks_simple(query: str, docs_joined: str, catalog: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Very simple lexical scorer: counts overlaps in id/description/IO keys.
    This is a placeholder until embedding-based retrieval is wired.
    """
    import re

    def tokenize(s: str) -> List[str]:
        s = (s or "").lower()
        return re.findall(r"[a-z0-9_.]+", s)

    q_tokens = set(tokenize(query) + tokenize(docs_joined))
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for b in catalog:
        tokens = set(tokenize(b.get("id", "")) + tokenize(" ".join(b.get("inputs", []))) + tokenize(" ".join(b.get("outputs", []))) + tokenize(b.get("description", "")))
        score = len(q_tokens & tokens) + 0.5 * len(set(tokenize(b.get("description", ""))) & q_tokens)
        scored.append((score, b))
    top = [b for _, b in sorted(scored, key=lambda x: x[0], reverse=True)[: max(1, k)]]
    return top


def _score_blocks_embed(query: str, docs_joined: str, catalog: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    """Embedding-based Top-K using OpenAI/Azure embeddings with cosine similarity.

    Falls back to lexical scoring if embeddings are unavailable.
    """
    try:
        from .llm_factory import build_text_embedder

        embed_fn, label = build_text_embedder()
        query_text = (query or "").strip()
        if docs_joined:
            query_text = f"{query_text}\n\n{docs_joined}"

        # Prepare block texts
        block_texts: List[str] = []
        for b in catalog:
            text = " ".join([
                str(b.get("id") or ""),
                "inputs:" + ",".join(b.get("inputs", []) or []),
                "outputs:" + ",".join(b.get("outputs", []) or []),
                str(b.get("description") or ""),
            ])
            block_texts.append(text)

        all_vecs = embed_fn([query_text] + block_texts)
        if not all_vecs or len(all_vecs) != len(block_texts) + 1:
            # Safety fallback
            return _score_blocks_simple(query, docs_joined, catalog, k)
        qv = _np.array(all_vecs[0], dtype=_np.float32)
        bmat = _np.array(all_vecs[1:], dtype=_np.float32)
        # Cosine similarity
        qn = qv / (float(_np.linalg.norm(qv)) + 1e-8)
        bn = bmat / ( _np.linalg.norm(bmat, axis=1, keepdims=True) + 1e-8 )
        sims = bn.dot(qn)
        order = sims.argsort()[::-1]
        top_idxs = order[: max(1, k)]
        return [catalog[int(i)] for i in top_idxs]
    except Exception:
        return _score_blocks_simple(query, docs_joined, catalog, k)


def _generate_plan_llm(
    instruction: str,
    documents_text: Optional[List[str]],
    registry: BlockRegistry,
    options: Optional[DesignEngineOptions] = None,
    hints_vars: Optional[Dict[str, Any]] = None,
) -> GeneratedPlan:
    from langchain_core.messages import SystemMessage, HumanMessage
    

    opts = options or DesignEngineOptions()

    # Build block catalog and apply Top-K filtering (simple lexical; embedding can replace later)
    full_catalog: List[Dict[str, Any]] = _compute_block_catalog(registry)
    # Normalize/limit documents (lightweight summarization)
    norm_docs = _normalize_documents_text(documents_text)
    docs_joined = "\n\n".join(norm_docs)
    max_chars = max(1000, int((options.max_docs_chars if options else 4000)))  # defensive
    if len(docs_joined) > max_chars:
        docs_joined = docs_joined[:max_chars]

    # Select Top-K blocks
    k = (options.topk_per_category if options else 6)  # category未実装のため単一K
    top_blocks = _score_blocks_embed(instruction, docs_joined, full_catalog, k)

    # Load templates and compute summaries for hinting
    selected_templates: List[TemplateSpec] = []
    try:
        all_templates = load_all_templates()
        if options and options.selected_templates:
            for tid in options.selected_templates:
                t = all_templates.get(tid)
                if t:
                    selected_templates.append(t)
    except Exception:
        selected_templates = []
    template_summaries = summarize_templates(selected_templates) if selected_templates else []

    system_prompt = (
        "あなたは業務設計エンジンです。利用可能なブロック一覧を基に、Plan(JSON)を生成してください。"
        "出力は厳密にJSONのみ、余計な説明やマークダウンは不要です。"
        "各ノードは存在するblock idのみを使用し、'in'/'out' キー名のみを使用（'inputs'/'outputs' は使用禁止）。"
        "'in' のキーと 'out' のキーはブロックスペックの入出力キーと一致させてください。"
        "UIブロックを最低1つ含め、DAGで循環が無いようにしてください。"
        "重要な原則:\n"
        "1. 参照は常に ${nodeId.alias} または ${vars.key} 形式を使用。alias は各ノードの out で割り当てた値。\n"
        "   - 良い例: out: { collected_data: invoice_file } → 参照は ${input_invoice_file.invoice_file}\n"
        "   - 悪い例: ${input_invoice_file.collected_data}（ローカル出力キー名の参照は禁止）\n"
        "2. ${vars.*} 参照は必ず vars セクションに定義された変数のみを使用\n"
        "3. ai.process_llm では 'output_schema'(非空オブジェクト) を必須、さらに 'prompt' または 'instruction' の少なくとも一方を指定\n"
        "4. 型の整合性: 各ブロックの入力型（object/array/string/boolean/integer/number等）と enum を厳守\n"
        "5. ファイル入力が必要な場合は必ず ui.interactive_input を使い、mode は 'collect'。requirements は配列で file フィールドを定義。\n"
        "6. Excel 出力は excel.write を使用。column_updates の中に columns 配列[{header, path}] と values を含めること（values は行配列）。\n"
        "7. サンプルごとの処理には foreach ループを使用\n"
        "8. 設計QAの既知変数（hints_vars）が曖昧さを解消する場合は固定の経路のみを生成。未確定で複数候補がある場合は 'when.expr' を用い、${vars.<key>} を条件に分岐を生成（条件式は簡潔に）。\n"
    )

    hints: List[str] = []
    hints_str = "\n- ".join(hints) if hints else "(なし)"

    human_prompt = f"""
指示:
{instruction}

参考文書(要約):
{docs_joined}

使用可能ブロック（id/入出力/スキーマ/説明）:
{json.dumps(top_blocks, ensure_ascii=False)}

選択テンプレートの要約（任意）:
{json.dumps(template_summaries, ensure_ascii=False)}

既知の変数（利用可能な場合は尊重して設計に反映）:
{json.dumps(hints_vars or {}, ensure_ascii=False)}

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

制約（遵守必須）:
- キー名は 'in'/'out' のみ使用（'inputs'/'outputs' は使用禁止）
- out のキーはブロックの outputs に存在するキー、in のキーはブロックの inputs に存在するキーのみ使用
- 参照は ${{node_id.alias}} または ${{vars.key}} 形式のみ使用（alias は各ノードの out によって定義）。
  - 良い例: out: {{ collected_data: invoice_file }} → ${{input_invoice_file.invoice_file}}
  - 悪い例: ${{input_invoice_file.collected_data}}
- ${{vars.*}} を使う場合、必ず対応する変数を vars セクションに定義
- ai.process_llm の 'evidence_data' は object 型、'output_schema' は非空オブジェクト必須、'prompt' または 'instruction' を少なくとも一方指定
  - output_schema はオブジェクト形式（例: {{{{field1: string, field2: number}}}}）で、空や文字列は不可
- ファイル処理が必要な場合、最初に ui.interactive_input を配置し、mode は 'collect' を使用。
  requirements は配列とし、file 入力を下記のように定義:
  例: in: {{ mode: collect, message: "...", requirements: [{{ id: "invoice_file", type: "file", label: "請求書ファイル", accept: ".xlsx,.xls" }}] }}; out: {{ collected_data: invoice_file }}
- Excel 出力は excel.write を使用し、column_updates の中に columns 配列と values を含める:
  例: in: {{ workbook: ${{input_invoice_file.invoice_file}}, column_updates: {{ sheet: "結果", columns: [{{header: "請求書番号", path: "invoice_no"}}], values: ${{match_records.results}} }} }}
"""

    model_name = os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1"
    temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0"))
    llm, model_label = build_chat_llm(temperature=temperature)
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
                **({"in": n.inputs} if n.inputs else {}),
                **({"out": n.outputs} if n.outputs else {}),
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
    # LLM出力の静的検証
    errors = validate_plan(plan, registry)
    if errors:
        # 自己修復（最大 attempts 回）
        repair_log: List[Dict[str, Any]] = []
        repair_log.append({"phase": "validate", "errors": list(errors)})
        attempts = max(0, int((options.max_self_repair_attempts if options else 0)))
        last_design = design
        for i in range(attempts):
            try:
                # Collect block spec snippets for blocks used in current design
                used_blocks: List[str] = []
                try:
                    used_blocks = [n.block for n in (last_design.graph or []) if n.block]  # type: ignore[attr-defined]
                except Exception:
                    used_blocks = [n.get("block") for n in (plan_dict.get("graph") or []) if isinstance(n, dict) and n.get("block")]
                spec_snippets: List[Dict[str, Any]] = []
                for bid, specs in registry.specs_by_id.items():
                    if bid in set(used_blocks):
                        spec = specs[-1]
                        spec_snippets.append({
                            "id": spec.id,
                            "inputs": list((spec.inputs or {}).keys()),
                            "outputs": list((spec.outputs or {}).keys()),
                            "description": spec.description or "",
                        })

                fix_system = (
                    "あなたは業務設計エンジンです。以下のPlan(JSON)と検証エラーを受け取り、"
                    "ブロックスペック（入力/出力キー）を厳守するようにPlanを修正して返してください。"
                    "出力は厳密にJSONのみ。構造は初回と同じスキーマに従うこと。"
                )
                fix_human = f"""
前回のPlan:
{json.dumps(plan_dict, ensure_ascii=False)}

検証エラー一覧:
{json.dumps(errors, ensure_ascii=False)}

参照用ブロックスペック（入力/出力キーのホワイトリスト）:
{json.dumps(spec_snippets, ensure_ascii=False)}

修正方針:
- エラー原因となっている入力/出力キーを必ずスペックのキーへ合わせて修正
- ui.interactive_input は 'in.requirements' ベースでUI項目を宣言。出力は 'out.collected_data' のエイリアスのみ
- ai.process_llm は 'output_schema'(空不可) を必須とし、'prompt' または 'instruction' のいずれかを指定
- 参照（${{node.alias}}/${{vars.*}}）形式は維持
                """
                llm_structured2 = llm.with_structured_output(LLMDesignModel, method="function_calling")
                design2 = llm_structured2.invoke([SystemMessage(content=fix_system), HumanMessage(content=fix_human)])
                last_design = design2
                # rebuild plan_dict and validate again
                plan_dict2 = {
                    "apiVersion": "v1",
                    "id": design2.id or (design.id if design else "generated_plan"),
                    "version": design2.version or "0.1.0",
                    "vars": design2.vars or (design.vars if design else {"instruction": instruction}),
                    "policy": design2.policy or {"on_error": "continue", "retries": 0},
                    "ui": {"layout": list((design2.ui or {}).get("layout") or [])} if design2.ui else {"layout": []},
                    "graph": [
                        {
                            "id": n.id,
                            **({"block": n.block} if n.block else {}),
                            **({"type": n.type} if n.type else {}),
                            **({"in": n.inputs} if n.inputs else {}),
                            **({"out": n.outputs} if n.outputs else {}),
                            **({"when": n.when} if n.when else {}),
                            **({"foreach": n.foreach} if n.foreach else {}),
                            **({"while": n.while_} if n.while_ else {}),
                            **({"body": n.body} if n.body else {}),
                            **({"call": n.call} if n.call else {}),
                        }
                        for n in design2.graph
                    ],
                }
                plan2 = Plan.model_validate(plan_dict2)
                errors2 = validate_plan(plan2, registry)
                if not errors2:
                    reasoning = "LLM生成+自己修復"
                    repair_log.append({"phase": f"repair_attempt_{i+1}", "status": "ok"})
                    return GeneratedPlan(plan=plan2, reasoning=reasoning, initial_errors=list(errors), repair_log=repair_log)
                errors = errors2
                repair_log.append({"phase": f"repair_attempt_{i+1}", "errors": list(errors2)})
                plan_dict = plan_dict2
            except Exception:
                # continue attempts
                continue
        # 設計思想に基づき、最終的にエラーを報告
        error_msg = "Plan validation failed:\n" + "\n".join(f"- {e}" for e in errors)
        raise ValueError(error_msg)
    reasoning = "LLM生成 (LangChain + OpenAI/Azure)"
    return GeneratedPlan(plan=plan, reasoning=reasoning)


def generate_business_overview(
    instruction: str,
    documents_text: Optional[List[str]] = None,
) -> BusinessOverview:
    """Step 1: Business Overview generation (structured)."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from core.plan.llm_factory import build_chat_llm

    if not _have_llm_key():
        raise RuntimeError(
            "OPENAI_API_KEY or AZURE_OPENAI_API_KEY is required for plan generation. "
            "Please set one of these environment variables."
        )

    norm_docs = _normalize_documents_text(documents_text)
    docs_joined = "\n\n".join(norm_docs)
    system = """
        あなたは業務設計アシスタントです。業務の概要(BusinessOverview)を論理式にて整理し、JSONで作成してください。
        不明点がある場合は open_points のみを返し、解消後は title, inputs, processes, outputs をすべて回答してください。
        processes では、必要に応じて when/foreach/while_ を用いて条件分岐・反復・再試行を表現してください。
        - when: { expr: string } のように簡潔に条件を表現
        - foreach: { item: string, in: string } で入力集合の反復を表現（例: { item: "row", in: "${inputs.rows}" }）
        - while_: { expr: string } で再試行や条件付き継続を表現
        参照は ${id.alias} 形式や ${vars.key} を用いても構いません（必要最低限に留めてください）。
    """
    human = f"""
指示:
{instruction}

参考文書(要約):
{docs_joined}
 
# 出力スキーマ（要約）
- inputs: 業務の入力（ファイル/データ/指示など）
- processes: 各処理の説明と、必要なら when/foreach/while_ で制御フローを表現
- outputs: 業務の出力
- open_points: 不明点

# Few-shot（簡略例）
processes: [
  {{
    "id": "read_zip",
    "description": "ZIPを解凍してファイル一覧を得る",
    "foreach": {{"item": "file", "in": "${{inputs.zip_files}}"}}
  }},
  {{
    "id": "parse_if_needed",
    "description": "必要な場合だけ解析する",
    "when": {{"expr": "${{vars.need_parse}}"}}
  }},
  {{
    "id": "retry_llm",
    "description": "抽出が安定するまで再試行",
    "while_": {{"expr": "${vars.retry}"}}
  }},
]
"""
    llm, _ = build_chat_llm(temperature=0)
    try:
        llm_structured = llm.with_structured_output(BusinessOverview, method="function_calling")
        res_llm = llm_structured.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        return res_llm
    except Exception:
        res = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        text = res.content if isinstance(res.content, str) else str(res.content)
        data = json.loads(_extract_json(text))
        return BusinessOverview.model_validate(data)


def generate_plan_skeleton(
    overview: BusinessOverview,
    registry: BlockRegistry,
    *,
    selected_templates: Optional[List[str]] = None,
    options: Optional[DesignEngineOptions] = None,
    res_qa: Optional[str] = None,
) -> PlanSkeleton:
    """Step 2: Generate a Plan Skeleton using only block names/description.

    Performs lightweight validation: duplicate ids, unknown blocks, layout refs.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from core.plan.llm_factory import build_chat_llm

    if not _have_llm_key():
        raise RuntimeError(
            "OPENAI_API_KEY or AZURE_OPENAI_API_KEY is required for plan generation. "
            "Please set one of these environment variables."
        )

    catalog = _compute_block_catalog(registry)
    # catalogの各要素について、id,descriptionを抽出
    catalog = [{"id": b["id"], "description": b["description"]} for b in catalog]

    # st.code(json.dumps(catalog, ensure_ascii=False, indent=2))

    # Load template summaries
    selected_templates_specs: List[TemplateSpec] = []
    try:
        all_templates = load_all_templates()
        if selected_templates:
            for tid in selected_templates:
                t = all_templates.get(tid)
                if t:
                    selected_templates_specs.append(t)
    except Exception:
        selected_templates_specs = []
    template_summaries = summarize_templates(selected_templates_specs) if selected_templates_specs else []

    system = (
        "あなたは業務設計エンジンです。BusinessOverviewを基に Plan Skeleton（関数呼び出しのJSON引数）を生成してください。"
        "目的はブロックの“接続設計”です。実在する入出力キー名は不要で、抽象的なキー名（例: source, data, result）を使用して構いません。"
        "以下のルールを厳守してください:\n"
        "- 参照は常に ${nodeId.alias} 形式のみ\n"
        "- ui.* はソースとして少なくとも1つの出力エイリアスを産む\n"
        "- 処理系（processing/ai/nlp 等）は少なくとも1つの入力エイリアスを消費し、1つ以上の出力エイリアスを産む\n"
        "- シンク系（excel/export 等）は少なくとも1つの入力エイリアスを消費\n"
        "- 集合（files/rows/items/records 等）を下流が処理する場合、必ず foreach を使用\n"
        "- 各ノードは 'id' を一意・空不可、'block' は使用可能なカタログの 'id' から選ぶ\n"
        "- ui.layout は graph のノードIDを上流→下流の順で並べる\n"
        "- 不明点がある場合のみ open_points に質問を列挙し、open_points が空のときは ui と graph を完全に返す"
    )
    human = f"""
# BusinessOverview:
{json.dumps(overview.model_dump(), ensure_ascii=False)}

# 使用できるブロック一覧:
{json.dumps(catalog, ensure_ascii=False)}

# 参考となる選択テンプレート:
{json.dumps(template_summaries, ensure_ascii=False)}

# 出力仕様/制約:
- JSONスキーマ: {{
  "ui": {{"layout": [str]}},
  "graph": [{{
    "id": str,
    "block": str,
    "inputs": object,   // 少なくとも1件（ソースノードを除く）
    "outputs": object,  // 少なくとも1件（シンクノードを除く）
    "when": object | null,
    "foreach": object | null,
    "while_": object | null,
    "description": str | null
  }}],
  "open_points": [str] | null
}}
- 接続規約:
  - 参照は {{{{nodeId.alias}}}} のみ
  - ui.* は outputs に少なくとも1つのエイリアスを定義（例: {{"data": "uploaded"}}）
  - 処理系は inputs で上流のエイリアスを少なくとも1つ参照し、outputs で新しいエイリアスを定義
  - シンク系は inputs で上流のエイリアスを少なくとも1つ参照
  - 実在キー名は不要。抽象キー（例: source/data/result など）で良い

# 簡易例（抽象; 実在キー名は使用しない）:
ui: {{"layout": ["input_ui", "transform", "export"]}}
graph: [
  {{
    "id": "input_ui",
    "block": "ui.interactive_input",
    "inputs": {{}},
    "outputs": {{"data": "user_inputs"}},
    "description": "ユーザーから必要な入力を収集する"
  }},
  {{
    "id": "transform",
    "block": "ai.process_llm",
    "inputs": {{"source": "${{{{input_ui.user_inputs}}}}"}},
    "outputs": {{"result": "normalized"}},
    "description": "入力を正規化・抽出する"
  }},
  {{
    "id": "export",
    "block": "excel.write",
    "inputs": {{"data": "${{{{transform.normalized}}}}"}},
    "outputs": {{"result": "exported"}},
    "description": "結果をExcelに出力する"
  }}
]

# when の例（条件分岐; 抽象）:
ui: {{"layout": ["input_ui", "transform_if", "export"]}}
graph: [
  {{
    "id": "input_ui",
    "block": "ui.interactive_input",
    "inputs": {{}},
    "outputs": {{"data": "user_inputs"}}
  }},
  {{
    "id": "transform_if",
    "block": "ai.process_llm",
    "when": {{"expr": "${{{{vars.use_llm}}}}"}},
    "inputs": {{"source": "${{{{input_ui.user_inputs}}}}"}},
    "outputs": {{"result": "normalized"}}
  }},
  {{
    "id": "export",
    "block": "excel.write",
    "inputs": {{"data": "${{{{transform_if.normalized}}}}"}},
    "outputs": {{"result": "exported"}}
  }}
]

# foreach の例（反復処理; 抽象）:
ui: {{"layout": ["read_rows", "process_each_row", "export"]}}
graph: [
  {{
    "id": "read_rows",
    "block": "file.read_csv",
    "inputs": {{}},
    "outputs": {{"rows": "rows"}}
  }},
  {{
    "id": "process_each_row",
    "block": "nlp.summarize_structured",
    "foreach": {{"item": "row", "in": "${{{{read_rows.rows}}}}"}},
    "inputs": {{"source": "${{{{read_rows.rows}}}}"}},
    "outputs": {{"result": "summaries"}}
  }},
  {{
    "id": "export",
    "block": "excel.write",
    "inputs": {{"data": "${{{{process_each_row.summaries}}}}"}},
    "outputs": {{"result": "exported"}}
  }}
]

# while_ の例（条件付き再試行; 抽象）:
ui: {{"layout": ["input_ui", "retry_llm", "export"]}}
graph: [
  {{
    "id": "input_ui",
    "block": "ui.interactive_input",
    "inputs": {{}},
    "outputs": {{"data": "user_inputs"}}
  }},
  {{
    "id": "retry_llm",
    "block": "ai.process_llm",
    "while_": {{"expr": "${{{{vars.need_retry}}}}"}},
    "inputs": {{"source": "${{{{input_ui.user_inputs}}}}"}},
    "outputs": {{"result": "normalized"}}
  }},
  {{
    "id": "export",
    "block": "excel.write",
    "inputs": {{"data": "${{{{retry_llm.normalized}}}}"}},
    "outputs": {{"result": "exported"}}
  }}
]

"""
    if res_qa:
        human += res_qa
    
    llm, _ = build_chat_llm(temperature=0)
    try:
        llm_structured = llm.with_structured_output(PlanSkeleton, method="function_calling")
        sk = llm_structured.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        st.text(sk)
    except Exception:
        res = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        text = res.content if isinstance(res.content, str) else str(res.content)
        data = json.loads(_extract_json(text))
        sk = PlanSkeleton.model_validate(data)

    errs = _validate_skeleton(sk, registry)
    if errs:
        raise ValueError("Plan Skeleton validation failed:\n" + "\n".join(f"- {e}" for e in errs))
    return sk


def generate_detail_plan(
    skeleton: PlanSkeleton,
    registry: BlockRegistry,
    selected_templates: Optional[List[str]] = None,
    options: Optional[DesignEngineOptions] = None,
    res_qa: Optional[str] = None,
) -> GeneratedPlan:
    """Step 3: Detail a PlanSkeleton into an executable Plan."""
    # Use instruction/docs context to generate a detailed plan; skeleton provides block hints implicitly via templates/overview
    if not _have_llm_key():
        raise RuntimeError(
            "OPENAI_API_KEY or AZURE_OPENAI_API_KEY is required for plan generation. "
            "Please set one of these environment variables."
        )

    catalog = _compute_block_catalog(registry)
    
    # Load template summaries
    selected_templates_specs: List[TemplateSpec] = []
    try:
        all_templates = load_all_templates()
        if selected_templates:
            for tid in selected_templates:
                t = all_templates.get(tid)
                if t:
                    selected_templates_specs.append(t)
    except Exception:
        selected_templates_specs = []
    template_summaries = summarize_templates(selected_templates_specs) if selected_templates_specs else []

    system = (
        "あなたは業務設計エンジンです。PlanSkeletonを詳細化しPlan(YAML)を完成させてください。"
        "出力は厳密にYAMLのみ。 JSONスキーマに準じた Plan を生成してください。"
        "各ノードは存在するblock idのみを参照可能。必ず 'in'/'out' を使用し、ブロックスペックの入出力キーと一致させること。"
        "参照は ${{nodeId.alias}} / ${{vars.key}} 形式のみ。ローカル出力キー名の参照は禁止。"
    )
    human = f"""
# PlanSkeleton:
{json.dumps(skeleton.model_dump(), ensure_ascii=False)}

# 使用できるブロック一覧（スキーマ含む）:
{json.dumps(catalog, ensure_ascii=False)}

# 参考となるテンプレート:
{json.dumps(template_summaries, ensure_ascii=False)}

# YAML仕様:
- 以下のYAMLスキーマに従うこと: {{
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

# 制約:
- キー名は 'in'/'out' のみ使用（'inputs'/'outputs' は使用禁止）
- out のキーはブロックの outputs に存在するキー、in のキーはブロックの inputs に存在するキーのみ使用
- 参照は ${{node_id.alias}} または ${{vars.key}} 形式のみ使用（alias は各ノードの out によって定義）。
  - 良い例: out: {{ collected_data: invoice_file }} → ${{input_invoice_file.invoice_file}}
  - 悪い例: ${{input_invoice_file.collected_data}}
- ${{vars.*}} を使う場合、必ず対応する変数を vars セクションに定義
- ai.process_llm の 'evidence_data' は object 型、'output_schema' は非空オブジェクト必須、'prompt' または 'instruction' を少なくとも一方指定
  - output_schema はオブジェクト形式（例: {{{{field1: string, field2: number}}}}）で、空や文字列は不可
- ファイル処理が必要な場合、最初に ui.interactive_input を配置し、mode は 'collect' を使用。
  requirements は配列とし、file 入力を下記のように定義:
  例: in: {{ mode: collect, message: "...", requirements: [{{ id: "invoice_file", type: "file", label: "請求書ファイル", accept: ".xlsx,.xls" }}] }}; out: {{ collected_data: invoice_file }}
- Excel 出力は excel.write を使用し、column_updates の中に columns 配列と values を含める:
  例: in: {{ workbook: ${{input_invoice_file.invoice_file}}, column_updates: {{ sheet: "結果", columns: [{{header: "請求書番号", path: "invoice_no"}}], values: ${{match_records.results}} }} }}
"""
    if res_qa:
        human += res_qa
    st.text(human)
    llm, _ = build_chat_llm(temperature=0)
    try:
        llm_structured = llm.with_structured_output(Plan, method="function_calling")
        dt = llm_structured.invoke([SystemMessage(content=system), HumanMessage(content=human)])
    except Exception:
        res = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        text = res.content if isinstance(res.content, str) else str(res.content)
        data = json.loads(_extract_json(text))
        dt = Plan.model_validate(data)

    # errs = _validate_plan(dt, registry)
    # if errs:
    #     raise ValueError("Plan detail validation failed:\n" + "\n".join(f"- {e}" for e in errs))
    return dt




