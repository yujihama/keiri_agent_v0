from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml


class ConfigStore:
    """Lightweight configuration store for resolving ${config.*} references.

    Loads YAML/JSON files from a configurable directory (default: ./config).
    Top-level keys are derived from file names without extension, e.g.,
    'task_configs.yaml' -> namespace 'task_configs'.
    """

    def __init__(self, root_dir: str | Path | None = None, config_dir: str | Path = "config") -> None:
        cwd = Path.cwd() if root_dir is None else Path(root_dir)
        self.root_dir: Path = cwd
        self.config_dir: Path = (cwd / config_dir).resolve()
        self._data_by_ns: Dict[str, Dict[str, Any]] = {}
        self._loaded: bool = False

    def load_all(self) -> None:
        if self._loaded:
            return
        if not self.config_dir.exists():
            self._loaded = True
            return
        for p in sorted(self.config_dir.iterdir()):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            ns = p.stem  # filename without extension
            try:
                if p.suffix.lower() in {".yaml", ".yml"}:
                    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                else:
                    data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._data_by_ns[ns] = data
            except Exception:
                # Ignore broken config files for now
                continue
        self._loaded = True

    def resolve(self, dotted_path: str) -> Any:
        """Resolve 'namespace.path.to.key' from loaded configuration.

        Returns None if not found.
        """

        self.load_all()
        if not dotted_path:
            return None
        parts = dotted_path.split(".")
        if not parts:
            return None
        ns, *rest = parts
        obj: Any = self._data_by_ns.get(ns)
        for seg in rest:
            if isinstance(obj, dict) and seg in obj:
                obj = obj[seg]
            else:
                return None
        return obj


_GLOBAL_STORE: ConfigStore | None = None


def get_store() -> ConfigStore:
    global _GLOBAL_STORE
    if _GLOBAL_STORE is None:
        # allow override config dir via env
        cfg_dir = os.getenv("KEIRI_AGENT_CONFIG_DIR", "config")
        _GLOBAL_STORE = ConfigStore(config_dir=cfg_dir)
    return _GLOBAL_STORE


