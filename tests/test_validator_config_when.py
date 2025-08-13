from __future__ import annotations

from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.models import Plan, Node
from core.plan.validator import validate_plan
from core.plan.config_store import ConfigStore


def test_validator_checks_when_and_config(tmp_path: Path, monkeypatch):
    # prepare config
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "task_configs.yaml").write_text("foo: {bar: 1}", encoding="utf-8")

    # monkeypatch global store to point to tmp config
    from core.plan import config_store as cs

    cs._GLOBAL_STORE = ConfigStore(root_dir=tmp_path, config_dir="config")

    reg = BlockRegistry()
    reg.load_specs()

    plan = Plan(
        id="p",
        version="0",
        graph=[
            Node(
                id="u",
                block="ui.interactive_input",
                inputs={
                    "mode": "collect",
                    "requirements": [{"id": "workbook", "type": "file", "label": "Excel", "accept": ".xlsx"}],
                },
                outputs={"collected_data": "v"},
            ),
            Node(
                id="p1",
                block="excel.write_results",
                inputs={
                    "workbook": {"name": "dummy.xlsx", "bytes": "${u.v.workbook}"},
                    "data": {},
                    "output_config": "${config.task_configs.foo}",
                },
                outputs={"write_summary": "s"},
                when={"expr": "1 < 2"},
            ),
        ],
    )

    errors = validate_plan(plan, reg)
    assert errors == [], errors


