#!/usr/bin/env python
import sys
from pathlib import Path
import json

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.blocks.processing.matching.semantic_topk import SemanticTopKBlock
from core.blocks.base import BlockContext

# 実際の実行結果を読み込む
artifact_path = PROJECT_ROOT / "headless/output/nlp_compare_fixed/text_similarity_compare_two_files/2025-09-05T16-01-00/artifacts"

# embed_a と embed_b の出力を読み込む
with open(artifact_path / "embed_a_outputs.json", 'r', encoding='utf-8') as f:
    embed_a_data = json.load(f)

with open(artifact_path / "embed_b_outputs.json", 'r', encoding='utf-8') as f:
    embed_b_data = json.load(f)

print(f"embed_a items count: {len(embed_a_data['items'])}")
print(f"embed_b items count: {len(embed_b_data['items'])}")

# 参照を手動で解決
query_embedding = embed_a_data['items'][0]['embedding']
items = embed_b_data['items']

print(f"\nquery_embedding type: {type(query_embedding)}")
print(f"query_embedding length: {len(query_embedding)}")
print(f"items type: {type(items)}")
print(f"items length: {len(items)}")

# SemanticTopKブロックの入力を構築
test_input = {
    "query_embedding": query_embedding,
    "items": items,
    "metric": "cosine",
    "top_k": 3,
    "require_embeddings": True
}

print("\nTesting SemanticTopK block with manual input...")

# ブロックをテスト
block = SemanticTopKBlock()
ctx = BlockContext(
    run_id="test_run",
    workspace=str(PROJECT_ROOT),
    artifacts_dir=str(PROJECT_ROOT / "test_artifacts"),
    node_id="test_similarity_ab",
    plan_id="test_plan",
    vars={},
    inputs={},
    outputs={}
)

try:
    result = block.run(ctx, test_input)
    print("Success! Results:")
    print(f"  Number of results: {len(result.get('results', []))}")
    for i, r in enumerate(result.get('results', [])[:3]):
        print(f"  Result {i}: score={r.get('score', 'N/A'):.4f}, id={r.get('id', 'N/A')}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

# 参照文字列のテスト
print("\n" + "="*50)
print("Testing reference resolution...")

# プランで使用される参照文字列をシミュレート
ref_string = "${embed_a.items.0.embedding}"
print(f"Reference: {ref_string}")

# 実行時の状態をシミュレート
runtime_outputs = {
    "embed_a": embed_a_data,
    "embed_b": embed_b_data
}

# 単純な参照解決をシミュレート
def resolve_reference(ref, outputs):
    if ref.startswith("${") and ref.endswith("}"):
        path = ref[2:-1]
        parts = path.split(".")
        current = outputs
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                try:
                    idx = int(part)
                    current = current[idx]
                except (ValueError, IndexError):
                    return None
            else:
                return None
        
        return current
    return ref

resolved = resolve_reference(ref_string, runtime_outputs)
print(f"Resolved type: {type(resolved)}")
if isinstance(resolved, list):
    print(f"Resolved length: {len(resolved)}")
    print(f"First few values: {resolved[:3]}")
