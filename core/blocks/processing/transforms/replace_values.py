from __future__ import annotations

from typing import Any, Dict, List
import re

from core.blocks.base import BlockContext, ProcessingBlock


class ReplaceValuesBlock(ProcessingBlock):
    id = "transforms.replace_values"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        rules = inputs.get("rules") or []

        if not isinstance(items, list):
            items = []
        if not isinstance(rules, list):
            rules = []

        # Normalize rules
        norm_rules: List[Dict[str, Any]] = []
        for r in rules:
            if not isinstance(r, dict):
                continue
            field = r.get("field")
            if not isinstance(field, str) or not field.strip():
                continue
            mappings = r.get("mappings") or []
            if not isinstance(mappings, list) or not mappings:
                continue
            match = str(r.get("match") or "equals").lower()
            case_insensitive = bool(r.get("case_insensitive", True))

            norm_maps: List[Dict[str, str]] = []
            for m in mappings:
                if isinstance(m, dict):
                    frm = m.get("from")
                    to = m.get("to")
                    if isinstance(frm, str) and to is not None:
                        norm_maps.append({"from": frm, "to": to})
            if not norm_maps:
                continue

            norm_rules.append(
                {
                    "field": field,
                    "mappings": norm_maps,
                    "match": match,
                    "case_insensitive": case_insensitive,
                }
            )

        def _ci_get(obj: Dict[str, Any], key: str) -> Any:
            if not isinstance(obj, dict):
                return None
            for k, v in obj.items():
                if str(k).lower() == str(key).lower():
                    return v
            return None

        def _ci_set(obj: Dict[str, Any], key: str, value: Any) -> None:
            if not isinstance(obj, dict):
                return
            real = None
            for k in obj.keys():
                if str(k).lower() == str(key).lower():
                    real = k
                    break
            if real is None:
                real = key
            obj[real] = value

        replaced_count = 0
        out_rows: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            row = dict(it)
            for r in norm_rules:
                field = r["field"]
                mode = r["match"]
                ci = r["case_insensitive"]
                src_val = _ci_get(row, field)

                # Convert to string for comparison when needed; preserve None
                s = None
                if src_val is not None:
                    s = str(src_val)
                    if ci:
                        s_cmp = s.lower()
                    else:
                        s_cmp = s
                else:
                    s_cmp = None

                for mp in r["mappings"]:
                    frm = mp["from"]
                    to = mp["to"]
                    if src_val is None:
                        continue
                    f_cmp = frm.lower() if ci else frm

                    matched = False
                    if mode == "equals":
                        matched = s_cmp == f_cmp
                    elif mode == "contains":
                        try:
                            matched = f_cmp in s_cmp  # type: ignore[operator]
                        except Exception:
                            matched = False
                    elif mode == "regex":
                        flags = re.IGNORECASE if ci else 0
                        try:
                            matched = re.search(frm, s, flags) is not None
                        except re.error:
                            matched = False
                    else:
                        # Unknown mode -> skip
                        matched = False

                    if matched:
                        _ci_set(row, field, to)
                        replaced_count += 1
                        break  # first match wins per rule

            out_rows.append(row)

        return {
            "rows": out_rows,
            "summary": {"input": len(items), "replaced": replaced_count, "rules": len(norm_rules)},
        }


