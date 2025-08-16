from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List, Tuple

import yaml

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import validate_plan, dry_run_plan


def list_designs() -> List[Path]:
    designs_dir = (Path.cwd() / "designs").resolve()
    return sorted(designs_dir.rglob("*.yaml"))


def _now_tmp_yaml_path() -> Path:
    return Path(tempfile.mkstemp(prefix=".tmp_plan_", suffix=".yaml", dir=str(Path.cwd()))[1])


def validate_and_dryrun_yaml(yaml_text: str, registry: BlockRegistry, *, do_dryrun: bool = True):
    tmp = _now_tmp_yaml_path()
    try:
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
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


