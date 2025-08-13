# 設計と実装のギャップ分析および修正計画

## 調査サマリー

設計書（`design.md`）と現在の実装を比較した結果、以下のギャップが確認されました。

## 1. UIブロックの統一状況

### 現状
- `ui.interactive_input` ブロックは実装済み
- しかし、レガシーUIブロックがまだ存在:
  - `ui.file_uploader.evidence_zip`
  - `ui.file_uploader.excel`
  - `ui.confirmation`
  - `ui.placeholder`

### ギャップ
- 設計では`ui.interactive_input`を中核コンポーネントとして統一することになっているが、完全に移行されていない

## 2. LLM処理（ai.process_llm）

### 現状
- `ai.process_llm` ブロックは実装済み
- Pydanticとstructured outputで型安全に処理されている
- 動的なPydanticモデル生成により、Planで指定されたスキーマに準拠した出力を返す

### ギャップ
- 設計に沿って実装されており、大きなギャップはない

## 3. ブロック仕様定義（YAML）

### 現状のYAML構造
```yaml
id: <ブロック識別子>
version: <バージョン>
entrypoint: <Pythonモジュール:クラス名>
inputs:
  <入力名>:
    type: <型>
    description: <説明>
outputs:
  <出力名>:
    type: <型>
requirements: []
description: <説明>
```

### ギャップ
設計書に記載されているが実装されていない項目:
- 入力項目の `required` フィールド
- 入力項目の `default` フィールド
- 入力項目の `validation` フィールド
- `examples` フィールド
- `dry_run` セクション（samples）

## 4. Plan定義言語（DSL）

### 現状
- 基本的な構造は実装済み
- foreach、while、whenなどの制御構造は実装済み

### ギャップ
- 現在のNodeモデルに不要なフィールドが多い（type、max_workers、priority、hitlなどがnullで出力される）
- 設計書の簡潔な構造と比べて冗長

## 5. 実行エンジンとSession State管理

### 現状
- 実行エンジンは実装済み
- Session Stateは各UIブロック内で独自に管理

### ギャップ
- 設計書に記載されている統一的なSession State管理の命名規則が実装されていない:
  ```python
  f"plan:{plan_id}::node:{node_id}::v{block_version}"
  ```
- Session Stateライフサイクル管理が体系化されていない

## 6. エラー設計

### 現状
- 単純なException処理のみ
- エラーメッセージをeventとして記録

### ギャップ
- 構造化エラー（BlockError）クラスが未実装
- エラーコード体系が未実装
- エラーの詳細情報（hint、recoverable、input_snapshot）が未実装

## 修正計画

### フェーズ1: 基盤の整備（優先度：高）

#### 1.1 エラー設計の実装
- `core/errors.py` を作成し、BlockErrorクラスとエラーコード体系を実装
- 各ブロックでBlockErrorを使用するように修正
- エラーハンドリングの統一

#### 1.2 Session State管理の統一
- `core/ui/session_state.py` を作成（設計書に記載あり）
- 統一的な命名規則の実装
- ステートライフサイクル管理の実装

#### 1.3 ブロック仕様定義の拡張
- BlockSpecモデルを拡張（required、default、validation、examples、dry_run）
- 既存のYAMLファイルを更新

### フェーズ2: UIブロックの統合（優先度：中）

#### 2.1 レガシーUIブロックの移行
- レガシーUIブロックの機能を`ui.interactive_input`に統合
- 移行ツールの作成（設計書に記載）
- 既存のPlanファイルの自動変換

#### 2.2 UIブロック統合後のテスト
- 統合されたUIブロックの動作確認
- 既存機能の互換性確認

### フェーズ3: Plan DSLの最適化（優先度：低）

#### 3.1 Nodeモデルの簡素化
- 不要なフィールドの削除または optional にして出力時に除外
- Plan生成時の最適化

#### 3.2 バリデーションの強化
- dry_run機能の完全実装
- サンプルデータを使用したバリデーション

### 実装スケジュール案

1. **第1週**: フェーズ1.1（エラー設計）、フェーズ1.2（Session State管理）
2. **第2週**: フェーズ1.3（ブロック仕様拡張）、テスト作成
3. **第3週**: フェーズ2.1（UIブロック統合）開始
4. **第4週**: フェーズ2.2（統合テスト）、フェーズ3（最適化）

### 追加の考慮事項

1. **後方互換性**: 既存のPlanファイルが動作し続けるよう、移行期間を設ける
2. **段階的移行**: 一度にすべてを変更せず、段階的に移行
3. **ドキュメント更新**: 実装と並行して、APIドキュメントや使用例を更新
4. **テストカバレッジ**: 各フェーズで十分なテストを作成

## 次のステップ

1. この修正計画のレビューと承認
2. 優先順位の確認と調整
3. フェーズ1の実装開始
