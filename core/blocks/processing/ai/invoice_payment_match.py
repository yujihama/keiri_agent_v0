from __future__ import annotations

from typing import Any, Dict, List
from dataclasses import dataclass
import re

from core.blocks.base import BlockContext, ProcessingBlock


@dataclass
class _PaymentRecord:
    description: str
    amount: float


class InvoicePaymentMatchBlock(ProcessingBlock):
    id = "ai.invoice_payment_match"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """請求書と入金明細の照合。

        - APIキーがある場合: LLM で照合（LangChain/OpenAI）。
        - ない場合: 既存のヒューリスティックにフォールバック。
        """

        evidence = inputs.get("evidence_data") or {}
        instruction = inputs.get("instruction", "")

        files: List[Dict[str, Any]] = evidence.get("files", []) if isinstance(evidence, dict) else []

        def _heuristic() -> Dict[str, Any]:
            # 金額の単純抽出・集計（従来のスタブ挙動を残す）
            amt_pattern = re.compile(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?")
            matched_items: List[Dict[str, Any]] = []
            grand_total = 0.0
            for f in files:
                name = f.get("name", "")
                text = f.get("text_excerpt", "") or ""
                amts: List[float] = []
                for m in amt_pattern.findall(text):
                    try:
                        amts.append(float(m.replace(",", "")))
                    except Exception:
                        continue
                if amts:
                    s = sum(amts)
                    grand_total += s
                    matched_items.append({"file": name, "count": len(amts), "sum": s})
            results = {"matched": len(matched_items) > 0, "items": matched_items}
            summary = {
                "instruction": instruction,
                "files": len(files),
                "matched_files": len(matched_items),
                "grand_total": round(grand_total, 2),
            }
            return {"results": results, "summary": summary}

        # LLM 実行（APIキーがあれば）
        import os
        have_llm = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
        if not have_llm:
            return _heuristic()

        try:
            # 入力を簡潔に整形（過大トークン抑制）
            sample = []
            for f in files[:10]:
                sample.append(
                    {
                        "file": f.get("name"),
                        "text_excerpt": (f.get("text_excerpt") or "")[:1500],
                    }
                )

            from langchain_openai import ChatOpenAI
            from langchain_core.messages import SystemMessage, HumanMessage

            sys_prompt = (
                "あなたは経理の照合作業を支援します。入力のテキスト抜粋から金額・請求/入金の候補を抽出し、\n"
                "一致/不一致の根拠を含む JSON を返してください。出力は厳密に JSON のみです。\n"
                "スキーマ: {\\n results: {matched: boolean, items: [{file: string, count: number, sum: number}]},\\n"
                " summary: {files: number, matched_files: number, grand_total: number} \\n                }"
            )
            human = {
                "instruction": instruction,
                "evidence_preview": sample,
            }
            model_name = os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1"
            temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0"))
            llm = ChatOpenAI(model=model_name, temperature=temperature)
            res = llm.invoke(
                [
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content=f"""入力:\n{human}"""),
                ]
            )
            text = res.content if isinstance(res.content, str) else str(res.content)

            # JSON 部分を抽出
            def _extract_json(s: str) -> str:
                import re as _re
                m = _re.search(r"```(?:json)?\n([\s\S]*?)```", s)
                if m:
                    return m.group(1).strip()
                start = s.find("{")
                end = s.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return s[start : end + 1]
                return s

            import json as _json

            data = _json.loads(_extract_json(text))
            # 必須フィールドの最低限検証/フォールバック
            if not isinstance(data, dict) or "results" not in data or "summary" not in data:
                return _heuristic()
            # 型の粗い補正
            results = data.get("results") or {}
            summary = data.get("summary") or {}
            if not isinstance(results, dict) or not isinstance(summary, dict):
                return _heuristic()
            # 欠損値の補完
            summary.setdefault("files", len(files))
            items = results.get("items") or []
            if isinstance(items, list):
                summary.setdefault("matched_files", len(items))
                total = 0.0
                for it in items:
                    try:
                        total += float(it.get("sum", 0) or 0)
                    except Exception:
                        continue
                summary.setdefault("grand_total", round(total, 2))
            return {"results": results, "summary": summary}
        except Exception:
            # LLM 失敗時はヒューリスティックで継続
            return _heuristic()


