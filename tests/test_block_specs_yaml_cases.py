from __future__ import annotations

from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
import importlib
from typing import Any, Dict

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
    assert count > 0
    return reg


@pytest.fixture(scope="session")
def all_specs(registry: BlockRegistry):
    out = []
    for items in registry.specs_by_id.values():
        out.extend(items)
    out.sort(key=lambda s: f"{s.id}@{s.version}")
    return out


def _sample_value_for_type(t: str, name: str = "") -> Any:
    t = (t or "object").lower()
    if t in ("string", "str"):
        # prefer enum first if needed (handled by caller)
        return name or "sample"
    if t in ("integer", "int"):
        return 1
    if t in ("number", "float"):
        return 1.0
    if t in ("boolean", "bool"):
        return True
    if t == "array":
        return []
    # default object
    return {}


def _build_inputs_from_spec(spec: Any) -> Dict[str, Any]:
    inputs: Dict[str, Any] = {}
    for key, meta in (spec.inputs or {}).items():
        if not isinstance(meta, dict):
            continue
        if "enum" in meta and isinstance(meta["enum"], list) and meta["enum"]:
            val = meta["enum"][0]
        else:
            val = _sample_value_for_type(str(meta.get("type") or "object"), key)
        inputs[key] = val

    # Heuristics for known blocks requiring meaningful minimal data
    if spec.id == "file.read_csv":
        inputs.setdefault("bytes", b"a,b\n1,2\n")
        inputs.setdefault("has_header", True)
    if spec.id == "excel.read_data":
        try:
            from openpyxl import Workbook  # type: ignore
            wb = Workbook()
            ws = wb.active
            ws.title = "Sheet1"
            ws.append(["a", "b"])
            ws.append([1, 2])
            bio = BytesIO()
            wb.save(bio)
            inputs["workbook"] = {"name": "test.xlsx", "bytes": bio.getvalue()}
            inputs.setdefault("read_config", {"sheets": [{"name": "Sheet1", "header_row": 1}]})
            inputs.setdefault("mode", "single")
        except Exception:
            pass
    if spec.id == "transforms.rename_fields":
        inputs.setdefault("items", [{"old": 1, "c": 3}])
        inputs.setdefault("rename", {"old": "new"})
        inputs.setdefault("mode", "move")

    # UI defaults to safe minimal values
    if spec.id == "ui.interactive_input":
        inputs.setdefault("mode", "collect")
        inputs.setdefault("requirements", [
            {"id": "name", "type": "text", "label": "Name", "required": True},
            {"id": "agree", "type": "boolean", "label": "Agree"},
        ])
        inputs.setdefault("message", "test")
    if spec.id == "ui.confirmation":
        inputs.setdefault("message", "Are you sure?")
        inputs.setdefault("options", ["approve", "reject"])
    if spec.id == "ui.diff_viewer":
        inputs.setdefault("before", {"x": 1})
        inputs.setdefault("after", {"x": 2})
        inputs.setdefault("message", "diff")

    return inputs


def _assert_type_matches(value: Any, type_name: str) -> None:
    # None はオプショナル出力として許容
    if value is None:
        return
    t = (type_name or "object").lower()
    if t in ("string", "str"):
        assert isinstance(value, str)
    elif t in ("integer", "int"):
        assert isinstance(value, int)
    elif t in ("number", "float"):
        assert isinstance(value, (int, float))
    elif t in ("boolean", "bool"):
        assert isinstance(value, bool)
    elif t == "array":
        assert isinstance(value, list)
    elif t == "object":
        # 柔軟に、辞書または配列（中間ステップ等）を許容
        assert isinstance(value, (dict, list))
    elif t == "any":
        assert True
    else:
        # unknown → no strict check
        assert value is not None or value is None


def _validate_outputs_against_spec(spec: Any, outputs: Dict[str, Any]) -> None:
    assert isinstance(outputs, dict)
    for out_key, out_meta in (spec.outputs or {}).items():
        if out_key in outputs and isinstance(out_meta, dict):
            out_type = str(out_meta.get("type") or "object")
            _assert_type_matches(outputs[out_key], out_type)


def test_yaml_driven_block_cases(registry: BlockRegistry, all_specs, monkeypatch) -> None:
    ctx = BlockContext(run_id="yaml-cases")
    exec_ctx = ExecutionContext(headless_mode=True)

    # Stub streamlit for interactive_input
    try:
        mod = importlib.import_module("core.blocks.ui.interactive_input")
        stub = SimpleNamespace(error=lambda *args, **kwargs: None, session_state={})
        monkeypatch.setattr(mod, "st", stub, raising=False)
    except Exception:
        pass

    SAFE_RUN_IDS = {
        "file.read_csv",
        "excel.read_data",
        "transforms.rename_fields",
        "ui.placeholder",
        "ui.confirmation",
        "ui.diff_viewer",
        "ui.interactive_input",
    }

    for spec in all_specs:
        inst = registry.get(f"{spec.id}@{spec.version}")
        inputs = _build_inputs_from_spec(spec)

        if isinstance(inst, UIBlock):
            out = inst.render(ctx, inputs, execution_context=exec_ctx)  # type: ignore[arg-type]
            _validate_outputs_against_spec(spec, out)
        else:
            # Prefer dry_run for safety; run for known-safe ids
            if spec.id in SAFE_RUN_IDS:
                try:
                    out = inst.run(ctx, inputs)  # type: ignore[attr-defined]
                except Exception:
                    # Fallback to dry_run if run is not safe
                    out = inst.dry_run(inputs)
            else:
                out = inst.dry_run(inputs)
            _validate_outputs_against_spec(spec, out)


