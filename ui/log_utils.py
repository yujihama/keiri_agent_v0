from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st


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


