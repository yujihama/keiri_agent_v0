#!/usr/bin/env python
import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

print(f"Python path: {sys.path[0]}")
print(f"Current dir: {os.getcwd()}")

try:
    from core.plan.execution_context import ExecutionContext
    print("Import successful")
    
    # ファイルパスが存在するか確認
    file_a = PROJECT_ROOT / "tests/data/nlp_compare/A.txt"
    file_b = PROJECT_ROOT / "tests/data/nlp_compare/B.txt"
    
    print(f"\nFile A exists: {file_a.exists()}")
    print(f"File B exists: {file_b.exists()}")
    
    if file_a.exists():
        content_a = file_a.read_bytes()
        print(f"File A size: {len(content_a)} bytes")
        print(f"File A content preview: {content_a[:50]}...")
        
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
