from __future__ import annotations

from typing import Any, Dict, List, Tuple, Iterable
import os

from core.blocks.base import BlockContext, ProcessingBlock


class PandasDataframeAgentBlock(ProcessingBlock):
    """pandas DataFrame を LLM による Python 実行エージェントで操作するブロック。

    想定ユース: 集計・フィルタ・結合・検証など、与えられた DataFrame 群に対するタスクを
    `instruction`（自然言語指示）で実行します。内部では LangChain の
    `create_pandas_dataframe_agent` を用いた Python 実行（REPL）で処理します。

    入力:
      - dataframes: DataFrame | list[DataFrame] | dict[str, DataFrame]
          pandas の DataFrame を 1つ以上。複数の場合は list か dict で指定。
      - instruction: str
          実施したいタスクの指示文。
      - header_type: str = "single" | "multi"
          カラムヘッダーの構造ヒント。DataFrame 自体に依存するため、
          ここでは MultiIndex を検出した場合の既定動作を制御する目的で使用。
      - flatten_multiindex: bool = true
          MultiIndex カラム検出時に文字列へフラット化するか。推奨: true。
      - flatten_joiner: str = "__"
          フラット化時の結合子。
      - sample_rows: int | None
          行数が多い場合に先頭 N 行へ縮約。None または 0 で無効化。既定: 1000。
      - allow_dangerous_code: bool
          LangChain 側の危険なコード実行許可フラグ。既定: false。
      - verbose: bool
          エージェントの詳細ログ。

    出力:
      - answer: str
          エージェントの最終出力（文字列）。
      - intermediate_steps: object
          LangChain エージェントの中間ステップ（存在すれば）。
      - summary: object
          モデル名、データセット数、各 DataFrame の概要など。

    制約/注意:
      - 非常に大きい DataFrame はトークンと実行コストが高くなるため、`sample_rows` により
        事前に縮約されます（既定 1000 行）。必要に応じて調整してください。
      - MultiIndex カラムはそのままだと LLM のコード生成が失敗しやすいため、既定で
        文字列へフラット化します（`flatten_multiindex=true`）。
      - LLM 実行には OPENAI/AZURE OPENAI の API キーが必須です。
    """

    id = "table.pandas_agent"
    version = "0.1.0"

    def _ensure_llm(self):
        have_llm = bool(os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY"))
        if not have_llm:
            from core.errors import BlockException, BlockError, ErrorCode

            raise BlockException(
                BlockError(
                    code=ErrorCode.CONFIG_MISSING,
                    message="OPENAI/AZURE_OPENAI APIキーが未設定のため、DataFrameエージェントを実行できません",
                    details={"required_env": ["OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"]},
                    hint="環境変数に OPENAI_API_KEY または AZURE_OPENAI_API_KEY を設定してください",
                    recoverable=False,
                )
            )

    @staticmethod
    def _is_dataframe(obj: Any) -> bool:
        try:
            import pandas as pd  # noqa: F401
            from pandas import DataFrame

            return isinstance(obj, DataFrame)
        except Exception:
            # pandas が未導入の場合でも安全に偽を返す
            return False

    @staticmethod
    def _flatten_multiindex_columns_if_needed(df, enable: bool, joiner: str) -> Tuple[Any, bool]:
        """MultiIndex カラムを必要に応じてフラット化して新しい DataFrame を返す。

        戻り値: (df_processed, flattened_performed)
        """

        import pandas as pd

        if not enable:
            return df, False
        if not isinstance(df.columns, pd.MultiIndex):
            return df, False

        # 破壊的変更を避ける
        new_df = df.copy()
        new_columns: List[str] = []
        for idx, tup in enumerate(new_df.columns):
            # None や空白を除外しつつ文字列化
            parts = [str(x) for x in tup if x is not None and str(x) != ""]
            label = joiner.join(parts).strip()
            if not label:
                label = f"col_{idx+1}"
            new_columns.append(label)
        new_df.columns = new_columns
        return new_df, True

    @staticmethod
    def _normalize_dataframes(
        inp: Any,
        header_type: str,
        flatten_multiindex: bool,
        flatten_joiner: str,
        sample_rows: int | None,
    ) -> List[Tuple[str, Any]]:
        """DataFrame 群入力を [(name, df), ...] に正規化し、必要に応じて MultiIndex をフラット化、
        先頭サンプリングを行う。
        """

        import pandas as pd

        def _iter_pairs(x: Any) -> Iterable[Tuple[str, Any]]:
            if PandasDataframeAgentBlock._is_dataframe(x):
                yield ("df1", x)
                return
            if isinstance(x, dict):
                for k, v in x.items():
                    if PandasDataframeAgentBlock._is_dataframe(v):
                        yield (str(k), v)
                return
            if isinstance(x, (list, tuple)):
                for i, v in enumerate(x, start=1):
                    if PandasDataframeAgentBlock._is_dataframe(v):
                        yield (f"df{i}", v)
                return
            # 型不正は無視（後段で未検出ならエラー）

        pairs: List[Tuple[str, Any]] = list(_iter_pairs(inp))
        if not pairs:
            return []

        out_pairs: List[Tuple[str, Any]] = []
        for name, df in pairs:
            # MultiIndex の事前処理方針
            # header_type=="multi" であっても、既定ではフラット化 true とする（LLM の堅牢性向上のため）
            do_flatten = flatten_multiindex
            df_proc, flattened = PandasDataframeAgentBlock._flatten_multiindex_columns_if_needed(
                df, enable=do_flatten, joiner=flatten_joiner
            )

            # サンプリング（負荷/コスト対策）
            if isinstance(sample_rows, int) and sample_rows > 0:
                try:
                    if len(df_proc) > sample_rows:
                        df_proc = df_proc.head(sample_rows).copy()
                except Exception:
                    pass

            # index を単純化（表示/取扱いのブレ低減）
            try:
                if isinstance(df_proc.index, pd.MultiIndex):
                    df_proc = df_proc.reset_index(drop=True)
            except Exception:
                pass

            out_pairs.append((name, df_proc))

        return out_pairs

    def dry_run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # 形だけの応答を返す（外部API呼び出しなし）
        df_inp = inputs.get("dataframes")
        pairs = self._normalize_dataframes(
            df_inp,
            header_type=str(inputs.get("header_type") or "single"),
            flatten_multiindex=bool(inputs.get("flatten_multiindex", True)),
            flatten_joiner=str(inputs.get("flatten_joiner") or "__"),
            sample_rows=int(inputs.get("sample_rows") or 1000),
        )
        return {
            "answer": "",
            "intermediate_steps": [],
            "summary": {
                "num_dataframes": len(pairs),
                "model": os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1",
            },
        }

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_llm()

        instruction_text: str = str(inputs.get("instruction") or "").strip()
        if not instruction_text:
            from core.errors import create_input_error, ErrorCode

            raise create_input_error(
                field="instruction",
                expected_type="non-empty string",
                actual_value=instruction_text,
                code=ErrorCode.INPUT_REQUIRED_MISSING,
            )

        df_inp = inputs.get("dataframes")
        header_type: str = str(inputs.get("header_type") or "single").lower()
        flatten_multiindex: bool = bool(inputs.get("flatten_multiindex", True))
        flatten_joiner: str = str(inputs.get("flatten_joiner") or "__")
        sample_rows_raw = inputs.get("sample_rows")
        try:
            sample_rows: int | None = int(sample_rows_raw) if sample_rows_raw is not None else 1000
        except Exception:
            sample_rows = 1000

        pairs = self._normalize_dataframes(
            df_inp,
            header_type=header_type,
            flatten_multiindex=flatten_multiindex,
            flatten_joiner=flatten_joiner,
            sample_rows=sample_rows,
        )
        if not pairs:
            from core.errors import create_input_error

            raise create_input_error(
                field="dataframes",
                expected_type="DataFrame or list/dict of DataFrame",
                actual_value=type(df_inp).__name__,
            )

        # LLM 準備
        from langchain_openai import ChatOpenAI

        model_name = os.getenv("KEIRI_AGENT_LLM_MODEL") or "gpt-4.1"
        temperature = float(os.getenv("KEIRI_AGENT_LLM_TEMPERATURE", "0"))
        llm = ChatOpenAI(model=model_name, temperature=temperature)

        # pandas agent 準備（古/新 API 併用対応）
        allow_dangerous_code = True
        verbose = True

        # DataFrame のみ取り出し順序を保って渡す
        dfs_ordered = [df for _, df in pairs]

        # create_pandas_dataframe_agent の import 位置は LangChain のバージョンで異なる
        agent_factory = None
        try:
            from langchain_experimental.agents.agent_toolkits import (
                create_pandas_dataframe_agent as _factory,
            )

            agent_factory = _factory
        except Exception:
            try:
                from langchain_experimental.agents import (
                    create_pandas_dataframe_agent as _factory2,
                )

                agent_factory = _factory2
            except Exception:
                try:
                    # さらに古い互換
                    from langchain.agents.agent_toolkits import (
                        create_pandas_dataframe_agent as _factory3,
                    )

                    agent_factory = _factory3
                except Exception as e:
                    from core.errors import wrap_exception, ErrorCode

                    raise wrap_exception(e, ErrorCode.CONFIG_MISSING, inputs)

        # 受け入れ可能なキーワード引数はバージョン差があるため、動的に付与
        agent_kwargs: Dict[str, Any] = {"verbose": verbose}
        # allow_dangerous_code がサポートされていれば渡す
        try:
            agent = agent_factory(llm, dfs_ordered, allow_dangerous_code=True, verbose=True)
        except TypeError:
            agent = agent_factory(llm, dfs_ordered, **agent_kwargs)

        # 実行
        try:
            # invoke 形式（LCEL）
            result = agent.invoke({"input": instruction_text})
            # 典型: {"input":..., "output": str, "intermediate_steps": ...}
            output_text = result.get("output") if isinstance(result, dict) else None
            steps = result.get("intermediate_steps") if isinstance(result, dict) else None
            if output_text is None:
                # run 形式（レガシ）
                output_text = agent.run(instruction_text)
                steps = None
        except Exception as e:
            from core.errors import wrap_exception, ErrorCode

            raise wrap_exception(e, ErrorCode.EXTERNAL_API_ERROR, inputs)

        # サマリー
        datasets_meta: List[Dict[str, Any]] = []
        for name, df in pairs:
            try:
                datasets_meta.append(
                    {
                        "name": name,
                        "rows": int(getattr(df, "shape", (0, 0))[0]),
                        "cols": int(getattr(df, "shape", (0, 0))[1]),
                        "columns": [str(c) for c in getattr(df, "columns", [])][:50],
                    }
                )
            except Exception:
                datasets_meta.append({"name": name})

        summary = {
            "model": model_name,
            "temperature": temperature,
            "num_dataframes": len(pairs),
            "header_type": header_type,
            "flatten_multiindex": flatten_multiindex,
            "sample_rows": sample_rows,
            "datasets": datasets_meta,
        }

        return {
            "answer": output_text if isinstance(output_text, str) else str(output_text),
            "intermediate_steps": steps,
            "summary": summary,
        }


