from __future__ import annotations

from typing import Any, Dict, List

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode, create_input_error


class TableUnpivotBlock(ProcessingBlock):
    """ワイド形式を縦持ちへ変換（melt）するブロック。

    入力:
      - dataframe: pandas.DataFrame | None
      - rows: list[dict] | None
      - id_vars: str | list[str] | None  不変列
      - value_vars: str | list[str] | None  展開対象列（未指定時は id_vars 以外）
      - var_name: str = "variable"  生成する列名（元カラム名）
      - value_name: str = "value"    生成する列名（値）
      - ignore_index: bool = True

    出力:
      - dataframe: pandas.DataFrame
      - rows: list[dict]
      - summary: { rows, cols, columns[] }
    """

    id = "table.unpivot"
    version = "0.1.0"

    @staticmethod
    def _ensure_pandas() -> None:
        try:
            import pandas  # noqa: F401
        except Exception as e:
            raise BlockException(
                BlockError(
                    code=ErrorCode.DEPENDENCY_NOT_FOUND,
                    message="pandas が必要です。requirements を確認してください",
                    details={"missing": "pandas"},
                    hint="requirements.txt に pandas が含まれているか、環境にインストールされているか確認してください",
                    recoverable=False,
                )
            ) from e

    @staticmethod
    def _to_dataframe(inputs: Dict[str, Any]):
        import pandas as pd  # type: ignore

        df = inputs.get("dataframe")
        if df is not None:
            return df
        rows = inputs.get("rows")
        if rows is None:
            raise create_input_error("rows|dataframe", "rows(list[dict]) or pandas.DataFrame", None)
        if not isinstance(rows, list):
            raise create_input_error("rows", "list[dict]", rows)
        if rows and not isinstance(rows[0], dict):
            return pd.DataFrame(rows)
        return pd.DataFrame(rows)

    @staticmethod
    def _to_list(x: Any) -> List[str] | None:
        if x is None:
            return None
        if isinstance(x, (list, tuple, set)):
            return [str(v) for v in x]
        return [str(x)]

    @staticmethod
    def _normalize_labels(x: Any) -> List[str]:
        try:
            return [str(c) for c in x]
        except Exception:
            return [str(x)]

    def dry_run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        return {"dataframe": None, "rows": [], "summary": {"rows": 0, "cols": 0, "columns": []}}

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_pandas()
        import pandas as pd  # type: ignore

        id_vars = self._to_list(inputs.get("id_vars"))
        value_vars = self._to_list(inputs.get("value_vars"))
        var_name = str(inputs.get("var_name") or "variable")
        value_name = str(inputs.get("value_name") or "value")
        ignore_index = bool(inputs.get("ignore_index", True))

        try:
            df_in = self._to_dataframe(inputs)
        except BlockException:
            raise
        except Exception as e:
            raise BlockException(
                BlockError(
                    code=ErrorCode.INPUT_VALIDATION_FAILED,
                    message="DataFrame 変換に失敗しました",
                    details={"reason": str(e)},
                    input_snapshot={k: (type(v).__name__) for k, v in inputs.items()},
                    recoverable=False,
                )
            ) from e

        try:
            melted = pd.melt(
                df_in,
                id_vars=id_vars,
                value_vars=value_vars,
                var_name=var_name,
                value_name=value_name,
                ignore_index=ignore_index,
            )
        except Exception as e:
            from core.errors import wrap_exception

            raise wrap_exception(e, ErrorCode.BLOCK_EXECUTION_FAILED, inputs)

        try:
            rows_out = melted.to_dict(orient="records")  # type: ignore[attr-defined]
        except Exception:
            rows_out = []

        summary = {
            "rows": int(getattr(melted, "shape", (0, 0))[0]),
            "cols": int(getattr(melted, "shape", (0, 0))[1]),
            "columns": self._normalize_labels(getattr(melted, "columns", [])),
        }

        return {"dataframe": melted, "rows": rows_out, "summary": summary}


