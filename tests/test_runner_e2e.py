from __future__ import annotations

import json
import base64
from pathlib import Path

from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def _encode_for_json(obj):
    if isinstance(obj, (bytes, bytearray)):
        return {"__type": "b64bytes", "data": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, dict):
        return {k: _encode_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode_for_json(v) for v in obj]
    return obj


def _write_ui_state(runner: PlanRunner, plan_id: str, run_id: str, ui_outputs: dict) -> None:
    state_dir = runner.runs_dir / plan_id
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / f"{run_id}.state.json"
    state = {"ui_outputs": _encode_for_json(ui_outputs), "pending_ui": None}
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def test_invoice_reconciliation_e2e(tmp_path: Path):
    # LLMキー読込
    load_dotenv()

    plan = load_plan(Path("designs/invoice_payment_reconciliation_fixed.yaml"))
    reg = BlockRegistry(); reg.load_specs()

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir, default_ui_hitl=True)

    # UI事前投入: ZIPとExcel
    zip_bytes = Path("tests/data/test_evidence.zip").read_bytes()
    wb_bytes = Path("tests/data/test_workbook.xlsx").read_bytes()
    run_id = "invoice_e2e"
    ui = {
        "ui_file_input": {
            "collected_data": {
                "evidence_zip": zip_bytes,
                "input_workbook": wb_bytes,
            }
        },
        "ui_confirm": {"approved": True},
    }
    _write_ui_state(runner, plan.id, run_id, ui)

    results = runner.run(plan, resume_run_id=run_id)

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


