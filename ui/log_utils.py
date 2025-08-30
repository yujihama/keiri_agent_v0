from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st
from pydantic import BaseModel, Field, ConfigDict

from core.plan.llm_factory import build_chat_llm, have_llm_key

try:
    from langchain_core.messages import SystemMessage, HumanMessage  # type: ignore
except Exception:  # pragma: no cover - optional at import time
    SystemMessage = object  # type: ignore
    HumanMessage = object  # type: ignore


def read_jsonl(file: Path) -> List[Dict[str, Any]]:
    try:
        text = file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        text = ""
    lines = text.splitlines()
    events: List[Dict[str, Any]] = []
    for l in lines:
        s = str(l).strip()
        if not s:
            continue
        try:
            events.append(json.loads(s))
        except Exception:
            continue
    return events


def filter_events(
    events: List[Dict[str, Any]],
    *,
    types: List[str] | None,
    nodes: List[str] | None,
    tags: List[str] | None,
    levels: List[str] | None,
    parent_run_id: str | None,
    query: str | None,
) -> List[Dict[str, Any]]:
    filtered = [e for e in events if (not types) or e.get("type") in types]
    if nodes:
        filtered = [e for e in filtered if e.get("node") in nodes or e.get("node") is None]
    if tags:
        filtered = [e for e in filtered if e.get("tag") in tags or e.get("tag") is None]
    if levels:
        filtered = [e for e in filtered if e.get("level") in levels or e.get("level") is None]
    if parent_run_id:
        filtered = [e for e in filtered if e.get("parent_run_id") == parent_run_id or e.get("run_id") == parent_run_id]
    if query:
        ql = query.lower()
        def _hit(ev: Dict[str, Any]) -> bool:
            try:
                src = [
                    str(ev.get("message", "")),
                    json.dumps(ev.get("data"), ensure_ascii=False, default=str),
                    json.dumps(ev.get("error_details"), ensure_ascii=False, default=str),
                ]
                return any(ql in s.lower() for s in src if s)
            except Exception:
                return False
        filtered = [e for e in filtered if _hit(e)]
    try:
        filtered.sort(key=lambda e: (int(e.get("seq", 0)), str(e.get("ts", ""))))
    except Exception:
        filtered.sort(key=lambda e: str(e.get("ts", "")))
    return filtered



# ============== サマリー用ユーティリティ ==============
_DEFAULT_ALLOWED_TYPES: List[str] = [
    "start",
    "node_start",
    "node_finish",
    "node_skip",
    "error",
    "loop_start",
    "loop_finish",
    "loop_iter_start",
    "loop_iter_finish",
    "subflow_start",
    "subflow_finish",
    "ui_wait",
    "ui_submit",
    "ui_reuse",
    "finish_summary",
    "finish",
]


def _brief_dict(d: Dict[str, Any], max_items: int = 8) -> str:
    try:
        items = []
        for i, (k, v) in enumerate(d.items()):
            if i >= max_items:
                items.append("…")
                break
            # バイナリ/巨大データの断捨離
            if isinstance(v, (bytes, bytearray)):
                items.append(f"{k}=<bytes:{len(v)}>" )
                continue
            sv = str(v)
            if len(sv) > 200:
                sv = sv[:200] + "…"
            if "base64" in k.lower() or "__type" in k.lower():
                items.append(f"{k}=<omitted>")
            else:
                items.append(f"{k}={sv}")
        return ", ".join(items)
    except Exception:
        return "<unserializable>"


def _format_event_brief(e: Dict[str, Any]) -> str:
    t = str(e.get("ts" , ""))
    et = str(e.get("type", ""))
    node = e.get("node")
    if et == "start":
        return f"{t} start plan={e.get('plan')} run_id={e.get('run_id')}"
    if et == "node_start":
        return f"{t} node_start node={node}"
    if et == "node_finish":
        ms = e.get("elapsed_ms")
        att = e.get("attempts")
        return f"{t} node_finish node={node} elapsed_ms={ms} attempts={att}"
    if et == "node_skip":
        return f"{t} node_skip node={node} reason={e.get('reason')}"
    if et == "error":
        msg = str(e.get("message", ""))
        code = str(e.get("error_code", ""))
        return f"{t} error node={node} code={code} message={msg}"
    if et in {"loop_start", "loop_finish", "loop_iter_start", "loop_iter_finish"}:
        return f"{t} {et} node={node}"
    if et in {"subflow_start", "subflow_finish"}:
        return f"{t} {et} node={node}"
    if et == "finish_summary":
        return (
            f"{t} finish_summary total_nodes={e.get('total_nodes')} "
            f"success_nodes={e.get('success_nodes')} error_nodes={e.get('error_nodes')} "
            f"skipped_nodes={e.get('skipped_nodes')}"
        )
    if et == "finish":
        return f"{t} finish plan={e.get('plan')} run={e.get('run')}"
    # fallback: 重要でないタイプは短く
    extras = {k: v for k, v in e.items() if k not in ("ts", "type", "plan", "run_id", "parent_run_id")}
    return f"{t} {et} {_brief_dict(extras)}"


def build_sanitized_log_text(
    events: List[Dict[str, Any]],
    *,
    allowed_types: List[str] | None = None,
    max_lines: int = 600,
    max_chars: int = 12000,
) -> str:
    """LLM投入用にテキスト整形したログを作成（非テキスト/巨大データは抑制）。"""
    allow = allowed_types or _DEFAULT_ALLOWED_TYPES
    # 型フィルタと時系列ソート（既にfilter_eventsでソート済みでも安全）
    filtered = [e for e in events if e.get("type") in allow]
    try:
        filtered.sort(key=lambda e: (int(e.get("seq", 0)), str(e.get("ts", ""))))
    except Exception:
        filtered.sort(key=lambda e: str(e.get("ts", "")))

    lines: List[str] = []
    total = 0
    for e in filtered[: max_lines * 2]:  # 軽く余裕を持ってから文字数で制限
        line = _format_event_brief(e)
        if not isinstance(line, str):
            continue
        if total + len(line) + 1 > max_chars:
            lines.append("…(truncated)…")
            break
        lines.append(line)
        total += len(line) + 1
        if len(lines) >= max_lines:
            lines.append("…(truncated)…")
            break
    header = "# 実行ログ（サマリー用に整形）\n"
    return header + "\n".join(lines)


def _snippet(s: str, max_chars: int) -> str:
    try:
        return s if len(s) <= max_chars else (s[: max_chars] + "…")
    except Exception:
        return s


def _looks_like_encoded_or_binary(s: str) -> bool:
    try:
        if "\x00" in s:
            return True
        if s.startswith("data:"):
            return True
        if len(s) > 400:
            allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r")
            ratio = sum(1 for c in s if c in allowed) / max(1, len(s))
            if ratio > 0.9:
                return True
        return False
    except Exception:
        return False


def build_results_excerpt_text(
    results: Dict[str, Any] | None,
    *,
    per_key_chars: int = 1000,
    joiner: str = " | ",
) -> str:
    """結果のトップレベル各キーごとに、読める文字列を再帰収集し先頭 per_key_chars で整形。

    - 各キーのサブツリーから文字列のみ抽出（数値/boolは除外）
    - base64/バイナリ相当は除外
    - 1キーあたり合計で先頭 per_key_chars までにクリップ
    - すべてのトップレベルキーを網羅
    """
    if not isinstance(results, dict) or not results:
        return ""
    lines: List[str] = []

    def _collect_texts(val: Any, out: List[str]) -> None:
        if isinstance(val, str):
            if val and not _looks_like_encoded_or_binary(val):
                out.append(val)
            return
        if isinstance(val, dict):
            for k, v in val.items():
                key = str(k)
                if "base64" in key.lower() or "bytes" in key.lower():
                    continue
                _collect_texts(v, out)
            return
        if isinstance(val, (list, tuple)):
            for v in val:
                _collect_texts(v, out)
            return
        # その他型は無視

    for k, v in results.items():
        texts: List[str] = []
        _collect_texts(v, texts)
        if not texts:
            continue
        combined = joiner.join(texts)
        if len(combined) > per_key_chars:
            combined = combined[: per_key_chars] + "…"
        try:
            key_name = str(k)
        except Exception:
            key_name = "key"
        lines.append(f"{key_name}: {combined}")

    if not lines:
        return ""
    header = "# ブロック結果（テキスト抜粋）\n"
    return header + "\n".join(lines)


def build_summary_input_text(
    events: List[Dict[str, Any]],
    results: Dict[str, Any] | None,
    *,
    max_log_lines: int = 600,
    max_log_chars: int = 12000,
    per_key_chars: int = 1000,
) -> str:
    """LLMの入力として、整形ログ + 結果テキスト抜粋を合成した文字列を作成。"""
    log_part = build_sanitized_log_text(
        events,
        allowed_types=None,
        max_lines=max_log_lines,
        max_chars=max_log_chars,
    )
    res_part = build_results_excerpt_text(results, per_key_chars=per_key_chars)
    if res_part:
        return log_part + "\n\n" + res_part
    return log_part


class ErrorItem(BaseModel):
    message: str = Field(description="エラーメッセージ")
    node: str | None = Field(default=None, description="エラー発生ノード")
    code: str | None = Field(default=None, description="エラーコード")
    model_config = ConfigDict(extra="forbid")


class RunSummaryModel(BaseModel):
    overview: str = Field(description="実行全体の要約（2-5文）")
    highlights: List[str] = Field(default_factory=list, description="主要な出来事の箇条書き")
    errors: List[ErrorItem] = Field(default_factory=list, description="発生したエラーのリスト")
    model_config = ConfigDict(extra="forbid")


def summarize_with_llm(sanitized_text: str, *, temperature: float = 0.0) -> RunSummaryModel:
    """LLMで実行サマリーを構造化生成（Pydanticで型安全）。"""
    if not have_llm_key():
        # キーが無い場合は簡易サマリーのみ
        return RunSummaryModel(
            overview="LLMキーが未設定のため簡易サマリーのみ表示します。",
            highlights=["ログは正常に整形されました"],
        )

    llm, model_label = build_chat_llm(temperature=temperature)
    Structured = RunSummaryModel
    structured_llm = llm.with_structured_output(Structured)

    sys = (
        "あなたは実行ログの要約アシスタントです。"
        "与えられた整形済みログだけを根拠に、過不足なく日本語で要約してください。"
        "バイナリ/画像/長大データは既に省略済みです。冗長な逐次ログは箇条書きに集約してください。"
        "エラーがあれば簡潔に列挙し、次に取るべきアクションがあれば提案してください。"
    )
    human = (
        "以下は実行ログおよびブロック結果のテキスト抜粋です。読み取り、実行概要・ハイライト・エラーを構造化で返してください。\n\n"
        f"{sanitized_text}"
    )
    data = structured_llm.invoke([
        SystemMessage(content=sys),
        HumanMessage(content=human),
    ])
    # run_id/model_labelは必要なら上位で扱う
    return data

