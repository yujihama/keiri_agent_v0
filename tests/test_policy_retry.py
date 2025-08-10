from __future__ import annotations

from typing import Any, Dict

from core.blocks.registry import BlockRegistry
from core.plan.models import Plan, Node, Policy
from core.plan.runner import PlanRunner
from pydantic import BaseModel


class DummySpec(BaseModel):
    id: str
    version: str
    entrypoint: str
    inputs: Dict[str, Any] = {}
    outputs: Dict[str, Any] = {"ok": {"type": "boolean"}}


def test_retry_policy(tmp_path):
    reg = BlockRegistry()
    reg.specs_by_id.setdefault("test.flaky", [])
    reg.specs_by_id["test.flaky"].append(
        DummySpec(id="test.flaky", version="0.1.0", entrypoint="core.tests_mocks.flaky:FlakyBlock")  # type: ignore[arg-type]
    )

    plan = Plan(
        id="p",
        version="0",
        graph=[
            Node(id="n1", block="test.flaky", inputs={}, outputs={"ok": "ok"}),
        ],
        policy=Policy(on_error="retry", retries=1),
    )

    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    out = runner.run(plan)
    assert out["ok"] is True


