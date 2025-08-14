from __future__ import annotations

from typing import Any, Dict, List, Sequence

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import BlockException, BlockError, ErrorCode, create_input_error


class TablePivotBlock(ProcessingBlock):
    """行配列/DataFrame からピボット集計（縦横変換）を行うブロック。

    入力:
      - dataframe: pandas.DataFrame | None
      - rows: list[dict] | None
        dataframe が無い場合に行配列から DataFrame を組み立てる
      - index: str | list[str]
      - columns: str | list[str]
      - values: str | list[str] | None
      - aggfunc: str | list[str] | dict[str,str]（sum/mean/count/min/max/nunique/first/last など）
      - fill_value: Any | None
      - dropna: bool = True
      - sort: bool = True
      - flatten_multiindex: bool = True
      - flatten_joiner: str = "__"

    出力:
      - dataframe: pandas.DataFrame
      - rows: list[dict]
      - summary: { rows, cols, columns[] }
    """

    id = "table.pivot"
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
            # list[list|tuple] の単純ケースも受容
            return pd.DataFrame(rows)
        return pd.DataFrame(rows)

    @staticmethod
    def _flatten_columns_if_needed(df, enable: bool, joiner: str):
        if not enable:
            return df
        try:
            import pandas as pd

            if isinstance(df.columns, pd.MultiIndex):
                new_df = df.copy()
                new_cols: List[str] = []
                for idx, tup in enumerate(new_df.columns):
                    parts = [str(x) for x in tup if x is not None and str(x) != ""]
                    label = joiner.join(parts).strip()
                    if not label:
                        label = f"col_{idx+1}"
                    new_cols.append(label)
                new_df.columns = new_cols
                return new_df
        except Exception:
            pass
        return df

    @staticmethod
    def _normalize_labels(x: Any) -> List[str]:
        try:
            return [str(c) for c in x]
        except Exception:
            return [str(x)]

    def dry_run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # 形だけ返す
        return {"dataframe": None, "rows": [], "summary": {"rows": 0, "cols": 0, "columns": []}}

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_pandas()
        import pandas as pd  # type: ignore

        # 入力取得/検証
        index = inputs.get("index")
        columns = inputs.get("columns")
        if index is None or columns is None:
            raise create_input_error("index|columns", "str | list[str]", {"index": index, "columns": columns})
        values = inputs.get("values")
        aggfunc = inputs.get("aggfunc") or "sum"
        fill_value = inputs.get("fill_value")
        dropna = bool(inputs.get("dropna", True))
        sort = bool(inputs.get("sort", True))
        flatten_multiindex = bool(inputs.get("flatten_multiindex", True))
        flatten_joiner = str(inputs.get("flatten_joiner") or "__")

        # pandas の pivot_table へ受け渡し可能な形式へ
        def _to_list(x: Any) -> List[str]:
            if x is None:
                return []
            if isinstance(x, (list, tuple, set)):
                return [str(v) for v in x]
            return [str(x)]

        idx_list = _to_list(index)
        col_list = _to_list(columns)
        val_arg: Any
        if values is None:
            val_arg = None
        else:
            v_list = _to_list(values)
            val_arg = v_list if len(v_list) > 1 else v_list[0]

        # aggfunc の文字列/配列/辞書をそのまま許可
        agg_arg = aggfunc

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
            pivoted = pd.pivot_table(
                df_in,
                index=idx_list if len(idx_list) > 1 else idx_list[0],
                columns=col_list if len(col_list) > 1 else col_list[0],
                values=val_arg,
                aggfunc=agg_arg,
                fill_value=fill_value,
                dropna=dropna,
                sort=sort,
            )
        except Exception as e:
            from core.errors import wrap_exception

            raise wrap_exception(e, ErrorCode.BLOCK_EXECUTION_FAILED, inputs)

        # index を列へ戻し、MultiIndex カラムは必要に応じてフラット化
        try:
            out_df = pivoted.reset_index()
        except Exception:
            out_df = pivoted
        out_df = self._flatten_columns_if_needed(out_df, flatten_multiindex, flatten_joiner)

        # 行配列へ変換
        try:
            rows_out: List[Dict[str, Any]] = out_df.to_dict(orient="records")  # type: ignore[attr-defined]
        except Exception:
            rows_out = []

        summary = {
            "rows": int(getattr(out_df, "shape", (0, 0))[0]),
            "cols": int(getattr(out_df, "shape", (0, 0))[1]),
            "columns": self._normalize_labels(getattr(out_df, "columns", [])),
        }

        return {"dataframe": out_df, "rows": rows_out, "summary": summary}


