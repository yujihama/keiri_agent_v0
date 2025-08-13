# 汎用業務自動化ツール 設計書

## 目次
1. [全体](#全体)
   - [フロー](#フロー)
   - [設計思想](#設計思想)
   - [拡張性原則](#拡張性原則)
2. [全体UI](#全体ui)
3. [ブロック](#ブロック)
   - [設計概要](#設計概要)
   - [ブロック仕様定義（YAML）](#ブロック仕様定義yaml)
   - [UIブロック](#uiブロック)
   - [Processブロック](#processブロック)
   - [ブロック拡張ガイドライン](#ブロック拡張ガイドライン)
4. [業務設計](#業務設計)
   - [Plan定義言語（DSL）](#plan定義言語dsl)
   - [Plan生成プロセス](#plan生成プロセス)
   - [拡張ポイント](#拡張ポイント)
5. [業務実施](#業務実施)
   - [実行エンジン](#実行エンジン)
   - [実行ポリシー](#実行ポリシー)
   - [実行時の可観測性](#実行時の可観測性)
6. [エラー設計](#エラー設計)
7. [拡張性設計](#拡張性設計)
8. [セキュリティ設計](#セキュリティ設計)
9. [将来の拡張構想](#将来の拡張構想)

---

# 全体
## フロー
 - 業務設計、業務実施の2つのフェーズに分かれる。
 - 業務設計では、プランのyamlファイルを生成し、ドライランが完了まで行う。
 - 業務実施では、プランを選択して実行すると業務（処理）が実行され、プランに沿ってUIでやり取りや結果生成がされる。
 - 一連の操作はログとして保持される。

## 設計思想
- UIは `ui.interactive_input` を中核コンポーネントとして統一する。
- セッション永続: すべてのUI入力は Streamlit Session State に保存し、再実行や画面更新でも値や描画をクリアしない。
- LLMを用いた処理はpydanticとstructured outputで型安全に処理をする。
- I/O契約の明文化: 各UI/Processingブロックは、必須/任意/既定値/バリデーション/型を YAML で構造化定義する。
- LLM駆動のPlan生成: LLMは BlockCatalog（YAML定義の集合）を参照して Plan YAML を生成する。
- 厳密検証とドライラン: 生成後はスキーマ/依存/I-O整合/参照解決の検証と、宣言されたサンプル/モックによるドライランを実施。
- 型安全な受け渡し: 参照解決後のノード I/O は JSON Schema/Pydantic で静的・動的に検証する。
- フォールバック禁止: 不備やエラーは黙って吸収せず、構造化エラーとしてUIに返す（失敗を可視化）。

## 拡張性原則
- プラグイン指向: 新しいブロックは既存コードを変更せずに追加可能。
- 段階的拡張: 基本機能から高度な機能へ段階的に拡張できる設計。
- ドメイン非依存: 会計以外の業務にも適用可能な汎用的な設計。
- エコシステム対応: 外部システムとの連携を容易にするインターフェース設計。

# 全体UI
- 業務固有のUI/UXは保持しない。業務固有のものはUIブロックに定義し、プランより選択される。

# ブロック
## 設計概要
- UIブロックとProcessブロックに区分される
- すべてのブロックは `block_specs/**/*.yaml` に仕様を定義します。
- ブロックは自己完結型で、依存関係は入出力のみで表現される。

## ブロック仕様定義（YAML）
各ブロックは以下の構造で定義されます：
```yaml
id: <ブロック識別子>
version: <セマンティックバージョン>
entrypoint: <Pythonモジュール:クラス名>
inputs:
  <入力名>:
    type: <JSON Schema型>
    description: <説明>
    required: <true/false>
    default: <既定値>
    validation: <追加検証ルール>
outputs:
  <出力名>:
    type: <JSON Schema型>
    description: <説明>
requirements: <実行時要件>
description: <ブロックの説明>
examples: <使用例>
dry_run:
  samples: <ドライラン用サンプルデータ>
```

### UIブロック
- 原則は`ui.interactive_input`を使用
- 足りない機能がある場合のみ、固有のUIブロックを作成可能。
- UIブロックの標準インターフェース：
  ```python
  def render(ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
      # ctx: 実行コンテキスト（run_id、workspace、vars）
      # inputs: ブロックへの入力
      # returns: collected_data, approved, response, metadata
  ```

### Processブロック
- LLMで処理をする場合は`ai.process_llm`を原則使用する。
- 固有処理のブロックはできるだけ作成せず、汎用的なブロックを作成してパラメータでコントロールする設計とする。
- Processブロックの標準インターフェース：
  ```python
  def run(ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
      # ctx: 実行コンテキスト
      # inputs: ブロックへの入力
      # returns: 定義された出力
  ```

## ブロック拡張ガイドライン
### 新規ブロック作成時の考慮事項
1. **汎用性**: 特定業務に依存しない設計
2. **パラメータ化**: 振る舞いはパラメータで制御
3. **エラーハンドリング**: 構造化エラーの返却
4. **テスタビリティ**: dry_run対応、モック可能な設計
5. **ドキュメント**: 入出力の詳細な説明とサンプル

### カテゴリ別ブロック設計指針
- **ファイル処理**: 様々な形式に対応できる汎用設計
- **データ変換**: 入力から出力へのマッピングを柔軟に定義可能
- **外部連携**: APIやデータベースとの接続を抽象化
- **AI/ML処理**: プロンプトとモデル設定を外部化

# 業務設計
## 設計概要
- LLMが各ブロックの定義を参照し、プランを生成する。
- ドライラン成功時のみ保存可能。
- loop/foreach, whenも可能。

## Plan定義言語（DSL）
### 基本構造
```yaml
apiVersion: v1
id: <プラン識別子>
version: <バージョン>
vars:
  <変数名>: <値>
policy:
  on_error: <halt|continue|retry>
  retries: <リトライ回数>
  timeout_ms: <タイムアウト>
  concurrency:
    default_max_workers: <並列数>
ui:
  layout: [<UIノードの表示順>]
graph:
  - id: <ノードID>
    block: <ブロックID>
    in:
      <入力名>: <値または参照>
    out:
      <出力名>: <エイリアス>
    when: <条件>
```

### 参照式
- `${nodeId.alias}`: 他ノードの出力参照
- `${vars.key}`: プラン変数参照
- `${env.KEY}`: 環境変数参照
- `${config.path.to.value}`: 設定値参照

### 制御構造
#### 条件分岐（when）
```yaml
when:
  expr: "${someValue} > 10 and ${otherValue} == 'active'"
  # または
  left: "${someValue}"
  op: "gt"  # eq, ne, gt, gte, lt, lte
  right: 10
```

#### 反復処理（foreach）
```yaml
- id: process_items
  type: loop
  foreach:
    input: "${data.items}"  # 配列またはオブジェクト
    itemVar: item          # 各要素を束縛する変数名
    indexVar: idx          # インデックス（省略可）
    max_concurrency: 4     # 並列実行数
  body:
    plan:
      graph: [...]
      exports:
        - from: <ノードID.出力>
          as: <エクスポート名>
  out:
    collect: <収集する出力名>
```

#### 条件ループ（while）
```yaml
- id: retry_process
  type: loop
  while:
    condition:
      expr: "${status} != 'success'"
    max_iterations: 5  # 必須：無限ループ防止
  body:
    plan:
      graph: [...]
```

#### サブフロー
```yaml
- id: call_subplan
  type: subflow
  call:
    plan_id: <プランID or パス>
    inputs:
      <入力名>: <値>
  out:
    exports:
      - from: <出力名>
        as: <エイリアス>
```

## Plan生成プロセス
### 1. 要件分析
- ユーザー指示の解析
- 参考文書からの情報抽出
- 必要なブロックの特定

### 2. LLM駆動生成
#### 入力処理
- ユーザー指示テキスト（業務の目的/制約/優先度等）
- 手順書/マニュアル/規定類のアップロード（pdf, docx, xlsx, md, txt）
- テキスト抽出と正規化（FileProcessor/TextExtractorの利用）

#### LLM処理詳細
- BlockCatalogをJSON Schema化してコンテキストに含める
- GPT-4.1（またはAzure OpenAI）+ Structured Outputで型安全な生成
- Pydantic Output Parserによる構造化データの受領
- 生成スキーマ例：
  ```json
  {
    "tasks": [{"name": "...", "block_id": "...", "inputs": {}, "outputs": {}}],
    "ui": [{"type": "file_uploader|confirmation|select", "id": "...", "bind": {}}],
    "flow": [{"from": "nodeA", "to": "nodeB", "when": "..."}],
    "vars": {"output_config": {}},
    "placeholders": ["vars.output_config", "..."]
  }
  ```

#### 出力と後処理
- 未解決入力は `${vars.*}` プレースホルダで明示
- Plan YAMLを `designs/<slug>_<yyyymmddHHMM>.yaml` に保存
- 設計レポート（未解決項目/警告/採用ブロック一覧）の生成

### 3. 検証フェーズ
- スキーマ検証: Plan構造の妥当性
- 参照検証: すべての参照が解決可能か
- DAG検証: 循環参照がないか
- 型検証: 入出力の型整合性
- UI整合性: UIレイアウトとグラフの対応

### 4. ドライラン
- モックデータでの実行シミュレーション
- I/O連携の健全性確認
- エラーケースの検出
- Excel疎通確認（ExcelManagerでの仮書込検証）
- ドライラン用サンプルデータの活用:
  - 各ブロックの `dry_run.samples` を使用
  - サンプル未定義の場合は明示的に失敗（フォールバック禁止）

## 拡張ポイント
### カスタムバリデーター
- ドメイン固有の検証ルール追加
- 組織ポリシーの適用

### Plan最適化
- 並列実行可能なノードの自動検出
- リソース効率の最適化

### バージョン管理
- Planの変更履歴管理
- 破壊的変更の検出と警告

# 業務実施
## 設計概要
- 選択したプランを元に業務実施。
- ユーザー入力やボタン押下後に画面がクリアされないように、描画を保持する設計とする。

## 実行エンジン
### 実行戦略
- **トポロジカル順序**: DAGの依存関係に基づく実行順序決定
- **並列実行**: 依存関係のないノードの並列処理
- **条件実行**: when条件による動的な実行制御
- **エラー処理**: ポリシーに基づくエラーハンドリング

### Session State管理
#### キー命名規則
```python
# ノード単位のステート管理
f"plan:{plan_id}::node:{node_id}::v{block_version}"

# グローバルステート
f"plan:{plan_id}::global::{key}"
```

#### ステートライフサイクル
1. **初期化**: ノード実行前に必要なステートを初期化
2. **更新**: ユーザー操作時の即時反映
3. **永続化**: 画面再描画でも値を保持
4. **クリーンアップ**: Plan完了時の選択的クリア

### UIレンダリング戦略
- **プログレッシブレンダリング**: 実行済みノードの結果を保持
- **インクリメンタル更新**: 変更部分のみの再描画
- **エラー表示の永続化**: エラー状態の明示的な保持

## 実行ポリシー
### エラーハンドリング
```yaml
policy:
  on_error: halt      # 即座に停止（既定）
                     # continue: エラーノードをスキップ
                     # retry: 指定回数リトライ
  retries: 3         # リトライ回数
  retry_delay_ms: 1000  # リトライ間隔
  timeout_ms: 300000    # ノードタイムアウト
```

### 並列実行制御
```yaml
concurrency:
  default_max_workers: 4
  per_node:           # ノード別の制御
    heavy_process: 1  # 重い処理は直列化
    api_calls: 10     # API呼び出しは並列度を上げる
```

## 実行時の可観測性
### 構造化ログ
```json
{
  "event": "node_start",
  "plan_id": "invoice_reconciliation",
  "run_id": "run_12345",
  "node_id": "process_data",
  "timestamp": "2025-01-01T10:00:00Z",
  "context": {
    "user_id": "user_123",
    "session_id": "session_456"
  }
}
```

### メトリクス
- ノード実行時間
- リソース使用状況
- エラー率
- ユーザー待機時間

### トレーシング
- 実行パスの可視化
- ボトルネックの特定
- デバッグ情報の収集

# エラー設計
## エラー表現
### 構造化エラー（BlockError）
```python
class BlockError:
    code: str           # エラーコード
    message: str        # ユーザー向けメッセージ
    details: dict       # 詳細情報
    input_snapshot: dict # エラー時の入力
    hint: str          # 修正のヒント
    recoverable: bool  # 再実行可能か
```

### エラーコード体系
- `INPUT_*`: 入力関連エラー
  - `INPUT_VALIDATION_FAILED`: 検証失敗
  - `INPUT_TYPE_MISMATCH`: 型不一致
  - `INPUT_REQUIRED_MISSING`: 必須項目欠落
- `OUTPUT_*`: 出力関連エラー
  - `OUTPUT_SCHEMA_MISMATCH`: スキーマ不一致
  - `OUTPUT_GENERATION_FAILED`: 生成失敗
- `DEPENDENCY_*`: 依存関連エラー
  - `DEPENDENCY_NOT_FOUND`: 依存ノード未定義
  - `DEPENDENCY_FAILED`: 依存ノード失敗
- `EXTERNAL_*`: 外部要因エラー
  - `EXTERNAL_API_ERROR`: API呼び出し失敗
  - `EXTERNAL_TIMEOUT`: タイムアウト
  - `EXTERNAL_RATE_LIMIT`: レート制限

## エラー伝播
- 親子関係での伝播ルール
- エラーコンテキストの集約
- ユーザーへの適切な通知

# 拡張性設計
## プラグインアーキテクチャ
### ブロックプラグイン
```python
# プラグインインターフェース
class BlockPlugin:
    def register(self, registry: BlockRegistry):
        """ブロックをレジストリに登録"""
    
    def get_specs(self) -> List[BlockSpec]:
        """ブロック仕様を返す"""
```

### 拡張ポイント
1. **カスタムブロック**: 新規ブロックの追加
2. **バリデーター**: 検証ルールの拡張
3. **実行フック**: 実行前後の処理挿入
4. **ストレージ**: データ永続化の実装切替
5. **認証/認可**: セキュリティレイヤーの追加

## インテグレーション
### 外部システム連携
- REST API連携ブロック
- データベース接続ブロック
- メッセージキュー連携
- ファイルストレージ連携

### イベント駆動
```python
# イベントインターフェース
class Event:
    type: str
    payload: dict
    timestamp: datetime

# イベントハンドラー
class EventHandler:
    def handle(self, event: Event):
        """イベント処理"""
```

# セキュリティ設計
## 監査
- **操作ログ**: すべての操作の記録（JSONLフォーマット）
- **変更追跡**: Plan/データの変更履歴
- **コンプライアンス**: 規制要件への対応
- **実行証跡**: `runs/<plan>/<timestamp>.jsonl` での完全な実行記録

# 将来の拡張構想
## 高度な機能
1. **ビジュアルプランエディタ**: GUIでのPlan作成/編集
2. **リアルタイムコラボレーション**: 複数ユーザーでの共同編集
3. **AI支援の高度化**: より賢いPlan生成と最適化
4. **マーケットプレイス**: ブロック/Planの共有

## エコシステム
1. **SDK/API**: 外部開発者向けツール
2. **テンプレートライブラリ**: 業界別テンプレート
3. **認証済みブロック**: 品質保証されたブロック
4. **コミュニティサポート**: ユーザーフォーラム

## 技術革新への対応
1. **新しいAIモデル**: 最新LLMへの対応
2. **クラウドネイティブ**: サーバーレス実行
3. **エッジコンピューティング**: 分散処理
4. **量子コンピューティング**: 将来の計算パラダイム

# ディレクトリ構成

```
keiri_agent/
├── app.py                          # Streamlitアプリケーションのエントリーポイント
├── core/
│   ├── blocks/
│   │   ├── base.py                 # ProcessingBlock/UIBlock基底クラス
│   │   ├── registry.py             # ブロックの自動発見とロード
│   │   ├── processing/
│   │   │   ├── ai/
│   │   │   │   └── process_llm.py  # 汎用LLM処理ブロック
│   │   │   ├── excel/
│   │   │   │   └── write_results.py
│   │   │   ├── file/
│   │   │   │   └── parse_zip_2tier.py
│   │   │   └── transforms/
│   │   │       ├── flatten_items.py
│   │   │       └── pick_value.py
│   │   └── ui/
│   │       └── interactive_input.py # 中核UIブロック
│   ├── plan/
│   │   ├── models.py               # Plan/Node/Binding等のPydanticモデル
│   │   ├── loader.py               # YAML/JSONローダー
│   │   ├── validator.py            # Plan検証ロジック
│   │   ├── runner.py               # 実行エンジン
│   │   ├── context.py              # 実行コンテキスト管理
│   │   ├── design_engine.py        # LLM駆動のPlan生成
│   │   └── text_extractor.py       # 文書からのテキスト抽出
│   ├── ui/
│   │   └── session_state.py        # Session State管理ユーティリティ
│   ├── schemas.py                  # 共通の型定義
│   └── utils.py                    # 汎用ユーティリティ
├── block_specs/                    # ブロック仕様定義（YAML）
│   ├── processing/
│   │   ├── ai.process_llm.yaml
│   │   ├── excel.write_results.yaml
│   │   └── file.parse_zip_2tier.yaml
│   └── ui/
│       └── ui.interactive_input.yaml
├── designs/                        # Plan保存ディレクトリ
│   ├── invoice_reconciliation.yaml
│   └── common/                     # 共通サブフロー
├── runs/                          # 実行ログディレクトリ
│   └── <plan_id>/
│       └── <timestamp>.jsonl
├── docs/
│   ├── architecture.md             # 詳細アーキテクチャ設計
│   └── design.md                   # 本設計書
├── tests/                         # テストコード
└── config/                        # 設定ファイル（レガシー）
```

# コアコンポーネントの役割

## 基盤コンポーネント
- **LLMClient**: OpenAI/Azure OpenAI APIのラッパー、構造化出力対応
- **ExcelManager**: openpyxlベースのExcel読み書き、セル/列単位の更新
- **FolderProcessor**: ZIP/フォルダ構造の解析、ファイル内容のテキスト抽出
- **FileProcessor**: 各種ファイル形式（PDF/DOCX/XLSX等）からのテキスト抽出
- **TextExtractor**: Plan生成時の文書処理統合インターフェース

## バージョニングと移行

### セマンティックバージョニング
- **ブロック**: `id@major.minor.patch`
  - major: 破壊的変更（I/O互換性なし）
  - minor: 機能追加（後方互換あり）
  - patch: バグ修正
- **Plan**: `apiVersion` と `version` で管理
  - apiVersion: DSL仕様のバージョン
  - version: Plan自体のバージョン

### 移行戦略
- **ブロック移行**:
  - メジャーバージョンアップ時は互換性警告
  - ピン止め機能（`block: ai.process_llm@1.0.0`）
  - 自動移行スクリプトの提供
- **UIブロック統合**:
  - レガシーブロック（`ui.file_uploader.*`等）から`ui.interactive_input`への段階移行
  - 移行ツールによる自動変換サポート
- **Plan DSL進化**:
  - `apiVersion` による機能サポート範囲の明示
  - 後方互換性の維持（最低2バージョン）

# アーキテクチャ概要図

```
┌─────────────────────────────────────────────────────────────┐
│                         ユーザーインターフェース              │
│                    (Streamlit / Web Application)             │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                         業務設計レイヤー                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ Plan Editor │  │Design Engine│  │ Plan Validator  │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │Block Catalog│  │Text Extractor│ │ Dry-run Engine │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                         実行レイヤー                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ Plan Runner │  │Session State│  │ Block Registry  │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ DAG Executor│  │Error Handler│  │  Observability  │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                         ブロックレイヤー                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐   │
│  │ UI Blocks   │  │Process Blocks│ │ Core Components │   │
│  └─────────────┘  └─────────────┘  └─────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

# 用語集

## 基本用語
- **Plan**: 業務フローを定義したYAMLファイル。ノードのDAGとして表現される。
- **Block**: 再利用可能な処理単位。UIブロックとProcessブロックの2種類。
- **Node**: Plan内の実行単位。1つのBlockを参照し、入出力を定義。
- **BlockSpec**: ブロックの仕様定義。YAML形式で入出力やバリデーションを記述。
- **BlockContext**: 実行時のコンテキスト情報。run_id、workspace、varsを含む。

## 実行関連
- **DAG**: Directed Acyclic Graph。循環のない有向グラフ。実行順序を決定。
- **Session State**: Streamlitのセッション管理機能。UIの状態を永続化。
- **Dry Run**: 実データを使わない検証実行。I/O連携の健全性を確認。
- **Run ID**: 実行の一意識別子。ログやトレーシングで使用。

## 制御構造
- **foreach**: 配列要素に対する反復処理。並列実行可能。
- **while**: 条件が真の間の反復処理。max_iterationsで無限ループ防止。
- **when**: 条件分岐。ノードの実行可否を制御。
- **subflow**: 別のPlanを呼び出す機能。モジュール化を実現。

## 参照式
- **Placeholder**: `${...}`形式の参照式。実行時に実際の値に置換。
- **Variable Reference**: `${vars.key}`でPlan変数を参照。
- **Node Reference**: `${nodeId.alias}`で他ノードの出力を参照。
- **Environment Reference**: `${env.KEY}`で環境変数を参照。
- **Config Reference**: `${config.path}`で設定値を参照。

## エラー関連
- **BlockError**: 構造化されたエラー情報。コード、メッセージ、詳細を含む。
- **Validation Error**: Plan検証時のエラー。スキーマや参照の不整合。
- **Runtime Error**: 実行時のエラー。リトライやスキップのポリシーで制御。

## 拡張性
- **Plugin**: 新機能を追加するための拡張機構。
- **Hook**: 実行の特定タイミングで処理を挿入する仕組み。
- **Registry**: ブロックを管理し、動的にロードする仕組み。

# 設計原則のまとめ

1. **宣言的定義**: すべての振る舞いをYAMLで宣言的に定義
2. **型安全性**: JSON Schema/Pydanticによる静的・動的型検証
3. **エラーの可視化**: フォールバックせず、エラーを明示的に表示
4. **状態の永続化**: Session Stateによる画面更新耐性
5. **拡張性**: プラグイン機構による機能追加の容易さ
6. **汎用性**: 特定業務に依存しない設計
7. **可観測性**: 構造化ログとメトリクスによる監視
8. **セキュリティ**: 入力検証とアクセス制御の徹底


