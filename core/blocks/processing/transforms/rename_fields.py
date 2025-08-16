from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class RenameFieldsBlock(ProcessingBlock):
    id = "transforms.rename_fields"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        mapping = inputs.get("rename") or {}
        # allow mapping from first row of rename_rows
        if not mapping and isinstance(inputs.get("rename_rows"), list):
            rr = inputs.get("rename_rows")
            if rr and isinstance(rr[0], dict):
                mapping = dict(rr[0])
        mode = str(inputs.get("mode") or "move").lower()
        drop = inputs.get("drop") or []

        if not isinstance(items, list):
            items = []
        if not isinstance(mapping, dict):
            mapping = {}
        if not isinstance(drop, list):
            drop = []

        def _rename_one(obj: Dict[str, Any]) -> Dict[str, Any]:
            if not isinstance(obj, dict):
                return {}
            out = dict(obj)
            for old, new in mapping.items():
                # case-insensitive match
                real_old = None
                for k in list(out.keys()):
                    if str(k).lower() == str(old).lower():
                        real_old = k
                        break
                if real_old is None:
                    continue
                if mode == "copy":
                    out[str(new)] = out.get(real_old)
                else:  # move
                    out[str(new)] = out.pop(real_old)
            # drop keys
            for key in drop:
                real = None
                for k in list(out.keys()):
                    if str(k).lower() == str(key).lower():
                        real = k
                        break
                if real is not None:
                    out.pop(real, None)
            return out

        out_rows: List[Dict[str, Any]] = []
        for it in items:
            out_rows.append(_rename_one(it))

        return {"rows": out_rows, "summary": {"rows": len(out_rows), "renamed": len(mapping)}}


