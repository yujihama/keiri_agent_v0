from __future__ import annotations

from pathlib import Path
import json

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def test_node_finish_contains_elapsed_and_attempts(tmp_path: Path):
    reg = BlockRegistry()
    reg.load_specs()
    plan = load_plan(Path("designs/invoice_reconciliation.yaml"))

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=reg, runs_dir=runs_dir)
    runner.run(plan)

    files = list((runs_dir / plan.id).glob("*.jsonl"))
    assert files, "no log file"
    lines = files[0].read_text(encoding="utf-8").splitlines()
    events = [json.loads(l) for l in lines if l.strip()]
    finishes = [e for e in events if e.get("type") == "node_finish"]
    assert finishes, "no node_finish events"
    # at least one event should contain the added fields
    assert any("elapsed_ms" in e and "attempts" in e for e in finishes)


