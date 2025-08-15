from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class SchemaDiffBlock(ProcessingBlock):
    id = "data.schema.diff"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        old = inputs.get("schema_old") or {}
        new = inputs.get("schema_new") or {}
        options = inputs.get("options") or {}

        def _norm(s: Any) -> Dict[str, Any]:
            return s if isinstance(s, dict) else {}

        old = _norm(old)
        new = _norm(new)
        diffs: List[Dict[str, Any]] = []

        old_keys = set(old.keys())
        new_keys = set(new.keys())
        for k in sorted(new_keys - old_keys):
            diffs.append({"type": "added", "field": k, "new": new[k]})
        for k in sorted(old_keys - new_keys):
            diffs.append({"type": "removed", "field": k, "old": old[k]})
        for k in sorted(new_keys & old_keys):
            o = old[k]
            n = new[k]
            if o != n:
                # naive structural compare
                diffs.append({"type": "changed", "field": k, "old": o, "new": n})

        # breaking changes heuristic: type narrowing or removed fields
        breaking: List[Dict[str, Any]] = [d for d in diffs if d["type"] in ("removed", "changed")]

        return {"diffs": diffs, "breaking_changes": breaking, "summary": {"count": len(diffs), "breaking": len(breaking)}}


