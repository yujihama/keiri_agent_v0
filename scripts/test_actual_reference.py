#!/usr/bin/env python
import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

print(f"Project root: {PROJECT_ROOT}")

# 実際の実行結果を読み込んで確認
artifact_path = PROJECT_ROOT / "headless/output/nlp_compare_fixed/text_similarity_compare_two_files/2025-09-05T16-01-00/artifacts"
print(f"Artifact path: {artifact_path}")
print(f"Path exists: {artifact_path.exists()}")

# embed_a の出力を確認
embed_a_path = artifact_path / "embed_a_outputs.json"
print(f"\nembed_a path: {embed_a_path}")
print(f"File exists: {embed_a_path.exists()}")

if embed_a_path.exists():
    with open(embed_a_path, 'r', encoding='utf-8') as f:
        embed_a_data = json.load(f)
    
    print("embed_a output structure:")
    print(f"Type: {type(embed_a_data)}")
    print(f"Keys: {list(embed_a_data.keys()) if isinstance(embed_a_data, dict) else 'Not a dict'}")
    
    if isinstance(embed_a_data, dict) and 'items' in embed_a_data:
        items = embed_a_data['items']
        print(f"\nitems type: {type(items)}")
        print(f"items length: {len(items) if isinstance(items, list) else 'Not a list'}")
        
        if isinstance(items, list) and len(items) > 0:
            first_item = items[0]
            print(f"\nFirst item type: {type(first_item)}")
            print(f"First item keys: {list(first_item.keys()) if isinstance(first_item, dict) else 'Not a dict'}")
            
            if isinstance(first_item, dict) and 'embedding' in first_item:
                embedding = first_item['embedding']
                print(f"\nEmbedding type: {type(embedding)}")
                print(f"Embedding length: {len(embedding) if isinstance(embedding, list) else 'Not a list'}")
                print(f"First 5 values: {embedding[:5] if isinstance(embedding, list) else 'Not available'}")
    
    # 参照をテスト
    print("\n" + "="*50)
    print("Testing reference: ${embed_a.items.0.embedding}")
    
    try:
        # 実際の参照解決をシミュレート
        result = embed_a_data['items'][0]['embedding']
        print(f"Success! Got embedding with {len(result)} dimensions")
    except Exception as e:
        print(f"Failed to resolve reference: {e}")
        
else:
    print(f"File not found: {embed_a_path}")

# embed_b も確認
print("\n" + "="*50)
embed_b_path = artifact_path / "embed_b_outputs.json"
if embed_b_path.exists():
    with open(embed_b_path, 'r', encoding='utf-8') as f:
        embed_b_data = json.load(f)
    
    print("embed_b output structure:")
    if isinstance(embed_b_data, dict) and 'items' in embed_b_data:
        items = embed_b_data['items']
        print(f"items length: {len(items) if isinstance(items, list) else 'Not a list'}")
