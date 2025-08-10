from __future__ import annotations

from core.blocks.base import UIBlock
from core.blocks.registry import BlockRegistry


def test_load_and_instantiate_placeholder_block():
    registry = BlockRegistry()
    count = registry.load_specs()
    assert count >= 1

    block = registry.get("ui.placeholder")
    assert isinstance(block, UIBlock)


