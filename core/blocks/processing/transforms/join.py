from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


def _get_ci(obj: Dict[str, Any], key: str) -> Any:
    if not isinstance(obj, dict):
        return None
    for k, v in obj.items():
        if str(k).lower() == str(key).lower():
            return v
    return None


def _coerce_number(val: Any) -> float | None:
    if val is None:
        return None
    # Accept numbers or numeric strings with commas
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).strip()
        if s == "":
            return None
        s = s.replace(",", "")
        return float(s)
    except Exception:
        return None


class JoinBlock(ProcessingBlock):
    id = "transforms.join"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        left = inputs.get("left") or []
        right = inputs.get("right") or []
        left_key = str(inputs.get("left_key") or "").strip()
        right_key = str(inputs.get("right_key") or "").strip()
        strategy = str(inputs.get("strategy") or "first").lower()
        select = inputs.get("select") or {}

        if not isinstance(left, list):
            left = []
        if not isinstance(right, list):
            right = []
        if not isinstance(select, dict):
            select = {}

        # Pre-index right by comparable key to speed lookups
        right_index: Dict[str, List[Dict[str, Any]]] = {}
        for r in right:
            if not isinstance(r, dict):
                continue
            rv = _get_ci(r, right_key)
            # Normalize numeric equivalence: represent as canonical string key
            num = _coerce_number(rv)
            key_repr = f"num:{num:.6f}" if isinstance(num, float) else f"str:{str(rv)}"
            right_index.setdefault(key_repr, []).append(r)

        out_rows: List[Dict[str, Any]] = []
        matches = 0
        for l in left:
            if not isinstance(l, dict):
                continue
            lv = _get_ci(l, left_key)
            num = _coerce_number(lv)
            key_repr = f"num:{num:.6f}" if isinstance(num, float) else f"str:{str(lv)}"
            candidates = right_index.get(key_repr, [])
            if not candidates:
                continue
            if strategy == "first":
                candidates = candidates[:1]
            for r in candidates:
                row: Dict[str, Any] = {}
                for out_name, path in select.items():
                    try:
                        side, field = (str(path).split(".", 1) + [""])[:2]
                    except Exception:
                        side, field = "", ""
                    if side == "left":
                        row[str(out_name)] = _get_ci(l, field)
                    elif side == "right":
                        row[str(out_name)] = _get_ci(r, field)
                    else:
                        row[str(out_name)] = None
                out_rows.append(row)
                matches += 1

        return {"rows": out_rows, "summary": {"left": len(left), "right": len(right), "matches": matches}}


