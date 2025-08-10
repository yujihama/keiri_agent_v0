from __future__ import annotations

from pathlib import Path
import json

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def test_runner_e2e_executes_plan_and_logs_events(tmp_path: Path, monkeypatch):
    registry = BlockRegistry()
    registry.load_specs()
    plan = load_plan(Path("designs/invoice_reconciliation.yaml"))

    runs_dir = tmp_path / "runs"
    runner = PlanRunner(registry=registry, runs_dir=runs_dir)
    results = runner.run(plan)

    # Check results contain expected aliases
    assert "evidence" in results or "match_results" in results or "write_summary" in results

    # Verify log file created and contains start/finish
    plan_dir = runs_dir / plan.id
    files = list(plan_dir.glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8").strip().splitlines()
    events = [json.loads(line) for line in content]
    types = [e["type"] for e in events]
    assert "start" in types and "finish" in types


