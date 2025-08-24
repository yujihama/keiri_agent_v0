from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, date

from core.blocks.base import BlockContext, ProcessingBlock


class CoerceValuesBlock(ProcessingBlock):
    id = "transforms.coerce_values"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        specs = inputs.get("specs") or []
        if not isinstance(items, list):
            items = []
        if not isinstance(specs, list):
            specs = []

        def _ci_get_key(d: Dict[str, Any], key: str) -> str | None:
            for k in d.keys():
                if str(k).lower() == str(key).lower():
                    return k
            return None

        def _try_number(val: Any) -> Any:
            if val is None:
                return None
            # allow numeric or numeric-like strings (commas allowed)
            try:
                if isinstance(val, (int, float)):
                    return val
                s = str(val).strip().replace(",", "")
                if s == "":
                    return None
                # prefer int when exact
                if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                    return int(s)
                return float(s)
            except Exception:
                return None

        def _try_bool(val: Any) -> Any:
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return val != 0
            if isinstance(val, str):
                s = val.strip().lower()
                if s in {"true", "1", "yes", "y"}:
                    return True
                if s in {"false", "0", "no", "n"}:
                    return False
            return None

        def _try_date(val: Any, fmts: List[str] | None, want_dt: bool) -> Any:
            if val is None:
                return None
            if isinstance(val, (datetime, date)):
                return val if want_dt else (val if isinstance(val, date) else val.date())
            if not isinstance(val, str):
                return None
            s = val.strip()
            if s == "":
                return None
            formats = list(fmts or []) + [
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S",
                "%Y/%m/%d %H:%M:%S",
            ]
            for f in formats:
                try:
                    dt = datetime.strptime(s, f)
                    return dt if want_dt else dt.date()
                except Exception:
                    continue
            return None

        replaced = 0
        out_rows: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            row = dict(it)
            for sp in specs:
                if not isinstance(sp, dict):
                    continue
                field = sp.get("field")
                typ = str(sp.get("type") or "string").lower()
                fmts = sp.get("formats") if isinstance(sp.get("formats"), list) else None
                if not isinstance(field, str) or not field:
                    continue
                real_key = _ci_get_key(row, field)
                if real_key is None:
                    continue
                val = row.get(real_key)
                new_val = None
                if typ in {"number", "int", "float"}:
                    new_val = _try_number(val)
                elif typ == "boolean":
                    new_val = _try_bool(val)
                elif typ in {"date", "datetime"}:
                    new_val = _try_date(val, fmts, want_dt=(typ == "datetime"))
                elif typ == "string":
                    try:
                        new_val = "" if val is None else str(val)
                    except Exception:
                        new_val = ""
                else:
                    # unknown -> skip
                    continue
                if new_val is not None and new_val != val:
                    row[real_key] = new_val
                    replaced += 1
            out_rows.append(row)

        # Provide convenience: first object (when input is a single object list)
        first_obj = out_rows[0] if out_rows else None
        return {
            "rows": out_rows,
            "first": first_obj,
            "summary": {"input": len(items), "converted": replaced, "specs": len(specs)},
        }


