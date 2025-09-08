from __future__ import annotations

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext
from tests.utils import inject_fastpath_for_llm


@pytest.mark.e2e
def test_invoice_reconciliation_e2e(tmp_path: Path):
    # LLMキー読込
    load_dotenv()

    plan = load_plan(Path("designs/invoice_payment_reconciliation_fixed.yaml"))
    # LLM ブロックを fast-path に（共通ユーティリティ経由で注入）
    inject_fastpath_for_llm(plan)
    reg = BlockRegistry(); reg.load_specs()

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir, default_ui_hitl=False)

    # ヘッドレス実行コンテキスト
    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=tmp_path / "out",
        file_inputs={
            "evidence_zip": Path("tests/data/test_evidence.zip"),
            "input_workbook": Path("tests/data/test_workbook.xlsx"),
        },
        ui_mock_responses={
            "ui.interactive_input": {
                "ui_confirm": {"approved": True, "metadata": {"submitted": True, "mode": "confirm"}}
            }
        },
    )

    results = runner.run(plan, execution_context=exec_ctx)

    # 基本成果物: workbook_updated
    wb = results.get("workbook_updated")
    assert isinstance(wb, dict) and isinstance(wb.get("bytes"), (bytes, bytearray))

    # ログ検証
    plan_dir = runs_dir / plan.id
    files = list(plan_dir.glob("*.jsonl"))
    assert files, "no log file"
    content = files[0].read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in content]
    types = [e.get("type") for e in events]
    assert "start" in types and "finish" in types


