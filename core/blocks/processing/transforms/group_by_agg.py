from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.blocks.base import BlockContext, ProcessingBlock


class GroupByAggBlock(ProcessingBlock):
    id = "transforms.group_by_agg"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        by = inputs.get("by") or []
        aggs = inputs.get("aggregations") or []
        if not isinstance(items, list):
            items = []
        by_keys = [str(k) for k in by] if isinstance(by, list) else []

        def _get(obj: Dict[str, Any], key: str):
            if not isinstance(obj, dict):
                return None
            for k, v in obj.items():
                if str(k).lower() == key.lower():
                    return v
            return None

        buckets: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            gkey = tuple(_get(it, k) for k in by_keys)
            buckets.setdefault(gkey, []).append(it)

        out_rows: List[Dict[str, Any]] = []
        for gk, rows in buckets.items():
            out: Dict[str, Any] = {by_keys[i]: gk[i] for i in range(len(by_keys))}
            for spec in aggs if isinstance(aggs, list) else []:
                if not isinstance(spec, dict):
                    continue
                field = str(spec.get("field"))
                op = str(spec.get("op", "sum")).lower()
                vals: List[float] = []
                for r in rows:
                    v = _get(r, field)
                    try:
                        vals.append(float(v))  # type: ignore[arg-type]
                    except Exception:
                        continue
                if op == "sum":
                    out[f"{field}_sum"] = sum(vals)
                elif op == "count":
                    out[f"{field}_count"] = len(rows)
                elif op == "avg":
                    out[f"{field}_avg"] = (sum(vals) / len(vals)) if vals else 0
                elif op == "min":
                    out[f"{field}_min"] = min(vals) if vals else None
                elif op == "max":
                    out[f"{field}_max"] = max(vals) if vals else None
            out_rows.append(out)

        return {"rows": out_rows, "summary": {"groups": len(out_rows), "by": by_keys}}


