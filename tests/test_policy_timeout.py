from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
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


def test_timeout_policy(tmp_path):
    reg = BlockRegistry()
    reg.specs_by_id.setdefault("test.slow", [])
    reg.specs_by_id["test.slow"].append(
        DummySpec(id="test.slow", version="0.1.0", entrypoint="core.tests_mocks.slow:SlowBlock")  # type: ignore[arg-type]
    )

    plan = Plan(
        id="p",
        version="0",
        graph=[Node(id="n1", block="test.slow", inputs={}, outputs={"ok": "ok"})],
        policy=Policy(on_error="continue", retries=0, timeout_ms=500),
    )

    runner = PlanRunner(registry=reg, runs_dir=tmp_path / "runs")
    out = runner.run(plan)
    # timeout means continue with empty outputs
    assert "ok" not in out


