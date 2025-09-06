from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class SelectByIndicesBlock(ProcessingBlock):
    id = "transforms.select_by_indices"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        indices = inputs.get("indices") or []
        if not isinstance(items, list):
            items = []
        if not isinstance(indices, list):
            indices = []

        out: List[Dict[str, Any]] = []
        for i in indices:
            try:
                j = int(i)
            except Exception:
                continue
            if 0 <= j < len(items):
                it = items[j]
                out.append(it if isinstance(it, dict) else {"value": it})
        return {"rows": out, "summary": {"selected": len(out), "total": len(items)}}


