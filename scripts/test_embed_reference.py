#!/usr/bin/env python
import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.plan.loader import load_plan
from core.plan.runner import PlanRunner
from core.blocks.registry import BlockRegistry
from core.plan.execution_context import ExecutionContext

def debug_reference_resolution():
    # プラン読み込み
    plan_file = PROJECT_ROOT / "designs/text_similarity_compare_two_files.yaml"
    plan = load_plan(plan_file)
    
    # テスト用のデータ（前回の実行結果から）
    embed_a_output = {
        "items": [{
            "id": "0-0",
            "source": "A.txt",
            "start": 0,
            "end": 146,
            "text": "Apple releases new iPhone...",
            "tokens": 31,
            "embedding": [0.1, 0.2, 0.3, 0.4, 0.5]  # 簡略化
        }],
        "summary": {"count": 1, "model": "openai-embed:text-embedding-3-large"}
    }
    
    # 実行状態をシミュレート
    exec_state = {
        "outputs": {
            "embed_a": embed_a_output
        }
    }
    
    # 参照文字列
    ref_string = "${embed_a.items.0.embedding}"
    
    print(f"Reference string: {ref_string}")
    print(f"\nExecution state outputs:")
    print(json.dumps(exec_state, indent=2))
    
    # 参照を解決する処理をシミュレート
    try:
        # 簡単な参照解決の実装
        if ref_string.startswith("${") and ref_string.endswith("}"):
            path = ref_string[2:-1]  # ${ と } を削除
            parts = path.split(".")
            
            print(f"\nResolving path: {parts}")
            
            # outputsから開始
            current = exec_state["outputs"]
            for i, part in enumerate(parts):
                print(f"  Step {i}: Looking for '{part}' in {type(current)}")
                
                if isinstance(current, dict):
                    if part in current:
                        current = current[part]
                        print(f"    Found: {type(current)}")
                    else:
                        print(f"    Not found! Available keys: {list(current.keys())}")
                        break
                elif isinstance(current, list):
                    try:
                        idx = int(part)
                        if 0 <= idx < len(current):
                            current = current[idx]
                            print(f"    Found at index {idx}: {type(current)}")
                        else:
                            print(f"    Index out of range! List length: {len(current)}")
                            break
                    except ValueError:
                        print(f"    Error: '{part}' is not a valid index")
                        break
                else:
                    print(f"    Error: Cannot access '{part}' on type {type(current)}")
                    break
            
            print(f"\nFinal result: {current}")
            print(f"Type: {type(current)}")
            
    except Exception as e:
        print(f"\nError during resolution: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_reference_resolution()
