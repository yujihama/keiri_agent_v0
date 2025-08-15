from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime, timezone
import hashlib

from core.blocks.base import BlockContext, ProcessingBlock


class ProvenanceCaptureBlock(ProcessingBlock):
    id = "data.provenance.capture"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        context = inputs.get("context") or {}
        if not isinstance(items, list):
            items = []

        ts = datetime.now(timezone.utc).isoformat()
        run_id = getattr(ctx, "run_id", "")
        node_id = ctx.vars.get("__node_id") if isinstance(ctx.vars, dict) else None

        out: List[Dict[str, Any]] = []
        for i, it in enumerate(items):
            base = it if isinstance(it, dict) else {"value": it}
            # compute a lightweight hash for traceability
            try:
                h = hashlib.sha256(str(base).encode("utf-8")).hexdigest()[:16]
            except Exception:
                h = ""
            pv = {
                "captured_at": ts,
                "run_id": run_id,
                "node_id": node_id,
                "hash": h,
            }
            if isinstance(context, dict):
                pv.update({k: v for k, v in context.items()})
            enriched = dict(base)
            enriched["__provenance__"] = pv
            out.append(enriched)

        return {"items_with_provenance": out, "summary": {"count": len(out)}}


