from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class FlattenItemsBlock(ProcessingBlock):
    id = "transforms.flatten_items"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten list of results into a single items list.

        Inputs
        ------
        - results_list: list of { matched: bool, items: [ {file, count, sum} ] } or list of wrapper objects
          Optionally accepts list of { results: { ... } } (as produced by ai.invoice_payment_match via foreach)

        Outputs
        -------
        - items: list[dict]
        """

        src = inputs.get("results_list")
        items: List[Dict[str, Any]] = []

        def _extract_items(obj: Any) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            # 配列なら各要素を再帰的に抽出
            if isinstance(obj, list):
                for it in obj:
                    out.extend(_extract_items(it))
                return out
            # dictでなければ空
            if not isinstance(obj, dict):
                return out
            # 1) direct results
            if isinstance(obj.get("items"), list):
                for it in obj["items"]:
                    if isinstance(it, dict):
                        out.append(dict(it))
                return out
            # 2) wrapped under known keys: results or *_results
            if isinstance(obj.get("results"), dict):
                return _extract_items(obj["results"])
            for k, v in obj.items():
                try:
                    if isinstance(k, str) and k.endswith("_results") and isinstance(v, dict):
                        return _extract_items(v)
                except Exception:
                    continue
            return out

        # 入口が何であっても再帰処理
        items.extend(_extract_items(src))

        return {"items": items}


