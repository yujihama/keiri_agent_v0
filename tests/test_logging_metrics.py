from __future__ import annotations

from pathlib import Path
import json
import base64

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


def test_node_finish_contains_elapsed_and_attempts(tmp_path: Path):
    load_dotenv()
    reg = BlockRegistry()
    reg.load_specs()
    plan = load_plan(Path("designs/invoice_payment_reconciliation_fixed.yaml"))

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir, default_ui_hitl=True)

    # pre-inject UI inputs
    zip_bytes = Path("tests/data/test_evidence.zip").read_bytes()
    wb_bytes = Path("tests/data/test_workbook.xlsx").read_bytes()
    run_id = "metrics"
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

    runner.run(plan, resume_run_id=run_id)

    files = list((runs_dir / plan.id).glob("*.jsonl"))
    assert files, "no log file"
    lines = files[0].read_text(encoding="utf-8").splitlines()
    events = [json.loads(l) for l in lines if l.strip()]
    finishes = [e for e in events if e.get("type") == "node_finish"]
    assert finishes, "no node_finish events"
    # at least one event should contain the added fields
    assert any("elapsed_ms" in e and "attempts" in e for e in finishes)


