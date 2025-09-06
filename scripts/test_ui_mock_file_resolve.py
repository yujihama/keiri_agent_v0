#!/usr/bin/env python
import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.plan.execution_context import ExecutionContext

def main():
    # ExecutionContextを作成
    exec_ctx = ExecutionContext(
        headless_mode=True,
        file_inputs={
            "file_a": Path("tests/data/nlp_compare/A.txt"),
            "file_b": Path("tests/data/nlp_compare/B.txt")
        },
        ui_mock_responses={
            "ui.interactive_input": {
                "upload_files": {
                    "collected_data": {
                        "file_a": "auto_resolve",
                        "file_b": "auto_resolve"
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
    )
    
    # UIモックレスポンスを取得
    mock_response = exec_ctx.get_ui_mock_response("ui.interactive_input", "upload_files")
    print("Mock response before processing:")
    print(json.dumps(mock_response, indent=2))
    
    # auto_resolveの処理をシミュレート
    if mock_response:
        cd = mock_response.get("collected_data", {})
        resolved = {}
        for field_id, value in cd.items():
            if value == "auto_resolve":
                file_data = exec_ctx.resolve_file_input(field_id)
                if file_data:
                    print(f"\n{field_id}: Successfully resolved to {len(file_data)} bytes")
                    resolved[field_id] = file_data
                else:
                    print(f"\n{field_id}: Failed to resolve")
                    resolved[field_id] = None
            else:
                resolved[field_id] = value
        
        print("\nResolved data types:")
        for k, v in resolved.items():
            print(f"  {k}: {type(v)} ({len(v) if isinstance(v, bytes) else 'N/A'} bytes)")

if __name__ == "__main__":
    main()
