#!/usr/bin/env python
import os
import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.plan.execution_context import ExecutionContext

def main():
    # プラン読み込み
    plan_file = PROJECT_ROOT / "designs/text_similarity_compare_two_files.yaml"
    plan = load_plan(plan_file)
    
    # テストデータ準備
    with open(PROJECT_ROOT / "tests/data/nlp_compare/A.txt", "rb") as f:
        file_a_bytes = f.read()
    with open(PROJECT_ROOT / "tests/data/nlp_compare/B.txt", "rb") as f:
        file_b_bytes = f.read()
    
    # UIモック設定
    ui_mocks = {
        "ui.interactive_input": {
            "upload_files": {
                "collected_data": {
                    "file_a": file_a_bytes,
                    "file_b": file_b_bytes
                },
                "approved": True,
                "response": None,
                "metadata": {
                    "submitted": True,
                    "mode": "collect"
                }
            }
        }
    }
    
    # 実行コンテキスト作成
    output_dir = PROJECT_ROOT / "headless/output/debug_nlp"
    execution_context = ExecutionContext(
        output_dir=str(output_dir),
        ui_mocks=ui_mocks,
        is_headless=True
    )
    
    # ランナー実行
    runner = PlanRunner()
    
    # 部分実行で入力を確認
    try:
        results = runner.run(plan, execution_context=execution_context)
    except Exception as e:
        print(f"Error occurred: {e}")
        
        # runner内の状態を確認（内部実装に依存）
        if hasattr(runner, '_execution_state'):
            state = runner._execution_state
            
            # filter_aの出力を確認
            if "filter_a" in state.outputs:
                print("\nfilter_a outputs:")
                filter_output = state.outputs["filter_a"]
                print(json.dumps(filter_output, indent=2))
                
            # filter_bの出力を確認
            if "filter_b" in state.outputs:
                print("\nfilter_b outputs:")
                filter_output = state.outputs["filter_b"]
                print(json.dumps(filter_output, indent=2))
                
            # extract_textsの出力も確認
            if "extract_texts" in state.outputs:
                print("\nextract_texts outputs (first 200 chars):")
                extract_output = state.outputs["extract_texts"]
                print(str(extract_output)[:200] + "...")

if __name__ == "__main__":
    main()