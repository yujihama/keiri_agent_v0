from __future__ import annotations

import time
from typing import Any, Dict

from core.blocks.base import BlockContext, ProcessingBlock


class SlowBlock(ProcessingBlock):
    id = "test.slow"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        time.sleep(2)
        return {"ok": True}


