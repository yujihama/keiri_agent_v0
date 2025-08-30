from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest
from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext
from tests.utils import has_llm_keys, latest_artifacts_dir


# Ensure .env is loaded before skip evaluation
load_dotenv()


@pytest.mark.llm
@pytest.mark.skipif(not has_llm_keys(), reason="LLM keys not set in environment")
def test_po_policy_llm_embeds_into_excel(tmp_path: Path):
    load_dotenv()

    plan = load_plan(Path("designs/po_policy_compliance.yaml"))
    reg = BlockRegistry(); reg.load_specs()
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs", default_ui_hitl=False)

    out_dir = tmp_path / "out_po_llm"
    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=out_dir,
        file_inputs={
            "po_csv": Path("tests/data/po_policy/po_data.csv"),
        },
        ui_mock_responses={
            "collect_approval": {
                "collected_data": {"approver_id": "cfo", "decision": "approve", "comment": "ok"},
                "approved": True,
                "response": None,
                "metadata": {"submitted": True, "mode": "collect"},
            }
        },
    )

    _ = runner.run(plan, execution_context=exec_ctx)

    # Confirm LLM write node wrote at least one row
    artifacts = latest_artifacts_dir(out_dir, "po_policy_compliance_demo")
    w = json.loads((artifacts / "write_llm_summary_outputs.json").read_text(encoding="utf-8"))
    rows = ((w.get("write_summary") or {}).get("rows_written"))
    assert isinstance(rows, int) and rows > 0, "LLM summary not embedded into Excel (no rows written)"


@pytest.mark.llm
@pytest.mark.skipif(not has_llm_keys(), reason="LLM keys not set in environment")
def test_invoice_dupes_llm_embeds_into_excel(tmp_path: Path):
    load_dotenv()

    plan = load_plan(Path("designs/invoice_duplicate_detection.yaml"))
    reg = BlockRegistry(); reg.load_specs()
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs", default_ui_hitl=False)

    out_dir = tmp_path / "out_inv_llm"
    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=out_dir,
        file_inputs={
            "invoices_csv": Path("tests/data/invoices/invoices.csv"),
        },
    )

    _ = runner.run(plan, execution_context=exec_ctx)

    artifacts = latest_artifacts_dir(out_dir, "invoice_duplicate_detection_demo")
    w = json.loads((artifacts / "write_llm_summary_outputs.json").read_text(encoding="utf-8"))
    rows = ((w.get("write_summary") or {}).get("rows_written"))
    assert isinstance(rows, int) and rows > 0, "LLM summary not embedded into Excel (no rows written)"


