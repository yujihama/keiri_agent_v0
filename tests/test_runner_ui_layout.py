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
            Node(
                id="u2",
                block="ui.interactive_input",
                inputs={
                    "mode": "collect",
                    "requirements": [
                        {"id": "workbook", "type": "file", "label": "Excel", "accept": ".xlsx"}
                    ],
                },
                outputs={"collected_data": "wb_data"},
            ),
            Node(
                id="u1",
                block="ui.interactive_input",
                inputs={
                    "mode": "collect",
                    "requirements": [
                        {"id": "evidence_zip", "type": "folder", "label": "ZIP"}
                    ],
                },
                outputs={"collected_data": "zip_data"},
            ),
            Node(
                id="proc",
                block="excel.write",
                inputs={
                    "workbook": {"name": "dummy.xlsx", "bytes": "${u2.wb_data.workbook}"},
                    "cell_updates": {"sheet": "Results", "cells": {"A1": "File", "B1": "Count", "C1": "Sum"}},
                    "column_updates": {"sheet": "Results", "start_row": 2, "header_row": 1, "columns": ["file", "count", "sum"], "values": []},
                },
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


