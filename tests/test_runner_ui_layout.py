from __future__ import annotations

from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.models import Plan, Node, UIConfig
from core.plan.runner import PlanRunner


def test_ui_nodes_respect_ui_layout_order(tmp_path: Path, monkeypatch):
    reg = BlockRegistry()
    reg.load_specs()

    # Build a simple plan with two UI nodes and one processing node depending on them
    plan = Plan(
        id="p",
        version="0",
        ui=UIConfig(layout=["u1", "u2"]),
        graph=[
            Node(id="u2", block="ui.file_uploader.excel", inputs={}, outputs={"workbook": "wb"}),
            Node(id="u1", block="ui.file_uploader.evidence_zip", inputs={}, outputs={"evidence_zip": "zip"}),
            Node(
                id="proc",
                block="excel.write_results",
                inputs={"workbook": "${u2.wb}", "data": "${u1.zip}", "output_config": {"k": 1}},
                outputs={"write_summary": "ok"},
            ),
        ],
    )

    events = []

    def on_event(ev):
        events.append(ev)

    runner = PlanRunner(registry=reg)
    runner.run(plan, on_event=on_event)

    node_starts = [e for e in events if e.get("type") == "node_start"]
    ids_in_order = [e.get("node") for e in node_starts]
    # u1 should appear before u2 because of ui.layout ordering
    assert ids_in_order.index("u1") < ids_in_order.index("u2")


