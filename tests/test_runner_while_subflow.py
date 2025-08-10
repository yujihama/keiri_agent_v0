from __future__ import annotations

from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def test_while_and_subflow_minimal(tmp_path: Path):
    reg = BlockRegistry()
    reg.load_specs()
    plan = load_plan(Path("designs/while_subflow_example.yaml"))
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    res = runner.run(plan)
    assert "iter_list" in res
    assert isinstance(res["iter_list"], list)
    assert "ok" in res


