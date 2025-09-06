#!/usr/bin/env python
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.blocks.base import BlockContext
from core.blocks.processing.nlp.chunk_texts import ChunkTextsBlock

def main():
    # テストデータ（filterブロックの出力を模倣）
    test_input = {
        "files": [{
            "name": "A.txt",
            "ext": ".txt", 
            "size": 146,
            "text_excerpt": "Apple releases new iPhone with improved camera and battery life. It features A18 chip and iOS 18. Pricing starts at $799. Availability next month."
        }],
        "strategy": "tokens",
        "max_tokens": 300,
        "overlap_tokens": 40
    }
    
    # ブロックインスタンス作成
    block = ChunkTextsBlock()
    
    # 実行コンテキスト
    ctx = BlockContext(
        run_id="test_run_001",
        workspace=str(PROJECT_ROOT),
        vars={}
    )
    
    try:
        # ブロック実行
        print("Running chunk_texts block with test data...")
        print(f"Input keys: {list(test_input.keys())}")
        print(f"Files input type: {type(test_input.get('files'))}")
        print(f"Files input content: {test_input.get('files')}")
        
        result = block.run(ctx, test_input)
        
        print("\nSuccess! Output:")
        print(f"Output keys: {list(result.keys())}")
        print(f"Number of chunks: {len(result.get('chunks', []))}")
        if result.get('chunks'):
            print(f"First chunk text: {result['chunks'][0].get('text', '')[:100]}...")
            
    except Exception as e:
        print(f"\nError occurred: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()