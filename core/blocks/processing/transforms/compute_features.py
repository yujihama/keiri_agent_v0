from __future__ import annotations

from typing import Any, Dict, List
import math

from core.blocks.base import BlockContext, ProcessingBlock


class ComputeFeaturesBlock(ProcessingBlock):
    id = "transforms.compute_features"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        config = inputs.get("config") or {}
        if not isinstance(items, list):
            items = []

        out: List[Dict[str, Any]] = []
        for it in items:
            base = it if isinstance(it, dict) else {"value": it}
            feats: Dict[str, Any] = {}
            # text features
            for spec in (config.get("text") or []):
                if not isinstance(spec, dict):
                    continue
                field = spec.get("field")
                ops = spec.get("ops") or []
                val = None
                for k, v in base.items():
                    if str(k).lower() == str(field).lower():
                        val = v
                        break
                s = str(val) if val is not None else ""
                name = str(spec.get("name") or field or "text")
                for op in ops:
                    op = str(op).lower()
                    if op == "normalize":
                        s = " ".join(s.strip().split()).lower()
                    if op == "ngram":
                        n = int(spec.get("n", 2))
                        feats[f"{name}_ngram_{n}"] = [s[i:i+n] for i in range(max(0, len(s) - n + 1))]
                feats[f"{name}_len"] = len(s)
            # numeric features
            for spec in (config.get("numeric") or []):
                if not isinstance(spec, dict):
                    continue
                field = spec.get("field")
                ops = spec.get("ops") or []
                val = None
                for k, v in base.items():
                    if str(k).lower() == str(field).lower():
                        val = v
                        break
                try:
                    x = float(val) if val is not None else 0.0
                except Exception:
                    x = 0.0
                name = str(spec.get("name") or field or "num")
                for op in ops:
                    op = str(op).lower()
                    if op == "log":
                        feats[f"{name}_log"] = math.log(x + 1e-9)
                    if op == "zscore":
                        # per item not meaningful; just include raw
                        feats[f"{name}_z"] = x
                feats[f"{name}_raw"] = x

            enriched = dict(base)
            enriched["features"] = feats
            out.append(enriched)

        return {"features": out, "summary": {"count": len(out)}}


