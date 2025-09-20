from __future__ import annotations

import json
from pathlib import Path

import pytest
from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext
# 共通ユーティリティ
from tests.utils import inject_fastpath_for_llm, latest_artifacts_dir


@pytest.mark.e2e
def test_po_policy_compliance_headless(tmp_path: Path):
    load_dotenv()

    plan_path = Path("designs/po_policy_compliance.yaml")
    plan = load_plan(plan_path)
    inject_fastpath_for_llm(
        plan,
        node_outputs={
            "llm_violations_summary": {
                "summary": {"total_items": 4, "violations": 2, "key_points": ""},
                "violations_brief": [],
            }
        },
    )

    reg = BlockRegistry(); reg.load_specs()
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs", default_ui_hitl=False)

    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=tmp_path / "out_po",
        file_inputs={
            "po_csv": Path("tests/data/po_policy/po_data.csv"),
        },
        ui_mock_responses={
            # Ensure authorized approver in headless mode
            "collect_approval": {
                "collected_data": {"approver_id": "cfo", "decision": "approve", "comment": "ok"},
                "approved": True,
                "response": None,
                "metadata": {"submitted": True, "mode": "collect"},
            }
        },
    )

    results = runner.run(plan, execution_context=exec_ctx)

    # Expect violations and summary to match deterministic test data
    violations = results.get("violations")
    summary = results.get("summary")
    assert isinstance(violations, list) and isinstance(summary, dict)
    assert summary.get("items") == 4
    rule_ids = {v.get("rule_id") for v in violations if isinstance(v, dict)}
    assert {"amount_threshold", "po_unique"}.issubset(rule_ids)

    # Approval should be computed and returned
    assert results.get("approved") is True

    # Excel report should be generated
    report = results.get("report_wb") or results.get("workbook_updated")
    assert isinstance(report, dict) and isinstance(report.get("bytes"), (bytes, bytearray))


@pytest.mark.e2e
def test_invoice_duplicate_detection_headless(tmp_path: Path):
    load_dotenv()

    plan_path = Path("designs/invoice_duplicate_detection.yaml")
    plan = load_plan(plan_path)
    inject_fastpath_for_llm(
        plan,
        node_outputs={
            "llm_summarize": {
                "summary": {"total_exact": 1, "total_candidates": 1, "notes": ""},
                "pairs": [],
            }
        },
    )

    reg = BlockRegistry(); reg.load_specs()
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs", default_ui_hitl=False)

    out_dir = tmp_path / "out_inv"
    exec_ctx = ExecutionContext(
        headless_mode=True,
        output_dir=out_dir,
        file_inputs={
            "invoices_csv": Path("tests/data/invoices/invoices.csv"),
        },
    )

    results = runner.run(plan, execution_context=exec_ctx)

    # Excel report should be generated
    report = results.get("report_wb") or results.get("workbook_updated")
    assert isinstance(report, dict) and isinstance(report.get("bytes"), (bytes, bytearray))

    # Validate exact match presence for INV-1001 (self or duplicate pair exists)
    artifacts = latest_artifacts_dir(out_dir, "invoice_duplicate_detection_demo")
    exact_path = artifacts / "exact_dupes_outputs.json"
    assert exact_path.exists(), f"missing artifact: {exact_path}"
    data = json.loads(exact_path.read_text(encoding="utf-8"))
    matches = data.get("matches") or []
    assert isinstance(matches, list) and matches, "no exact matches"
    found_inv1001 = any(
        isinstance(m, dict)
        and isinstance(m.get("left"), dict)
        and isinstance(m.get("right"), dict)
        and m["left"].get("invoice_no") == "INV-1001"
        and m["right"].get("invoice_no") == "INV-1001"
        and m["left"].get("vendor_id") == "V001"
        and m["right"].get("vendor_id") == "V001"
        for m in matches
    )
    assert found_inv1001, "expected INV-1001 exact duplicate/self-match not found"





