from __future__ import annotations

from typing import Any, Dict, List, Set

from core.blocks.base import BlockContext, ProcessingBlock


class PolicyValidateBlock(ProcessingBlock):
    id = "policy.validate"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        validation_context = inputs.get("validation_context") or {}
        rules = inputs.get("rules") or []
        options = inputs.get("options") or {}

        items = validation_context.get("items") if isinstance(validation_context, dict) else None
        if not isinstance(items, list):
            items = []
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

        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            ref = it.get("id") or it.get("_id") or idx
            for rule in rules:  # type: ignore[assignment]
                if not isinstance(rule, dict):
                    continue
                rid = rule.get("id") or f"r{idx}"
                rtype = str(rule.get("type", "")).lower()

                if rtype == "threshold":
                    field = rule.get("field")
                    op = str(rule.get("op", "lte")).lower()
                    val = rule.get("value")
                    left = _get(it, str(field))
                    try:
                        lf = float(left)  # type: ignore[arg-type]
                        rv = float(val)  # type: ignore[arg-type]
                    except Exception:
                        continue
                    ok = {
                        "lt": lf < rv,
                        "lte": lf <= rv,
                        "gt": lf > rv,
                        "gte": lf >= rv,
                        "eq": lf == rv,
                        "ne": lf != rv,
                    }.get(op, True)
                    if not ok:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"field": field, "left": left, "op": op, "value": val}})
                elif rtype == "required":
                    fields = rule.get("fields") or ([rule.get("field")] if rule.get("field") else [])
                    missing = [f for f in fields if _get(it, f) in (None, "")]
                    if missing:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"missing": missing}})
                elif rtype == "unique":
                    field = rule.get("field")
                    val = _get(it, str(field))
                    bucket = unique_track.setdefault(str(field), set())
                    if val in bucket:
                        violations.append({"rule_id": rid, "item_ref": ref, "details": {"field": field, "duplicate": val}})
                    else:
                        bucket.add(val)

        passed = len(violations) == 0
        return {"validation_context": validation_context, "violations": violations, "passed": bool(passed)}