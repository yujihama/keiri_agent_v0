from __future__ import annotations

from pathlib import Path
import yaml

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner


def test_when_guard_skips_node(tmp_path: Path):
    # clone base plan and add a when:false node into graph list properly
    base = Path("designs/invoice_payment_reconciliation_fixed.yaml")
    data = yaml.safe_load(base.read_text(encoding="utf-8"))
    data["graph"].append(
        {
            "id": "will_skip",
            "block": "ui.placeholder",
            "when": {"expr": "0 == 1"},
            "out": {"value": "ignored"},
        }
    )
    p = tmp_path / "plan.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    reg = BlockRegistry()
    reg.load_specs()
    plan = load_plan(p)
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    res = runner.run(plan)
    # should not contain alias 'ignored'
    assert "ignored" not in res


def test_foreach_collects_results(tmp_path: Path):
    reg = BlockRegistry()
    reg.load_specs()
    # foreach のミニマルなプランを動的に生成
    plan_yaml = {
        "apiVersion": "v1",
        "id": "foreach_min",
        "version": "0.1.0",
        "graph": [
            {
                "id": "loop",
                "type": "loop",
                "foreach": {"input": [1, 2, 3], "itemVar": "item"},
                "out": {"collect": "item_result_list"},
                "body": {
                    "plan": {
                        "id": "child",
                        "version": "0.1.0",
                        "graph": [
                            {"id": "emit", "block": "ui.placeholder", "in": {"value": "${vars.item}"}, "out": {"value": "ok"}}
                        ],
                    }
                },
            }
        ],
    }
    p = tmp_path / "foreach.yaml"
    p.write_text(yaml.safe_dump(plan_yaml, allow_unicode=True, sort_keys=False), encoding="utf-8")
    plan = load_plan(p)
    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    res = runner.run(plan)
    assert "item_result_list" in res
    assert isinstance(res["item_result_list"], list)


