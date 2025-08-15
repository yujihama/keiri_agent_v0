from __future__ import annotations

from typing import Any, Dict, List, Set
import re

from core.blocks.base import BlockContext, ProcessingBlock


class PolicyEnforceBlock(ProcessingBlock):
    """Evaluate simple declarative policies against a list of items.

    Supported rule types:
    - threshold: { id, type: 'threshold', field, op: 'lt'|'lte'|'gt'|'gte'|'eq'|'ne', value }
    - required: { id, type: 'required', fields: [..] } or { id, type: 'required', field }
    - forbidden: { id, type: 'forbidden', condition: { field, operator, value } }
    - regex: { id, type: 'regex', field, pattern }
    - unique: { id, type: 'unique', field }
    """

    id = "control.policy_enforce"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        policy = inputs.get("policy") or {}
        options = inputs.get("options") or {}
        strict = str(options.get("mode", "strict")).lower() == "strict"

        rules = policy.get("rules") if isinstance(policy, dict) else None
        allow = set(policy.get("exceptions", {}).get("allow_list", [])) if isinstance(policy, dict) else set()

        violations: List[Dict[str, Any]] = []
        if not isinstance(items, list):
            items = []
        if not isinstance(rules, list):
            rules = []

        def _get(obj: Dict[str, Any], key: str):
            if not isinstance(obj, dict):
                return None
            # case insensitive key access
            for k, v in obj.items():
                if str(k).lower() == str(key).lower():
                    return v
            return None

        # unique tracker per field
        unique_seen: Dict[str, Set[Any]] = {}

        for idx, it in enumerate(items):
            if not isinstance(it, dict):
                continue
            item_ref = it.get("id") or it.get("_id") or idx
            # item-scoped allow token candidates
            allow_token_candidates = [
                f"id:{item_ref}",
                *(f"{k}:{_get(it, k)}" for k in ("vendor_id", "po_no", "invoice_no") if _get(it, k) is not None),
            ]
            allow_hit = any(tok in allow for tok in allow_token_candidates)

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
                    if not ok and not allow_hit:
                        violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"field": field, "left": left, "op": op, "value": val}})
                elif rtype == "required":
                    fields = rule.get("fields") or ([rule.get("field")] if rule.get("field") else [])
                    missing = [f for f in fields if _get(it, f) in (None, "")]
                    if missing and not allow_hit:
                        violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"missing": missing}})
                elif rtype == "forbidden":
                    cond = rule.get("condition") or {}
                    f = cond.get("field")
                    op = str(cond.get("operator", "eq")).lower()
                    val = cond.get("value")
                    left = _get(it, str(f))
                    hit = False
                    try:
                        if op == "eq":
                            hit = left == val
                        elif op == "in":
                            hit = left in val  # type: ignore[operator]
                        elif op == "contains":
                            hit = str(val) in str(left)
                    except Exception:
                        hit = False
                    if hit and not allow_hit:
                        violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"field": f, "operator": op, "value": val}})
                elif rtype == "regex":
                    field = rule.get("field")
                    pattern = rule.get("pattern", ".*")
                    text = _get(it, str(field))
                    if text is None:
                        if not allow_hit:
                            violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"field": field, "reason": "missing"}})
                        continue
                    try:
                        if not re.search(pattern, str(text)) and not allow_hit:
                            violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"field": field, "pattern": pattern}})
                    except Exception:
                        continue
                elif rtype == "unique":
                    field = rule.get("field")
                    val = _get(it, str(field))
                    bucket = unique_seen.setdefault(str(field), set())
                    if val in bucket and not allow_hit:
                        violations.append({"rule_id": rid, "item_ref": item_ref, "details": {"field": field, "duplicate": val}})
                    else:
                        bucket.add(val)

        passed = len(violations) == 0
        if not strict and violations:
            # lenient mode: pass but include violations summary
            passed = True

        return {
            "violations": violations,
            "passed": bool(passed),
            "summary": {"items": len(items), "rules": len(rules), "violations": len(violations)},
        }


