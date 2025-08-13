from __future__ import annotations

import yaml
from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def test_while_and_subflow_minimal(tmp_path: Path):
    reg = BlockRegistry()
    reg.load_specs()

    # Prepare subflow child plan on disk
    sub_yaml = {
        "apiVersion": "v1",
        "id": "child_plan",
        "version": "0.1.0",
        "graph": [
            {"id": "emit", "block": "ui.placeholder", "in": {"value": "ok"}, "out": {"value": "value"}}
        ],
    }
    child_path = tmp_path / "child.yaml"
    child_path.write_text(yaml.safe_dump(sub_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")

    # Parent plan with while loop and subflow
    parent_yaml = {
        "apiVersion": "v1",
        "id": "parent",
        "version": "0.1.0",
        "graph": [
            {
                "id": "loop",
                "type": "loop",
                "while": {"max_iterations": 2},
                "out": {"collect": "iter_list"},
                "body": {
                    "plan": {
                        "id": "loop_child",
                        "version": "0.1.0",
                        "graph": [
                            {"id": "emit", "block": "ui.placeholder", "in": {"value": "x"}, "out": {"value": "ok"}}
                        ],
                    }
                },
            },
            {
                "id": "call_sub",
                "type": "subflow",
                "call": {"plan_id": str(child_path)},
                "out": {"value": "ok"},
            },
        ],
    }
    parent_path = tmp_path / "parent.yaml"
    parent_path.write_text(yaml.safe_dump(parent_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")
    plan = load_plan(parent_path)

    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    res = runner.run(plan)
    assert "iter_list" in res
    assert isinstance(res["iter_list"], list)
    assert "ok" in res


