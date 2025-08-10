from __future__ import annotations

from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import dry_run_plan, validate_plan


def test_validate_and_dry_run_ok():
    registry = BlockRegistry()
    assert registry.load_specs() >= 3

    plan = load_plan(Path("designs/invoice_reconciliation.yaml"))
    errors = validate_plan(plan, registry)
    assert errors == []

    assert dry_run_plan(plan, registry) is True


def test_validate_detects_unknown_node_in_reference():
    registry = BlockRegistry()
    registry.load_specs()

    # load and tamper
    plan = load_plan(Path("designs/invoice_reconciliation.yaml"))
    # break a reference: point to a non-existing node id
    for node in plan.graph:
        if node.id == "match_ai":
            node.inputs["evidence_data"] = "${no_such_node.evidence}"
    errors = validate_plan(plan, registry)
    assert any("unknown node" in e for e in errors)


