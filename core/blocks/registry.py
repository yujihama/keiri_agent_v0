from __future__ import annotations

import importlib.util
import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml
from pydantic import BaseModel, Field

from .base import ProcessingBlock, UIBlock


class BlockSpec(BaseModel):
    """Specification describing a block declared in YAML.

    The `entrypoint` may be either a Python dotted path (e.g.
    `package.module:ClassName`) or a file path (e.g.
    `blocks/ui/placeholder.py:PlaceholderUIBlock`). File paths are resolved
    relative to the project root or `core/` when starting with `blocks/`.
    """

    id: str
    version: str
    entrypoint: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    requirements: List[str] = Field(default_factory=list)
    # 任意メタ: タグ/カテゴリ/スキーマ参照
    tags: List[str] | None = None
    category: str | None = None
    schema_refs: List[str] | None = None
    description: Optional[str] = None


class BlockRegistry:
    """Registry that loads block specs and dynamically instantiates blocks."""

    def __init__(self, project_root: Optional[str | Path] = None, specs_dir: str = "block_specs") -> None:
        self.project_root: Path = Path(project_root) if project_root else Path.cwd()
        self.specs_dir: Path = self.project_root / specs_dir
        self._specs_by_id: Dict[str, List[BlockSpec]] = {}

    @property
    def specs_by_id(self) -> Dict[str, List[BlockSpec]]:
        return self._specs_by_id

    def load_specs(self) -> int:
        """Load all YAML specs under the `specs_dir` recursively.

        Returns the number of specs loaded.
        """

        if not self.specs_dir.exists():
            return 0

        count = 0
        for spec_path in sorted(self.specs_dir.rglob("*.yaml")):
            with spec_path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            spec = BlockSpec.model_validate(data)
            self._specs_by_id.setdefault(spec.id, []).append(spec)
            count += 1
        # 簡易な import 可否検査（UIのカタログでの警告用に利活用）
        for bids in self._specs_by_id.values():
            for s in bids:
                reqs = s.requirements or []
                for r in reqs:
                    if isinstance(r, str) and not r.startswith("env:"):
                        try:
                            __import__(r)
                        except Exception:
                            # 単にロードは継続。UI側で不足依存を通知するための事前ウォームアップ
                            pass
        return count

    def list_block_ids(self) -> List[str]:
        return sorted(self._specs_by_id.keys())

    def _resolve_spec(self, block_id: str, version: Optional[str] = None) -> BlockSpec:
        specs = self._specs_by_id.get(block_id) or []
        if not specs:
            raise KeyError(f"Block id not found: {block_id}")
        if version:
            for s in specs:
                if s.version == version:
                    return s
            raise KeyError(f"Version {version} not found for block {block_id}")

        # Choose the highest semantic version when multiple are present.
        try:
            from packaging.version import Version

            specs_sorted = sorted(specs, key=lambda s: Version(s.version))
            return specs_sorted[-1]
        except Exception:
            # Fallback: last loaded
            return specs[-1]

    def get(self, block_id: str, version: Optional[str] = None) -> ProcessingBlock | UIBlock:
        """Instantiate a block by id (and optional version)."""

        # support id@semver notation in block_id
        bid = block_id
        ver = version
        if "@" in block_id and version is None:
            bid, ver = block_id.split("@", 1)

        spec = self._resolve_spec(bid, ver)
        cls = self._load_class_from_entrypoint(spec.entrypoint)
        instance = cls()  # type: ignore[call-arg]

        # Optional sanity check
        if not isinstance(instance, (ProcessingBlock, UIBlock)):
            raise TypeError(
                f"Loaded class for {block_id} is not a ProcessingBlock/UIBlock: {type(instance)!r}"
            )
        return instance

    def _load_class_from_entrypoint(self, entrypoint: str):
        module_part, _, class_name = entrypoint.partition(":")
        if not class_name:
            raise ValueError(f"Invalid entrypoint (missing class): {entrypoint}")

        module_part = module_part.strip()
        class_name = class_name.strip()

        # File path case (ends with .py or contains a path separator)
        normalized = module_part.replace("\\", "/")
        if normalized.endswith(".py") or "/" in normalized:
            candidate_files: List[Path] = []

            # Direct relative to project root
            candidate_files.append((self.project_root / normalized).resolve())

            # Relative to core/ for entries starting with blocks/
            if normalized.startswith("blocks/"):
                candidate_files.append((self.project_root / "core" / normalized).resolve())

            for file_path in candidate_files:
                if file_path.exists():
                    mod_name = f"dyn_{uuid4().hex}"
                    spec = importlib.util.spec_from_file_location(mod_name, file_path)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = module
                    spec.loader.exec_module(module)
                    try:
                        return getattr(module, class_name)
                    except AttributeError as e:
                        raise ImportError(
                            f"Class {class_name!r} not found in module loaded from {file_path}"
                        ) from e

            raise FileNotFoundError(
                f"Entrypoint file not found for {entrypoint!r}. Tried: {[str(p) for p in candidate_files]}"
            )

        # Dotted module path case
        module = import_module(module_part)
        try:
            return getattr(module, class_name)
        except AttributeError as e:
            raise ImportError(f"Class {class_name!r} not found in module {module_part!r}") from e


