from __future__ import annotations

from pathlib import Path

from core.plan.config_store import ConfigStore


def test_config_store_resolves_keys(tmp_path: Path):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "defaults.yaml").write_text("root:\n  value: 123\n", encoding="utf-8")
    (cfg_dir / "task_configs.json").write_text("{\"excel\": {\"sheet\": \"S\"}}", encoding="utf-8")

    store = ConfigStore(root_dir=tmp_path, config_dir="config")
    store.load_all()

    assert store.resolve("defaults.root.value") == 123
    assert store.resolve("task_configs.excel.sheet") == "S"
    assert store.resolve("no.such") is None


