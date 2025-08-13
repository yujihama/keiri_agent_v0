from __future__ import annotations

import json
import base64
from pathlib import Path

from dotenv import load_dotenv  # type: ignore
from openpyxl import load_workbook

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


def test_retirement_benefit_q1_2025_e2e(tmp_path: Path):
    # .env からAPIキー等を読み込み（LLM呼び出し用）
    load_dotenv()

    plan_path = Path("designs/retirement_benefit_q1_2025.yaml")
    assert plan_path.exists(), "Plan file not found"

    reg = BlockRegistry(); reg.load_specs()
    plan = load_plan(plan_path)

    # 入力データのロード（実データ）
    base_dir = Path("tests/data/retirement_data")
    employees = (base_dir / "社員一覧.csv").read_bytes()
    journal = (base_dir / "仕訳データ.csv").read_bytes()
    workbook_src = (base_dir / "退職給付ワークブック.xlsx").read_bytes()

    # ランナー（UIをHITLモードにして事前投入を利用）
    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir, default_ui_hitl=True)

    run_id = "retirement_q1_2025"
    ui = {
        "upload_files": {"collected_data": {"employees_csv": employees, "journal_csv": journal, "workbook": workbook_src}},
        "select_quarter": {"collected_data": {"fiscal_year": "2025", "quarter": "Q1"}},
    }
    _write_ui_state(runner, plan.id, run_id, ui)

    result = runner.run(plan, resume_run_id=run_id)

    # 出力の基本検証（Excel生成）
    assert isinstance(result, dict)
    wb_out = result.get("wb_final") or result.get("wb") or result.get("workbook_updated")
    assert isinstance(wb_out, dict) and isinstance(wb_out.get("bytes"), (bytes, bytearray)), "workbook bytes missing"

    # Excel内容の検証（ターゲットシート、C2、F2）
    out_file = tmp_path / "retirement_benefit_q1_2025.xlsx"
    out_file.write_bytes(wb_out["bytes"])  # type: ignore[arg-type]
    wb = load_workbook(out_file, data_only=True)
    assert "2025_Q1" in wb.sheetnames
    ws = wb["2025_Q1"]
    assert str(ws["C2"].value) == "2025-06-30"
    f2 = ws["F2"].value
    assert f2 in (None, ""), "F2 must be cleared for Q1"

    # ログが生成されていること
    plan_dir = runs_dir / plan.id
    logs = list(plan_dir.glob("*.jsonl"))
    assert len(logs) >= 1


