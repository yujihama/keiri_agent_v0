from __future__ import annotations

from typing import Any, Dict, List, Tuple
from datetime import datetime, date

from core.blocks.base import BlockContext, ProcessingBlock
import streamlit as st


class FilterItemsBlock(ProcessingBlock):
    id = "transforms.filter_items"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        conditions = inputs.get("conditions") or []
        options = inputs.get("options") or {}
        case_insensitive = bool(options.get("case_insensitive", True))

        def _get_by_path(obj: Any, path: str) -> Any:
            cur = obj
            for seg in str(path).split("."):
                s = seg.strip()
                if not s:
                    return None
                if isinstance(cur, dict):
                    if case_insensitive:
                        lk = None
                        for k in cur.keys():
                            if str(k).lower() == s.lower():
                                lk = k
                                break
                        cur = cur.get(lk) if lk is not None else None
                    else:
                        cur = cur.get(s)
                else:
                    return None
            return cur

        def _coerce_dt(v: Any) -> Any:
            if isinstance(v, (datetime, date)):
                return v
            if isinstance(v, str):
                for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
                    try:
                        return datetime.strptime(v, fmt)
                    except Exception:
                        continue
            return v

        def _compare(op: str, left: Any, right: Any, right2: Any = None) -> bool:
            if op in {"between"}:
                l = _coerce_dt(left)
                r1 = _coerce_dt(right)
                r2 = _coerce_dt(right2)
                try:
                    return r1 <= l <= r2
                except Exception:
                    try:
                        return float(right) <= float(left) <= float(right2)  # type: ignore[arg-type]
                    except Exception:
                        return False
            if op in {"eq", "ne", "contains", "in"}:
                if case_insensitive and isinstance(left, str) and isinstance(right, str):
                    l, r = left.lower(), right.lower()
                else:
                    l, r = left, right
                if op == "eq":
                    return l == r
                if op == "ne":
                    return l != r
                if op == "contains":
                    try:
                        return r in l  # type: ignore[operator]
                    except Exception:
                        return False
                if op == "in":
                    try:
                        return l in right  # type: ignore[operator]
                    except Exception:
                        return False
            # numeric/date comparisons
            l = _coerce_dt(left)
            r = _coerce_dt(right)
            try:
                if isinstance(l, (datetime, date)) and isinstance(r, (datetime, date)):
                    pass  # direct compare
                else:
                    l = float(l)  # type: ignore[assignment]
                    r = float(r)  # type: ignore[assignment]
            except Exception:
                return False
            if op == "gt":
                return l > r  # type: ignore[operator]
            if op == "gte":
                return l >= r  # type: ignore[operator]
            if op == "lt":
                return l < r  # type: ignore[operator]
            if op == "lte":
                return l <= r  # type: ignore[operator]
            return False

        filtered: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                excluded.append(it)  # type: ignore[arg-type]
                continue
            ok = True
            for cond in conditions if isinstance(conditions, list) else []:
                if not isinstance(cond, dict):
                    continue
                field = cond.get("field")
                op = (cond.get("operator") or "eq").lower()
                v1 = cond.get("value")
                v2 = cond.get("value2")
                left = _get_by_path(it, str(field))
                if not _compare(op, left, v1, v2):
                    ok = False
                    break
            (filtered if ok else excluded).append(it)

        return {
            "filtered": filtered,
            "excluded": excluded,
            "summary": {"input": len(items) if isinstance(items, list) else 0, "filtered": len(filtered), "excluded": len(excluded)},
        }


