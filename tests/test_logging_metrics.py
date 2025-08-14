from __future__ import annotations

from pathlib import Path
import json
import base64

from dotenv import load_dotenv  # type: ignore

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext


def _encode_for_json(obj):
    if isinstance(obj, (bytes, bytearray)):
        return {"__type": "b64bytes", "data": base64.b64encode(bytes(obj)).decode("ascii")}
    if isinstance(obj, dict):
        return {k: _encode_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_encode_for_json(v) for v in obj]
    return obj


pass


def test_node_finish_contains_elapsed_and_attempts(tmp_path: Path):
    load_dotenv()
    reg = BlockRegistry()
    reg.load_specs()
    plan = load_plan(Path("designs/invoice_payment_reconciliation_fixed.yaml"))
    # ループ内の ai.process_llm を fast-path に（answer注入）
    for n in plan.graph:
        try:
            if getattr(n, "type", "") == "loop" and n.body and n.body.plan and n.body.plan.graph:
                for cn in n.body.plan.graph:
                    if getattr(cn, "block", "") == "ai.process_llm":
                        cin = dict(getattr(cn, "inputs", {}))
                        ev = dict(cin.get("evidence_data") or {})
                        ev["answer"] = "{\"results\": [], \"summary\": {}}"
                        cin["evidence_data"] = ev
                        cn.inputs = cin
        except Exception:
            pass

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir, default_ui_hitl=False)

    # ヘッドレス実行
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
    runner.run(plan, execution_context=exec_ctx)

    files = list((runs_dir / plan.id).glob("*.jsonl"))
    assert files, "no log file"
    lines = files[0].read_text(encoding="utf-8").splitlines()
    events = [json.loads(l) for l in lines if l.strip()]
    finishes = [e for e in events if e.get("type") == "node_finish"]
    assert finishes, "no node_finish events"
    # at least one event should contain the added fields
    assert any("elapsed_ms" in e and "attempts" in e for e in finishes)


