#!/usr/bin/env python3
"""
Headless CLI Runner

- デフォルトの設定・出力先は `headless/` 配下
  - 設定: `headless/configs/*.json`
  - 出力: `headless/output/`
- ランログ(JSONL)は `runs/<plan_id>/<timestamp>.jsonl`
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# .env の読み込み（任意）
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# プロジェクトルートを sys.path に追加（このファイルは headless/ 配下にあるため）
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext


HEADLESS_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_DIR = HEADLESS_DIR / "configs"
DEFAULT_OUTPUT_DIR = HEADLESS_DIR / "output"


def _load_json_file(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_execution_context(args) -> ExecutionContext:
    # ベース
    if args.config:
        execution_context = ExecutionContext.from_config_file(args.config)
    else:
        execution_context = ExecutionContext()

    # ヘッドレスフラグ
    execution_context.headless_mode = True if args.headless else execution_context.headless_mode

    # 出力先（未指定なら headless/output）
    if args.output:
        execution_context.output_dir = Path(args.output)
    elif execution_context.output_dir is None:
        execution_context.output_dir = DEFAULT_OUTPUT_DIR

    # 変数
    if args.vars:
        if args.vars.strip().startswith("{"):
            vars_data = json.loads(args.vars)
        else:
            vars_path = Path(args.vars)
            vars_data = _load_json_file(vars_path)
        execution_context.vars_overrides.update(vars_data)

    # ファイル入力（指定がなければ headless/configs/files_config.json を自動採用）
    files_data = None
    if args.files:
        files_data = _load_json_file(Path(args.files))
    else:
        default_files = DEFAULT_CONFIG_DIR / "files_config.json"
        if default_files.exists():
            files_data = _load_json_file(default_files)
    if isinstance(files_data, dict):
        execution_context.file_inputs.update({k: Path(v) for k, v in files_data.items()})

    # UIモック（指定がなければ headless/configs/ui_mocks.json を自動採用）
    mocks_data = None
    if args.ui_mocks:
        mocks_data = _load_json_file(Path(args.ui_mocks))
    else:
        default_mocks = DEFAULT_CONFIG_DIR / "ui_mocks.json"
        if default_mocks.exists():
            mocks_data = _load_json_file(default_mocks)
    if isinstance(mocks_data, dict):
        execution_context.ui_mock_responses.update(mocks_data)

    return execution_context


def output_results(results: dict, output_dir: Optional[Path], plan_id: str) -> None:
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        results_file = output_dir / f"{plan_id}_results.json"
        with results_file.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"Results saved to: {results_file}")

        # バイナリの保存（name/bytes 想定）
        for key, value in results.items():
            if isinstance(value, dict) and isinstance(value.get("bytes"), (bytes, bytearray)):
                name = value.get("name", f"{key}.bin")
                (output_dir / name).write_bytes(value["bytes"])
                print(f"Binary saved: {(output_dir / name)}")

    print("\n=== Execution Results ===")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless CLI Runner")
    parser.add_argument("plan_file", help="Plan YAML file path")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    parser.add_argument("--config", help="Execution config JSON file")
    parser.add_argument("--vars", help="Variables JSON file or JSON string")
    parser.add_argument("--files", help="Files config JSON file")
    parser.add_argument("--ui-mocks", help="UI mocks JSON file")
    parser.add_argument("--output", help="Output directory (default: headless/output)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    plan_path = Path(args.plan_file)
    if not plan_path.exists():
        print(f"Error: Plan file not found: {plan_path}")
        sys.exit(1)

    if args.verbose:
        print(f"Loading plan from: {plan_path}")

    plan = load_plan(plan_path)
    if args.verbose:
        print(f"Plan loaded: {plan.id} (nodes={len(plan.graph)})")

    exec_ctx = build_execution_context(args)
    if args.verbose:
        print(f"Execution context: {exec_ctx.to_dict()}")

    registry = BlockRegistry()
    registry.load_specs()
    runner = PlanRunner(registry=registry, default_ui_hitl=False)

    if args.verbose:
        print("Starting execution...")

    results = runner.run(plan, vars_overrides=exec_ctx.vars_overrides, execution_context=exec_ctx)

    if args.verbose:
        print("Execution finished.")

    output_results(results, exec_ctx.output_dir, plan.id)


if __name__ == "__main__":
    main()


