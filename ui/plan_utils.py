from __future__ import annotations

import json
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple

import yaml

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan


def list_designs() -> List[Path]:
    designs_dir = (Path.cwd() / "designs").resolve()
    return sorted(designs_dir.rglob("*.yaml"))


@contextmanager
def _create_temp_yaml_file():
    """一時的なYAMLファイルを作成し、自動的に削除するコンテキストマネージャー"""
    # NamedTemporaryFileを使って自動削除を保証
    with tempfile.NamedTemporaryFile(
        mode='w',
        prefix=".tmp_plan_",
        suffix=".yaml",
        dir=str(Path.cwd()),
        encoding='utf-8',
        delete=False  # 明示的に削除制御するためFalse
    ) as tmp_file:
        tmp_path = Path(tmp_file.name)
        yield tmp_path

    # コンテキスト終了時にファイルを削除
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception as e:
        # 削除に失敗した場合でも例外を投げない
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"一時ファイルの削除に失敗しました: {tmp_path} - {e}")


def validate_and_dryrun_yaml(yaml_text: str, registry: BlockRegistry, *, do_dryrun: bool = True):
    with _create_temp_yaml_file() as tmp:
        tmp.write_text(yaml_text, encoding="utf-8")
        plan = load_plan(tmp)
        errors = validate_plan(plan, registry)
        dr_err = None
        if not errors and do_dryrun:
            try:
                dry_run_plan(plan, registry)
            except Exception as e:  # noqa: BLE001
                dr_err = e
        return plan, errors or [], dr_err


