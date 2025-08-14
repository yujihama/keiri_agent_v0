#!/usr/bin/env python3
"""
Keiri Agent CLI Runner

コマンドラインからプランを実行するためのツール
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# 環境変数の読み込み
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext
from core.plan.file_handler import FileInputHandler


def build_execution_context(args) -> ExecutionContext:
    """コマンドライン引数から実行コンテキストを構築"""
    
    # 設定ファイルから読み込み
    if args.config:
        execution_context = ExecutionContext.from_config_file(args.config)
    else:
        execution_context = ExecutionContext()
    
    # コマンドライン引数でオーバーライド
    execution_context.headless_mode = args.headless
    
    if args.output:
        execution_context.output_dir = Path(args.output)
    
    if args.vars:
        if args.vars.startswith('{'):
            # JSON文字列として解析
            vars_data = json.loads(args.vars)
        else:
            # ファイルとして読み込み
            vars_path = Path(args.vars)
            if vars_path.exists():
                with vars_path.open('r', encoding='utf-8') as f:
                    vars_data = json.load(f)
            else:
                raise FileNotFoundError(f"Variables file not found: {vars_path}")
        
        execution_context.vars_overrides.update(vars_data)
    
    if args.files:
        files_path = Path(args.files)
        if files_path.exists():
            with files_path.open('r', encoding='utf-8') as f:
                files_data = json.load(f)
            execution_context.file_inputs.update({
                k: Path(v) for k, v in files_data.items()
            })
    
    if args.ui_mocks:
        mocks_path = Path(args.ui_mocks)
        if mocks_path.exists():
            with mocks_path.open('r', encoding='utf-8') as f:
                mocks_data = json.load(f)
            execution_context.ui_mock_responses.update(mocks_data)
    
    return execution_context


def output_results(results: dict, output_dir: Optional[Path], plan_id: str):
    """実行結果を出力"""
    
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 結果をJSONファイルに保存
        results_file = output_dir / f"{plan_id}_results.json"
        with results_file.open('w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
        print(f"Results saved to: {results_file}")
        
        # バイナリファイルがあれば保存
        for key, value in results.items():
            if isinstance(value, dict) and isinstance(value.get('bytes'), bytes):
                file_name = value.get('name', f"{key}.bin")
                file_path = output_dir / file_name
                file_path.write_bytes(value['bytes'])
                print(f"Binary file saved: {file_path}")
            elif isinstance(value, str) and len(value) > 100 and value.startswith('data:'):
                # base64エンコードされたデータ
                import base64
                try:
                    data = base64.b64decode(value)
                    file_name = f"{key}.bin"
                    file_path = output_dir / file_name
                    file_path.write_bytes(data)
                    print(f"Base64 file saved: {file_path}")
                except Exception:
                    pass
    
    # 結果を標準出力に表示
    print("\n=== Execution Results ===")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(
        description="Keiri Agent CLI Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 基本的な実行
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml
  
  # ヘッドレスモードで実行
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml --headless
  
  # 変数を指定して実行
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml --vars '{"fiscal_year": "2025", "quarter": "Q1"}'
  
  # 設定ファイルから実行
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml --config execution_config.json
  
  # ファイル入力を指定
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml --files files_config.json
  
  # UIモック応答を指定
  python cli_runner.py designs/retirement_benefit_q1_2025.yaml --ui-mocks ui_mocks.json
        """
    )
    
    parser.add_argument(
        "plan_file", 
        help="Plan YAML file path"
    )
    
    parser.add_argument(
        "--headless", 
        action="store_true",
        help="Run in headless mode (no UI interaction)"
    )
    
    parser.add_argument(
        "--config", 
        help="Execution configuration JSON file"
    )
    
    parser.add_argument(
        "--vars", 
        help="Variables JSON file or JSON string"
    )
    
    parser.add_argument(
        "--files", 
        help="File inputs configuration JSON file"
    )
    
    parser.add_argument(
        "--ui-mocks", 
        help="UI mock responses JSON file"
    )
    
    parser.add_argument(
        "--output", 
        help="Output directory for results and files"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    try:
        # Planファイルの存在確認
        plan_path = Path(args.plan_file)
        if not plan_path.exists():
            print(f"Error: Plan file not found: {plan_path}")
            sys.exit(1)
        
        if args.verbose:
            print(f"Loading plan from: {plan_path}")
        
        # Plan読み込み
        plan = load_plan(plan_path)
        
        if args.verbose:
            print(f"Plan loaded: {plan.id} (version: {plan.version})")
            print(f"Nodes: {len(plan.graph)}")
        
        # 実行コンテキスト構築
        execution_context = build_execution_context(args)
        
        if args.verbose:
            print(f"Execution context: {execution_context.to_dict()}")
        
        # ブロックレジストリ初期化
        registry = BlockRegistry()
        registry.load_specs()
        
        if args.verbose:
            print(f"Block registry loaded: {len(registry.specs_by_id)} blocks")
        
        # 実行
        runner = PlanRunner(
            registry=registry, 
            default_ui_hitl=False
        )
        
        if args.verbose:
            print("Starting plan execution...")
        
        results = runner.run(
            plan, 
            vars_overrides=execution_context.vars_overrides,
            execution_context=execution_context
        )
        
        if args.verbose:
            print("Plan execution completed successfully")
        
        # 結果出力
        output_results(results, execution_context.output_dir, plan.id)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
