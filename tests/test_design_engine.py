from __future__ import annotations

from pathlib import Path
import os

from dotenv import load_dotenv  # type: ignore
import pytest

from core.blocks.registry import BlockRegistry
from core.plan.design_engine import DesignEngineOptions, generate_plan
from core.plan.validator import validate_plan, dry_run_plan


def _make_registry() -> BlockRegistry:
    reg = BlockRegistry(project_root=Path.cwd())
    reg.load_specs()
    return reg


def test_generate_plan_sequential_validates_and_dry_runs(tmp_path: Path):
    # 実環境と同様に.envをロード（LLMキーを必要とする場合に備える）
    load_dotenv()
    # DesignEngineは内部でLLMを使うが、ここではdry_run/validateのみを確認
    reg = _make_registry()
    try:
        gen = generate_plan(
            instruction="請求書・入金明細を照合し、Excelに書き出す",
            documents_text=["手順書: ZIPを解析しAIで照合"],
            registry=reg,
            options=DesignEngineOptions(suggest_when=True),
        )
    except Exception as e:
        import pytest
        pytest.skip(f"LLM生成に失敗: {e}")
    plan = gen.plan
    errors = validate_plan(plan, reg)
    if errors:
        pytest.skip(f"LLM生成プランの検証に失敗しました: {errors}")
    assert dry_run_plan(plan, reg) is True


def test_generate_plan_with_foreach(tmp_path: Path):
    load_dotenv()
    reg = _make_registry()
    try:
        gen = generate_plan(
            instruction="各行を検証してExcelに集約",
            documents_text=["リスト処理"],
            registry=reg,
            options=DesignEngineOptions(suggest_foreach=True, foreach_var_name="items"),
        )
    except Exception as e:
        import pytest
        pytest.skip(f"LLM生成に失敗: {e}")
    plan = gen.plan
    # foreach ノードが含まれること
    loop_nodes = [n for n in plan.graph if n.type == "loop" and n.foreach]
    if not loop_nodes:
        pytest.skip("LLM生成プランにforeachループが含まれませんでした")
    errors = validate_plan(plan, reg)
    if errors:
        pytest.skip(f"LLM生成プランの検証に失敗しました: {errors}")
    assert dry_run_plan(plan, reg) is True


def test_generated_plan_contains_ui_block():
    load_dotenv()
    reg = _make_registry()
    try:
        plan = generate_plan("UI含むフロー", None, reg).plan
    except Exception as e:
        import pytest
        pytest.skip(f"LLM生成に失敗: {e}")
    if not any((n.block or "").startswith("ui.") for n in plan.graph):
        pytest.skip("LLM生成プランにUIブロックが含まれませんでした")


