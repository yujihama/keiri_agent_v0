# ヘッドレス実行デバッグガイド

このガイドは、`text_similarity_compare_two_files.yaml`プランのデバッグ作業から得られた知見をまとめています。

## デバッグ時の効果的な手順

### 1. エラーメッセージの詳細確認

```bash
# verbose オプションで詳細なログを出力
python headless/cli_runner.py <plan.yaml> --headless --verbose

# 出力をファイルに保存して後で詳細分析
python headless/cli_runner.py <plan.yaml> --headless --verbose 2>&1 | Out-File -FilePath debug_output.txt -Encoding UTF8
```

**ポイント:**
- エラーの発生箇所と内容を正確に把握
- スタックトレースから問題のブロックを特定
- 実行コンテキストの状態も確認

### 2. アーティファクトの段階的確認

```
headless/output/<実行名>/<タイムスタンプ>/artifacts/
├── <block_id>_outputs.json    # 各ブロックの出力
├── <block_id>_inputs.json     # 各ブロックの入力（デバッグ時）
└── ...
```

**確認手順:**
1. 実行されたブロックの出力を順番に確認
2. データの流れと変換を追跡
3. 期待する形式と実際の出力を比較

### 3. 最小限のテストケース作成

```python
# scripts/test_<block_name>.py
#!/usr/bin/env python
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.blocks.<category>.<block_name> import <BlockClass>
from core.blocks.base import BlockContext

def test_block():
    # 実際のデータを使用してテスト
    test_input = { ... }
    block = <BlockClass>()
    ctx = BlockContext(...)
    
    result = block.run(ctx, test_input)
    print(f"Result: {result}")

if __name__ == "__main__":
    test_block()
```

### 4. 関連コードの調査

```bash
# ブロックの実装を確認
find core/blocks -name "*<block_name>*" -type f

# 期待する入力形式を確認
grep -r "inputs" core/blocks/processing/<block_name>/

# エラーメッセージの発生箇所を特定
grep -r "<エラーメッセージ>" core/
```

### 5. 段階的な修正と検証

**修正フロー:**
1. 一つの問題に集中して修正
2. 修正後は必ず動作確認
3. 新たな問題が発生していないか確認
4. 成功したら次の問題に進む

## 注意点とトラブルシューティング

### 1. デフォルト設定ファイルの影響

**問題:** プラン専用の設定が意図しないデフォルト設定で上書きされる

```json
// headless/configs/ui_mocks.json (デフォルト)
{
  "ui.interactive_input": {
    "upload_files": {
      "collected_data": {
        "file_a": "C:/path/to/default/file.txt",  // ← これが原因
        "file_b": "auto_resolve"
      }
    }
  }
}
```

**対策:**
- デフォルト設定ファイルの内容を確認
- 競合する設定を削除またはコメントアウト
- プラン専用の設定ファイルを使用

### 2. 参照解決の仕組み

**正しい参照方法:**
```yaml
# 基本形
output: "${node_id.output_field}"

# ネストした参照
output: "${node_id.output.nested.field}"

# 配列インデックス（修正後）
output: "${node_id.items.0.field}"

# 複雑な構造
output: "${node_id.results.items.0.embedding}"
```

**よくある間違い:**
```yaml
# ❌ 間違い: 配列インデックスが解決されない（修正前）
output: "${embed_a.items.0.embedding}"

# ✅ 正解: 適切なデータ構造の参照
output: "${embed_a.items.0.embedding}"  # PlanRunner修正後
```

### 3. UIモックの`auto_resolve`

```json
{
  "ui.interactive_input": {
    "upload_files": {
      "collected_data": {
        "file_a": "auto_resolve",  // ✅ 正解
        "file_b": "auto_resolve"   // ファイル入力と自動的に紐付け
      },
      "approved": true,
      "metadata": {
        "submitted": true,
        "mode": "collect"
      }
    }
  }
}
```

**重要:**
- `--files`オプションで指定したファイルと自動的にマッピング
- ファイルパスを直接指定しない
- `auto_resolve`文字列を使用

### 4. ブロック間のデータ形式

```python
# 例: transforms.flatten_items
# 入力期待値
{
  "results_list": [
    {"results": {"items": [...]}},  # LLMブロックの出力
    {"results": {"items": [...]}}
  ]
}

# 出力
{
  "items": [...]  # フラット化された結果
}
```

**注意点:**
- 各ブロックの入出力形式を`block_specs/`で確認
- ラッパーオブジェクトの有無に注意
- データ変換の必要性を検討

### 5. エラーハンドリングとプラン設計

```yaml
# 並行実行を避ける場合
steps:
  - id: step1
    block: ...
    
  - id: step2  # step1の完了後に実行
    block: ...
    in:
      data: "${step1.output}"
```

**ベストプラクティス:**
- 依存関係のあるブロックは適切に順序付け
- エラー時もアーティファクトが残るように設計
- 重要なデータは中間結果として保存

### 6. PowerShell環境での注意

```powershell
# ✅ 正解: 仮想環境のアクティベート
.\venv\Scripts\activate

# ✅ 正解: コマンドの連結
cd path; python script.py

# ❌ 間違い: && は PowerShell で使用不可
cd path && python script.py
```

## デバッグ用ツールとコマンド

### 1. 実行ログの分析

```powershell
# 最新の実行結果を確認
Get-ChildItem headless/output/ | Sort-Object LastWriteTime -Descending | Select-Object -First 1

# 特定のブロックの出力を確認
Get-Content "headless/output/<run>/artifacts/<block>_outputs.json" | ConvertFrom-Json
```

### 2. 参照解決のテスト

```python
# scripts/test_reference_resolution.py
def test_reference(node_outputs, reference_string):
    """参照解決のテスト"""
    # PlanRunnerのresolve関数をテスト
    pass
```

### 3. ブロック単体テスト

```python
# scripts/test_block_standalone.py
def test_block_with_real_data():
    """実際のアーティファクトデータを使用したテスト"""
    pass
```

## トラブルシューティングチェックリスト

### エラー発生時の確認事項

- [ ] エラーメッセージの完全な内容を確認
- [ ] 最後に成功したブロックを特定
- [ ] アーティファクトファイルの存在と内容を確認
- [ ] デフォルト設定ファイルとの競合をチェック
- [ ] 参照の構文と対象データ構造を確認
- [ ] 仮想環境がアクティブかを確認

### 修正後の検証事項

- [ ] エラーが解消されている
- [ ] 期待する出力が生成されている
- [ ] 他のブロックに副作用がない
- [ ] 最終的な結果ファイルが正常

## 参考情報

### 関連ファイル
- `core/plan/runner.py` - 参照解決の実装
- `core/blocks/base.py` - ブロック基底クラス
- `headless/cli_runner.py` - CLI実行ツール
- `block_specs/` - ブロック仕様書

### 有用なコマンド
```bash
# プロジェクト内検索
grep -r "pattern" core/
find . -name "*.py" -exec grep -l "pattern" {} \;

# ログ分析
tail -f headless/output/debug.log
grep -A 5 -B 5 "ERROR" headless/output/debug.log
```

このガイドを参考に、効率的なデバッグを行ってください。
