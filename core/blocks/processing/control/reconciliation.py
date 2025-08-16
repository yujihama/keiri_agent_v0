from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.blocks.base import BlockContext, ProcessingBlock


class ControlReconciliationBlock(ProcessingBlock):
    id = "control.reconciliation"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        left = inputs.get("left") or []
        right = inputs.get("right") or []
        keys = inputs.get("keys") or []
        options = inputs.get("options") or {}

        if not isinstance(left, list):
            left = []
        if not isinstance(right, list):
            right = []
        if not isinstance(keys, list):
            keys = []
        key_names: List[str] = [str(k) for k in keys if isinstance(k, str)]

        def _key(obj: Dict[str, Any]) -> Tuple[Any, ...]:
            if not isinstance(obj, dict):
                return tuple()
            vals: List[Any] = []
            for k in key_names:
                v = None
                for kk, vv in obj.items():
                    if str(kk).lower() == k.lower():
                        v = vv
                        break
                vals.append(v)
            return tuple(vals)

        left_map: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for it in left:
            if isinstance(it, dict):
                left_map[_key(it)] = it
        right_map: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        for it in right:
            if isinstance(it, dict):
                right_map[_key(it)] = it

        matched: List[Dict[str, Any]] = []
        diffs: List[Dict[str, Any]] = []
        left_only: List[Dict[str, Any]] = []
        right_only: List[Dict[str, Any]] = []

        all_keys = set(left_map.keys()) | set(right_map.keys())
        compare_fields = [str(f) for f in (options.get("compare_fields") or []) if isinstance(f, str)]

        for k in all_keys:
            l = left_map.get(k)
            r = right_map.get(k)
            if l is not None and r is not None:
                # compare values for fields
                d: Dict[str, Any] = {"key": list(k), "differences": []}
                fields = compare_fields or sorted({*l.keys(), *r.keys()})
                for f in fields:
                    lv = next((v for kk, v in l.items() if str(kk).lower() == f.lower()), None)
                    rv = next((v for kk, v in r.items() if str(kk).lower() == f.lower()), None)
                    if lv != rv:
                        d["differences"].append({"field": f, "left": lv, "right": rv})
                if d["differences"]:
                    diffs.append(d)
                else:
                    matched.append({"key": list(k), "item_left": l, "item_right": r})
            elif l is not None:
                left_only.append(l)
            else:
                right_only.append(r)  # type: ignore[list-item]

        return {
            "matched": matched,
            "diffs": diffs,
            "left_only": left_only,
            "right_only": right_only,
            "summary": {
                "left": len(left),
                "right": len(right),
                "matched": len(matched),
                "diffs": len(diffs),
                "left_only": len(left_only),
                "right_only": len(right_only),
            },
        }