from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock


class FromRowsToDataFrameBlock(ProcessingBlock):
    id = "table.from_rows"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        rows = inputs.get("rows")
        # Default: make all columns string dtype unless explicitly overridden
        requested_dtype = inputs.get("dtype") or None
        try:
            import pandas as pd  # type: ignore
        except Exception:
            # pandas 未導入でも壊れないように空を返す（定義に合わせ実装は最小限）
            return {"dataframe": None}

        if not isinstance(rows, list):
            return {"dataframe": pd.DataFrame()}  # type: ignore[name-defined]
        if rows and not isinstance(rows[0], dict):
            try:
                df_nd = pd.DataFrame(rows, dtype=(requested_dtype if requested_dtype is not None else "string"))  # type: ignore[name-defined]
            except Exception:
                df_nd = pd.DataFrame(rows)  # type: ignore[name-defined]
                try:
                    df_nd = df_nd.astype("string")  # type: ignore[assignment]
                except Exception:
                    pass
            return {"dataframe": df_nd}

        try:
            df = pd.DataFrame(rows, dtype=(requested_dtype if requested_dtype is not None else "string"))  # type: ignore[name-defined]
        except Exception:
            df = pd.DataFrame(rows)  # type: ignore[name-defined]
            try:
                df = df.astype("string")  # type: ignore[assignment]
            except Exception:
                pass
        return {"dataframe": df}


