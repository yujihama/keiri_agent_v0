from __future__ import annotations

import os
import pytest

from core.blocks.base import BlockContext


CTX = BlockContext(run_id="unit")


def test_df_agent_dry_run_summary_with_multiindex():
    pd = pytest.importorskip("pandas")
    # Import inside test to avoid hard dependency when langchain stack is missing
    mod = pytest.importorskip("core.blocks.processing.table.df_agent")
    PandasDataframeAgentBlock = getattr(mod, "PandasDataframeAgentBlock")

    blk = PandasDataframeAgentBlock()
    arrays = [["A", "A", "B"], ["x", "y", "z"]]
    tuples = list(zip(*arrays))
    idx = pd.MultiIndex.from_tuples(tuples, names=["lvl1", "lvl2"])
    df = pd.DataFrame([[1, 2, 3]], columns=idx)
    out = blk.dry_run({
        "dataframes": df,
        "header_type": "multi",
        "flatten_multiindex": True,
        "sample_rows": 1,
    })
    assert out["summary"]["num_dataframes"] == 1


def test_df_agent_run_raises_without_llm_keys(monkeypatch: pytest.MonkeyPatch):
    pd = pytest.importorskip("pandas")
    mod = pytest.importorskip("core.blocks.processing.table.df_agent")
    PandasDataframeAgentBlock = getattr(mod, "PandasDataframeAgentBlock")

    blk = PandasDataframeAgentBlock()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    with pytest.raises(Exception):
        blk.run(CTX, {"dataframes": pd.DataFrame({"a": [1]}), "instruction": "sum a"})

