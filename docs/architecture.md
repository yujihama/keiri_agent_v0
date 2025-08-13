# 完成形アーキテクチャ詳細設計

本書は「①業務設計（Plan生成）」と「②業務実施（Plan実行）」の二層で構成される完成形アーキテクチャの改訂版です。UIは `ui.interactive_input` を中核コンポーネントとして統一し、StreamlitのSession StateでUI状態を永続します。各ブロックは入出力I/Fを厳格にYAMLで宣言し、Plan生成/検証/ドライラン/実行の全工程で型安全に扱います。フォールバックは行わず、エラーは必ずUIに明示的に返します。

---

## 1. 設計思想（Principles）
- インタラクティブUIの単一化: Planに含めるUIは原則 `ui.interactive_input` を使用する。
- セッション永続: すべてのUI入力は Streamlit Session State に保存し、再実行や画面更新でも値や描画をクリアしない。
- I/O契約の明文化: 各UI/Processingブロックは、必須/任意/既定値/バリデーション/型を YAML で構造化定義する。
- LLM駆動のPlan生成: LLMは BlockCatalog（YAML定義の集合）を参照して Plan YAML を生成する。
- 厳密検証とドライラン: 生成後はスキーマ/依存/I-O整合/参照解決の検証と、宣言されたサンプル/モックによるドライランを実施。
- 型安全な受け渡し: 参照解決後のノード I/O は JSON Schema/Pydantic で静的・動的に検証する。
- フォールバック禁止: 不備やエラーは黙って吸収せず、構造化エラーとしてUIに返す（失敗を可視化）。

---

## 2. 全体アーキテクチャ

- 設計レイヤ（Design）
  - BlockCatalog（ブロック定義レジストリ）/ Plan Editor / Plan Validator / Dry-run Engine / Plan Store
  - AI設計支援（LLMが BlockCatalog を参照しPlan候補を合成）
- 実行レイヤ（Runtime）
  - Block Registry（自動発見/バージョン解決）
  - Plan Runner（DAG実行: 逐次/並列/条件/ループ/サブフロー/HITL）
  - Observability（構造化ログ/メトリクス/イベント）
- コアコンポーネント
  - LLMClient: OpenAI/Azure OpenAI APIのラッパー、構造化出力対応
  - ExcelManager: openpyxlベースのExcel読み書き、セル/列単位の更新
  - FolderProcessor: ZIP/フォルダ構造の解析、ファイル内容のテキスト抽出
  - FileProcessor: 各種ファイル形式（PDF/DOCX/XLSX等）からのテキスト抽出

---

## 3. UIとSession Stateの設計

- 中核UIブロック: `ui.interactive_input`
  - 複数フィールド（ファイル/テキスト/選択/ブール/数値/チャット等）を `requirements` で宣言的に定義。
  - モード: `collect|confirm|inquire|mixed`。用途に合わせて同一ブロックを再利用。
- Session State契約（必須）
  - キー規約: `ss_key = f"plan:{plan_id}::node:{node_id}::v{block_version}"`
  - 初期化: 初回表示時に `requirements` から初期値/既定値を構築 → `st.session_state[ss_key]` に格納。
  - 更新: ユーザー操作時は即時 `st.session_state` に反映。Nodeの `out.collected_data` は Session State から構築。
  - 永続: 画面再実行・再描画でも `st.session_state` の値を尊重。明示的な「リセット操作」以外でクリアしない。
  - 互換: `requirements` のスキーマが変更された場合は「マージ+差分警告」方針（欠落/型不一致を検出）。
- UIエラー表示
  - 構造化エラー（後述の `BlockError`）を UI 上で強調表示し、入力再編集可能な状態を維持。

---

## 4. ブロック定義（YAML）仕様

すべてのブロックは `block_specs/**/*.yaml` にI/O契約を定義します。代表例（抜粋）:

```yaml
# block_specs/ui/ui.interactive_input.yaml
id: ui.interactive_input
version: 0.1.0
entrypoint: blocks/ui/interactive_input.py:InteractiveInputBlock
inputs:
  mode:
    type: string
    enum: ["collect", "confirm", "inquire", "mixed"]
    description: 動作モード
  requirements:
    type: array
    description: 収集する情報の定義
    items:
      type: object
      required: [id, type, label]
      properties:
        id: { type: string }
        type: { type: string, enum: ["file", "files", "folder", "text", "select", "boolean", "number", "chat"] }
        label: { type: string }
        description: { type: string }
        required: { type: boolean, default: true }
        options: { type: array }
        accept: { type: string }
        validation: { type: object }
  message: { type: string }
  context: { type: object }
outputs:
  collected_data: { type: object, description: requirements の ID をキーとする }
  approved: { type: boolean }
  response: { type: string }
  metadata: { type: object }
requirements: []
description: 汎用インタラクティブ入力UIブロック
```

処理系ブロックの例（型参照に `$ref` を使用）:

```yaml
# block_specs/processing/ai.process_llm.yaml
id: ai.process_llm
version: 1.0.0
entrypoint: blocks/processing/ai/process_llm.py:ProcessLLMBlock
inputs:
  evidence_data:
    type: object
  instruction:
    type: string
  prompt:
    type: string
    description: LLMへ渡す主命令文。未指定時はinstructionを利用。
  system_prompt:
    type: string
    description: 既定のシステムプロンプトを上書きする場合に指定。
  output_schema:
    type: object
    description: JSON-Schema風スキーマ（簡易）。これに基づいて動的Pydanticを生成し出力を構造化。
  per_file_chars:
    type: integer
    description: "1ファイルあたりのテキスト抜粋の最大文字数（既定: 1500）。"
  group_key:
    type: string
outputs:
  results:
    type: object
  summary:
    type: object
requirements: []
description: |
  LLMまたはヒューリスティックで文書の抽出・照合を行う汎用ブロック。
  - 全入力ファイルを対象に処理
  - システム/ユーザープロンプトはPlanから指定可能
  - 出力スキーマはPlanからJSON-Schema風に与え、動的Pydanticで構造化出力
```

拡張ルール（共通）:
- すべての `inputs/outputs` は JSON Schema ベース。`$ref` は `module:TypeName`（PydanticModel）や `jsonschema://` を許容。
- `required`/`default`/`nullable`/`examples`/`dry_run.samples` をサポート。ドライランは宣言サンプルが無ければ失敗とする（フォールバック禁止）。
- バージョニングは SemVer。破壊的変更時は major を上げ、Plan/Validator で互換警告。

---

## 5. Plan（設計ファイル）DSL

- 基本構造: `apiVersion`/`id`/`version`/`vars`/`policy`/`ui`/`graph`
- 参照式: `${nodeId.key}` `${vars.key}` `${env.KEY}` `${config.*}`
- UIレイアウト: `ui.layout` は表示順のヒント。実体は `graph` のノードでレンダリング。

代表例（`ui.interactive_input` を中核に統合した例）:

```yaml
apiVersion: v1
id: invoice_reconciliation
version: 0.2.0
vars:
  instruction: "請求書・入金明細を照合し差異を出力"
  output_config: ${config.task_configs.accounting_task_1.output_config}
policy:
  on_error: halt          # 既定は厳格に停止。retry等は明示指定
  retries: 0
  concurrency:
    default_max_workers: 4
ui:
  layout: [collect_inputs, parse_evidence, process_llm, write_excel]
graph:
  - id: collect_inputs
    block: ui.interactive_input
    in:
      mode: mixed
      message: "照合に必要な入力を提供してください"
      requirements:
        - { id: evidence_zip, type: file,   label: "証跡ZIP",    accept: ".zip" }
        - { id: workbook,    type: file,   label: "Excel",      accept: ".xlsx" }
        - { id: proceed,     type: boolean, label: "実行してよい" }
    out:
      collected_data: collected
  - id: parse_evidence
    block: file.parse_zip_2tier
    when:
      expr: "${collect_inputs.collected.evidence_zip} != null"
    in:
      zip_bytes: ${collect_inputs.collected.evidence_zip}
    out:
      evidence_data: evidence
  - id: process_llm
    block: ai.process_llm
    in:
      evidence_data: ${parse_evidence.evidence}
      prompt: ${vars.instruction}
      output_schema:
        results:
          type: object
          properties:
            items:
              type: array
              items:
                type: object
                properties:
                  file: string
                  count: integer
        summary:
          type: object
          properties:
            total_files: integer
    out:
      results: results
      summary: summary
  - id: write_excel
    block: excel.write
    in:
      workbook: ${collect_inputs.collected.workbook}
      data: ${process_llm.results}
      output_config: ${vars.output_config}
    out:
      write_summary: write_summary
```

### 5.1 条件分岐（when）

すべてのノードは任意の `when` プロパティを持つことができます。`when` が評価されて偽の場合、そのノードはスキップされます。

```yaml
- id: conditional_process
  block: ui.interactive_input
  when:
    expr: "${parse_evidence.evidence.files.length} > 0"
  in:
    mode: confirm
    message: "証跡ファイルが見つかりました。処理を続行しますか？"
```

`when` の指定方法:
- `expr`: 文字列式（`${...}` 参照を解決後に評価）
- 比較オブジェクト: `{ left: "${value}", op: "gt", right: 10 }`（op: eq/ne/gt/gte/lt/lte）

### 5.2 ループ（foreach/while）

#### foreach（配列の反復）
配列を反復処理し、各要素に対してサブグラフまたはサブフローを実行します。

```yaml
- id: process_each_file
  type: loop
  foreach:
    input: "${parse_evidence.evidence.files}"  # 配列
    itemVar: file                              # 各要素を束縛する変数名
    indexVar: idx                              # インデックス（任意）
    max_concurrency: 4                         # 並列実行数
  body:
    plan:
      graph:
        - id: analyze_file
          block: ai.process_llm
          in:
            evidence_data: { files: ["${file}"] }
            prompt: "このファイルの内容を要約"
            output_schema:
              summary: { type: string }
          out:
            results: file_result
      exports:
        - from: analyze_file.file_result
          as: result
  out:
    collect: result                            # 全イテレーションの結果をリスト化
```

#### while（条件ループ）
条件が真の間、繰り返し実行します。無限ループを防ぐため `max_iterations` は必須です。

```yaml
- id: retry_until_approved
  type: loop
  while:
    condition:
      expr: "${approval_status.approved} != true"
    max_iterations: 3
  body:
    plan:
      graph:
        - id: approval_status
          block: ui.interactive_input
          in:
            mode: confirm
            message: "処理結果を確認してください"
```

### 5.3 サブフロー（再利用可能なPlan呼び出し）

別のPlanファイルを呼び出し、入出力をマッピングします。

```yaml
- id: validate_and_process
  type: subflow
  call:
    plan_id: common/validation_flow    # designs/common/validation_flow.yaml
    inputs:
      data: ${collect_inputs.collected}
      rules: ${vars.validation_rules}
  out:
    exports:
      - from: validation_passed
        as: is_valid
      - from: error_messages
        as: errors
```

サブフローの特性:
- 変数スコープ: 独立（親の `vars` は自動継承されない）
- run_id: 親から派生（例: `parent_run#1` → `parent_run#1.sub#1`）
- エラー伝播: サブフロー内のエラーは親に伝播

---

## 6. Plan Validator（厳密検証）

検証は「失敗は失敗として返す」を前提に、以下を全て満たさない場合はエラーを返す。
1) スキーマ検証: Plan自体の構造、各ノードの `block_specs` との合致、必須入力の充足。
2) 参照検証: `${...}` 参照の解決可能性/型互換（出力→入力）。
3) DAG検証: 閉路なし、未使用ノード/出力の警告、実行順の一貫性。
4) UI整合: `ui.layout` と `graph` の対応、`ui.interactive_input.requirements` の重複/型矛盾検出。
5) 型検証: `$ref` の解決、JSON Schema と Pydantic による静的/動的チェック。

いずれかに失敗した場合、`ValidationError` を構造化して返す（UIに表示）。

---

## 7. Dry-run Engine（フォールバック禁止）

- 目的: 実データを使わずに I/O 連携の健全性を確認。
- 方式: 各ブロックの `dry_run.samples` または `examples`、既定値/モックを宣言的に使用。宣言が無い入力はドライラン不可能として明確に失敗させる。
- 出力: 各ノードの入出力サマリー、未解決参照、型不一致をレポート。

---

## 8. Plan Runner（実行）

### 8.1 実行順序

- **トポロジカル順**: DAGの依存関係に基づいて実行順を決定
- **並列実行**: 依存関係がないノードは `policy.concurrency.default_max_workers` の範囲で並列実行
- **条件スキップ**: `when` 条件が偽のノードは実行をスキップし、出力は未定義（`null`）

### 8.2 UIレンダリング

`ui.interactive_input` ブロックの処理:
1. Session State キー生成: `f"plan:{plan_id}::node:{node_id}::v{block_version}"`
2. 初回レンダリング時に `requirements` から初期値を構築
3. ユーザー入力は即座に Session State へ反映
4. ブロック出力 `collected_data` は Session State の現在値から構築
5. 画面再描画時も Session State の値を保持（明示的リセット以外）

### 8.3 実行ポリシー

```yaml
policy:
  on_error: halt      # halt|continue|retry
  retries: 0          # リトライ回数（on_error: retry 時）
  timeout_ms: 300000  # ノードタイムアウト（ミリ秒）
  concurrency:
    default_max_workers: 4
    per_node:         # ノード別の並列数制御
      process_each_file: 8
```

### 8.4 構造化ログ（JSONL）

実行ログは `runs/{plan_id}/{timestamp}.jsonl` に出力:

```json
{"event": "plan_start", "plan_id": "invoice_reconciliation", "run_id": "run_12345", "timestamp": "2025-01-01T10:00:00Z"}
{"event": "node_start", "node_id": "collect_inputs", "block": "ui.interactive_input", "timestamp": "2025-01-01T10:00:01Z"}
{"event": "node_complete", "node_id": "collect_inputs", "outputs": {"collected_data": "{...}"}, "duration_ms": 15234}
{"event": "node_skipped", "node_id": "conditional_process", "reason": "when_condition_false", "condition": "${...} > 0"}
{"event": "loop_iteration", "node_id": "process_each_file", "iteration": 0, "item": "{...}"}
{"event": "node_error", "node_id": "process_llm", "error": {"code": "API_ERROR", "message": "..."}, "retry": 1}
{"event": "plan_complete", "run_id": "run_12345", "status": "success", "total_duration_ms": 45678}
```

---

## 9. エラーハンドリング（フォールバック禁止）

### 9.1 エラー表現（BlockError）

すべてのエラーは構造化された `BlockError` として表現し、UIに確実に返却します。

```python
class BlockError:
    code: str           # エラーコード（例: INPUT_VALIDATION_FAILED）
    message: str        # ユーザー向けメッセージ
    details: dict       # 詳細情報（node_id, field, actual_value等）
    input_snapshot: dict # エラー時の入力状態
    hint: str          # 修正のヒント
    recoverable: bool  # 再実行可能かどうか
```

エラーコード体系:
- `INPUT_VALIDATION_FAILED`: 入力検証エラー
- `OUTPUT_SCHEMA_MISMATCH`: 出力スキーマ不一致
- `DEPENDENCY_NOT_FOUND`: 依存ノードの出力が未定義
- `API_ERROR`: 外部API呼び出しエラー
- `TIMEOUT_ERROR`: タイムアウト
- `PERMISSION_DENIED`: 権限不足

### 9.2 ランナーのエラー処理

```yaml
policy:
  on_error: halt    # halt（既定）: 即座に停止
                   # continue: エラーノードをスキップして継続
                   # retry: 指定回数リトライ
```

エラー時の動作:
1. **halt（既定）**: エラーノードで実行停止、UIにエラー詳細を表示
2. **continue**: エラーノードの出力を `null` として後続処理
3. **retry**: `policy.retries` 回まで再実行、全て失敗時は halt 同様

### 9.3 UI統合

エラー表示の実装:
```python
if error:
    st.error(f"❌ {error.message}")
    with st.expander("エラー詳細"):
        st.json(error.details)
    if error.hint:
        st.info(f"💡 {error.hint}")
    if error.recoverable:
        if st.button("再実行"):
            # Session State は保持されているため、修正後の値で再実行
            rerun_from_node(error.details["node_id"])
```

---

## 10. ディレクトリ/ファイル構成（改訂）

```
keiri_agent/
├── app.py
├── core/
│   ├── blocks/
│   │   ├── base.py                 # ProcessingBlock/UIBlock/BlockContext（validate/dry_run/run）
│   │   ├── registry.py             # block_specs の自動発見・ロード
│   │   ├── processing/ ...
│   │   └── ui/
│   │       └── interactive_input.py
│   ├── plan/
│   │   ├── models.py               # Plan/Node/Port/Binding/Policy/UIConfig
│   │   ├── loader.py
│   │   ├── validator.py            # 厳格検証
│   │   ├── runner.py               # 実行（UI/条件/ループ/サブフロー）
│   │   └── context.py
│   ├── ui/
│   │   └── session_state.py        # Session State のラッパ（キー規約/マージ/リセット）
│   └── schemas.py                  # 型定義（Pydantic）/ JSON Schema 生成
├── block_specs/
│   ├── ui/ui.interactive_input.yaml
│   └── processing/ ...
├── designs/
├── runs/
└── docs/
```

---

## 11. LLM設計支援

- 入力: ユーザー指示、参考資料（pdf/docx/xlsx/md/txt）
- コンテキスト: BlockCatalog（各 `block_specs` のJSON Schema 化）
- 出力: Plan YAML（`ui.interactive_input` を用いた UI 入力の統合、未解決入力は `${vars.*}` で明示）
- 安全性: Pydantic で型検証、未解決/曖昧は占位/警告として返却（自動補完しない）

---

## 12. セキュリティ/運用

- データ: アップロードは Session State または一時領域で処理。不要な永続化は禁止。
- 秘匿情報: APIキーは環境変数/セッション内で保持。保存不可。
- ログ: 機微情報はサマリ化/マスク。JSONLでエクスポート可。

---

## 13. バージョニング/互換性

- ブロック: `id@semver` を参照。メジャー更新時は互換警告/ピン止めを推奨。
- Plan DSL: `apiVersion` と `version` を保持。Validator で互換性診断。
- UIブロック移行戦略:
  - レガシーブロック（`ui.file_uploader.*`, `ui.confirmation.*`）は移行期間中は存置
  - 新規開発は `ui.interactive_input` の使用を必須とする
  - 移行スクリプトで旧Plan内のUIブロックを `ui.interactive_input` に自動変換

---

## 14. 将来拡張

- UI: 複数 `ui.interactive_input` のページング/ウィザード化、入力プリセットの共有。
- 生成: DAG可視化・ドラッグ&ドロップのPlanエディタ。
- 実行: 分散キュー/大規模並列、集約演算の拡張。
- 運用: 設計の版管理・差分レビュー・承認ワークフロー。


