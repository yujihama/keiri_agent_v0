from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class FromRowsToDataFrameBlock(ProcessingBlock):
    id = "table.from_rows"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        rows = inputs.get("rows")
        dtype = inputs.get("dtype") or None
        try:
            import pandas as pd  # type: ignore
        except Exception:
            # pandas 未導入でも壊れないように空を返す（定義に合わせ実装は最小限）
            return {"dataframe": None}

        if not isinstance(rows, list):
            return {"dataframe": pd.DataFrame()}  # type: ignore[name-defined]
        if rows and not isinstance(rows[0], dict):
            return {"dataframe": pd.DataFrame(rows)}  # type: ignore[name-defined]

        try:
            df = pd.DataFrame(rows, dtype=None if dtype is None else dtype)  # type: ignore[name-defined]
        except Exception:
            df = pd.DataFrame(rows)  # type: ignore[name-defined]
        return {"dataframe": df}


