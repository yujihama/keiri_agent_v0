from __future__ import annotations

from pathlib import Path

from core.blocks.registry import BlockRegistry
from core.plan.design_engine import DesignEngineOptions, generate_plan
from core.plan.validator import validate_plan, dry_run_plan


def _make_registry() -> BlockRegistry:
    reg = BlockRegistry(project_root=Path.cwd())
    reg.load_specs()
    return reg


def test_generate_plan_sequential_validates_and_dry_runs(tmp_path: Path):
    reg = _make_registry()
    gen = generate_plan(
        instruction="請求書・入金明細を照合し、Excelに書き出す",
        documents_text=["手順書: ZIPを解析しAIで照合"],
        registry=reg,
        options=DesignEngineOptions(suggest_when=True),
    )
    plan = gen.plan
    errors = validate_plan(plan, reg)
    assert errors == [], f"validation errors: {errors}"
    assert dry_run_plan(plan, reg) is True


def test_generate_plan_with_foreach(tmp_path: Path):
    reg = _make_registry()
    gen = generate_plan(
        instruction="各行を検証してExcelに集約",
        documents_text=["リスト処理"],
        registry=reg,
        options=DesignEngineOptions(suggest_foreach=True, foreach_var_name="items"),
    )
    plan = gen.plan
    # foreach ノードが含まれること
    loop_nodes = [n for n in plan.graph if n.type == "loop" and n.foreach]
    assert loop_nodes, "foreach loop node not generated"
    errors = validate_plan(plan, reg)
    assert errors == [], f"validation errors: {errors}"
    assert dry_run_plan(plan, reg) is True


def test_generated_plan_contains_ui_block():
    reg = _make_registry()
    plan = generate_plan("UI含むフロー", None, reg).plan
    assert any((n.block or "").startswith("ui.") for n in plan.graph)


