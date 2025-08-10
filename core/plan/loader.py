from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import Plan


def load_plan(path: str | Path) -> Plan:
    """Load a plan from a YAML or JSON file and parse it into a Plan model.

    This function intentionally does not resolve `${...}` references. Those are
    kept as-is for the validator/runner to interpret later.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    if file_path.suffix.lower() in {".yaml", ".yml"}:
        with file_path.open("r", encoding="utf-8") as f:
            data: Any = yaml.safe_load(f) or {}
    elif file_path.suffix.lower() == ".json":
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        raise ValueError(f"Unsupported plan file extension: {file_path.suffix}")

    return Plan.model_validate(data)


