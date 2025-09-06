from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class AttachContextBlock(ProcessingBlock):
    id = "transforms.attach_context"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        context = inputs.get("context") or {}
        as_key = inputs.get("as")  # optional: wrap context under a specific key

        if not isinstance(items, list):
            items = []
        if not isinstance(context, dict):
            context = {}

        out: List[Dict[str, Any]] = []
        for it in items:
            base = dict(it) if isinstance(it, dict) else {"value": it}
            if as_key:
                base[str(as_key)] = context
            else:
                # merge top-level (do not overwrite existing keys)
                for k, v in context.items():
                    if k not in base:
                        base[k] = v
            out.append(base)
        return {"items": out, "summary": {"count": len(out)}}


