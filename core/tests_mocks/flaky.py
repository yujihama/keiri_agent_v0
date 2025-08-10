from __future__ import annotations

from typing import Any, Dict

from core.blocks.base import BlockContext, ProcessingBlock


class FlakyBlock(ProcessingBlock):
    id = "test.flaky"
    version = "0.1.0"

    def __init__(self) -> None:
        self._count = 0

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        self._count += 1
        if self._count < 2:
            raise RuntimeError("fail once")
        return {"ok": True}


