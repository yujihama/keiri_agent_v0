from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import importlib
from typing import List

import pytest

from core.blocks.registry import BlockRegistry
from core.blocks.base import ProcessingBlock, UIBlock, BlockContext
from core.plan.execution_context import ExecutionContext


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def registry(repo_root: Path) -> BlockRegistry:
    reg = BlockRegistry(project_root=repo_root)
    count = reg.load_specs()
    assert count > 0, "No block specs loaded"
    return reg


@pytest.fixture(scope="session")
def all_specs(registry: BlockRegistry):
    specs: List = []
    for items in registry.specs_by_id.values():
        specs.extend(items)
    # stable order for ids
    specs.sort(key=lambda s: f"{s.id}@{s.version}")
    return specs


def test_spec_files_count_matches(registry: BlockRegistry, repo_root: Path) -> None:
    yaml_files = sorted((repo_root / "block_specs").rglob("*.yaml"))
    total_specs = sum(len(v) for v in registry.specs_by_id.values())
    assert total_specs == len(yaml_files)


def test_entrypoint_resolves_and_class_type(registry: BlockRegistry, all_specs) -> None:
    for s in all_specs:
        cls = registry._load_class_from_entrypoint(s.entrypoint)
        assert isinstance(cls, type)
        if "/ui/" in s.entrypoint or s.entrypoint.startswith("blocks/ui"):
            assert issubclass(cls, UIBlock)
        else:
            assert issubclass(cls, ProcessingBlock)


def test_registry_get_instance_id_version(registry: BlockRegistry, all_specs) -> None:
    for s in all_specs:
        inst = registry.get(f"{s.id}@{s.version}")
        assert isinstance(inst, (ProcessingBlock, UIBlock))
        # 実装クラスの id/version は後方互換や複数バリアントの都合で異なる場合があるため、
        # ここでは型・生成可否のみを検証する


