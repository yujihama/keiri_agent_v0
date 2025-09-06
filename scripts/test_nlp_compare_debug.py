import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.plan.reader import PlanReader
from core.plan.executor import ExecutionContext
from core.plan.runner import Runner
from core.ui.logging import set_headless_logging

def main():
    set_headless_logging(verbose=True)
    
    # プラン読み込み
    plan_file = "designs/text_similarity_compare_two_files.yaml"
    plan = PlanReader.read_plan(plan_file)
    
    # テストデータ準備
    with open("tests/data/nlp_compare/A.txt", "rb") as f:
        file_a_bytes = f.read()
    with open("tests/data/nlp_compare/B.txt", "rb") as f:
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
    exec_ctx = ExecutionContext(
        output_dir="headless/output/debug_nlp_compare",
        ui_mocks=ui_mocks,
        is_headless=True
    )
    
    # ランナー実行
    runner = Runner()
    
    try:
        # chunk_aの前まで実行
        for node in plan.graph.nodes:
            print(f"\n=== Executing node: {node.id} ===")
            ctx = runner._create_node_context(plan.id, node, exec_ctx)
            block = runner._get_block_instance(node.block)
            
            # 入力の準備
            inputs = {}
            for key, ref in node.inputs.items():
                val = runner._resolve_input_value(ref, ctx, runner._exec_state)
                inputs[key] = val
                
            # chunk_aブロックの直前で入力を詳しく見る
            if node.id == "chunk_a":
                print(f"Inputs for chunk_a:")
                print(f"  files type: {type(inputs.get('files'))}")
                print(f"  files value: {json.dumps(inputs.get('files'), indent=2)}")
                
            # ブロック実行
            outputs = block.run(ctx, inputs)
            
            # 状態を更新
            runner._exec_state["outputs"][node.id] = outputs
            
            # chunk_aで止める（エラーが出る前）
            if node.id == "chunk_a":
                break
                
    except Exception as e:
        print(f"\nError occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
