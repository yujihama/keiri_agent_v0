from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class FilterKeywordBlock(ProcessingBlock):
    id = "transforms.filter_keyword"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        fields = inputs.get("fields") or []
        keywords = inputs.get("keywords") or []
        case_insensitive = bool(inputs.get("case_insensitive", True))

        def get_by_path(obj: Any, path: str) -> Any:
            cur = obj
            for seg in str(path).split("."):
                s = seg.strip()
                if not s:
                    return None
                if isinstance(cur, dict):
                    # case-insensitive field match
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

        fields = [f for f in fields if isinstance(f, str) and f]
        kw = [str(k) for k in keywords if isinstance(k, (str, int, float))]
        if case_insensitive:
            kw = [k.lower() for k in kw]

        filtered: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                excluded.append(it)  # type: ignore[arg-type]
                continue
            hit = False
            for f in fields:
                val = get_by_path(it, f)
                if val is None:
                    continue
                text = str(val)
                if case_insensitive:
                    text = text.lower()
                for k in kw:
                    if k in text:
                        hit = True
                        break
                if hit:
                    break
            (filtered if hit else excluded).append(it)

        return {
            "filtered": filtered,
            "excluded": excluded,
            "summary": {"input": len(items) if isinstance(items, list) else 0, "filtered": len(filtered), "excluded": len(excluded)},
        }


