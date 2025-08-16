from __future__ import annotations

from typing import Any, Dict, List, Set

from core.blocks.base import BlockContext, ProcessingBlock


class ControlValidationBlock(ProcessingBlock):
    id = "control.validation"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        dataset = inputs.get("dataset") or []
        rules = inputs.get("rules") or []
        options = inputs.get("options") or {}

        if not isinstance(dataset, list):
            dataset = []
        if not isinstance(rules, list):
            rules = []

        violations: List[Dict[str, Any]] = []
        unique_track: Dict[str, Set[Any]] = {}

        def _get(obj: Dict[str, Any], key: str):
            if not isinstance(obj, dict):
                return None
            for k, v in obj.items():
                if str(k).lower() == str(key).lower():
                    return v
            return None

        for idx, it in enumerate(dataset):
            if not isinstance(it, dict):
                continue
            ref = it.get("id") or it.get("_id") or idx
            for rule in rules:  # type: ignore[assignment]
                if not isinstance(rule, dict):
                    continue
                rid = rule.get("id") or f"r{idx}"
                rtype = str(rule.get("type", "")).lower()
                field = rule.get("field")
                if rtype == "required":
                    fields = rule.get("fields") or ([field] if field else [])
                    missing = [f for f in fields if _get(it, f) in (None, "")]
                    if missing:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"missing": missing}})
                elif rtype == "range":
                    v = _get(it, str(field))
                    try:
                        val = float(v)  # type: ignore[arg-type]
                        minv = float(rule.get("min")) if rule.get("min") is not None else None  # type: ignore[arg-type]
                        maxv = float(rule.get("max")) if rule.get("max") is not None else None  # type: ignore[arg-type]
                    except Exception:
                        continue
                    if minv is not None and val < minv:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"field": field, "min": minv, "actual": val}})
                    if maxv is not None and val > maxv:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"field": field, "max": maxv, "actual": val}})
                elif rtype == "unique":
                    val = _get(it, str(field))
                    b = unique_track.setdefault(str(field), set())
                    if val in b:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"field": field, "duplicate": val}})
                    else:
                        b.add(val)
        
        return {"violations": violations, "summary": {"items": len(dataset), "rules": len(rules), "violations": len(violations)}}