# 完成形アーキテクチャ詳細設計

本書は、本ツールを「①業務設計」と「②業務実施」の二層で構成する完成形アーキテクチャの詳細設計を定義します。処理ブロック/UIブロックのプラグイン機構、設計ファイル（Plan）による宣言的オーケストレーション、ドライラン、実行ログ、UI統合を含みます。

---

## 1. 目的とスコープ
- 目的: 保守性・拡張性・再利用性・透明性を高め、経理業務の自動化/半自動化を設計駆動で実行可能にする。
- スコープ:
  - 設計レイヤ（業務設計）: ユーザー指示/手順書→Plan（YAML/JSON）生成・編集・検証・ドライラン。
  - 実行レイヤ（業務実施）: Planに従い処理ブロック/UIブロックをDAG順で実行、結果出力/ログ。
  - プラグイン: 処理ブロック(UI含む)をディレクトリ配置＋YAML定義で自動認識。

---

## 2. 要求事項の反映
- 2層構成: ①業務設計、②業務実施。
- 処理ブロック: 疎結合Pythonメソッド/クラス＋YAML定義（入出力/説明/バージョン）。
- UIブロック: ファイルアップロード、確認ダイアログ、選択UI等をYAML定義で配備。
- 設計時: ブロック定義を見ながらフロー（Plan）策定、ドライランでI/O疎通確認。
- 設計ファイル: UI上で表示・編集・保存（YAML/JSON）。
- 実施時: Plan選択で実行。UIブロックを定義順で表示。結果はUIへ出力。構造化ログで振り返り。

---

## 3. 全体アーキテクチャ

論理構成:
- 設計レイヤ
  - BlockCatalog（ブロック一覧）/ Plan Editor / Plan Validator / Dry-run Engine / Plan Store
  - AI設計支援（既存 RuleSuggester を拡張しブロック選定提案）
- 実行レイヤ
  - Block Registry（自動発見/バージョン解決）
  - Plan Runner（DAG実行: 逐次/並列/条件/人手介在/ループ/サブフロー）
  - Observability（構造化ログ/メトリクス/イベント）
- 既存コアの再利用
  - LLMClient（AI処理）/ ExcelManager（出力）/ FolderProcessor（証跡構造化）/ InvoiceChecker（チェック）

---

## 業務設計（Plan生成）仕様

- 入力（UI）
  - ユーザー指示テキスト（業務の目的/制約/優先度等）
  - 手順書/マニュアル/規定類のアップロード（pdf, docx, xlsx, md, txt）
- 処理フロー（Design Engine）
  1. 文書インジェスト: アップロード文書のテキスト抽出/正規化（既存の抽出系を再利用）
  2. 要件抽出（LLM/Structured Output）:
     - 目標、入出力データ、必要なUI介入（アップロード/確認/選択）、分岐条件、繰り返し単位、サブフロー候補を抽出
     - スキーマに準拠したJSONを生成（Pydantic検証）
  3. ブロック選定/配線案生成:
     - BlockCatalogのメタ（tags/入出力I/F）と要件をマッチングし、`graph` ノード列と依存を構築
     - UIブロック（アップロード/確認）を必要箇所に挿入
     - 未解決入力は `${vars.*}` プレースホルダで明示
  4. Plan構築/ポリシー設定:
     - `vars`, `policy(on_error/retries/timeout)`, `ui.layout`, `graph` を組み立てYAML化
  5. ドライラン（疎通確認）:
     - サンプル値でI/O検証、Excel書込の事前チェック、未解決参照/型不整合/閉路を検出
  6. 差分提示/編集:
     - Planプレビュー（YAML/JSON）と検証結果、未解決項目リストを提示し、UIで修正→再検証
- 出力
  - 設計ファイル（Plan YAML/JSON）を `designs/` 配下に保存（命名: `<slug>_<yyyymmddHHMM>.yaml`）
  - 設計レポート（検出した未解決/警告/採用ブロック一覧）をUIで表示
- UI仕様（設計タブ）
  - ステップ: 1) 指示入力 2) 文書アップロード 3) 生成プレビュー 4) ドライラン 5) 保存/上書き
  - YAMLエディタ（スキーマ検証/フォーマット）とテンプレート挿入（`when`/`foreach`/`subflow`）
- LLM仕様
  - GPT-4.1（LangChain）+ Pydantic Output Parserにより、抽出結果を型安全に受領
  - 代表スキーマ（概要）:
    ```json
    {
      "tasks": [{"name": "...", "block_id": "...", "inputs": {}, "outputs": {}}],
      "ui": [{"type": "file_uploader|confirmation|select", "id": "...", "bind": {}}],
      "flow": [{"from": "nodeA", "to": "nodeB", "when": "..."}],
      "vars": {"output_config": {}},
      "placeholders": ["vars.output_config", "..."]
    }
    ```
- セキュリティ/運用
  - アップロード文書はメモリ/一時領域で処理し、Plan以外は保存しない
  - 生成/検証のイベントは `runs/designs/<plan>/<ts>.jsonl` に出力（任意）

---

## 4. ディレクトリ/ファイル構成（完成形）

```
keiri_agent/
├── app.py                               # streamlitの起動コード
├── core/
│   ├── base_llm_service.py
│   ├── excel_manager.py
│   ├── file_processor.py
│   ├── folder_processor.py
│   ├── invoice_checker.py
│   ├── llm_client.py
│   ├── models.py
│   ├── rule_manager.py
│   ├── rule_suggester.py
│   ├── task_engine.py                   # 既存: 段階的にPlan Runnerへ統合/委譲
│   ├── ui_components.py
│   ├── utils.py
│   ├── blocks/                          # 新規: ブロック実装コード
│   │   ├── base.py                      # ProcessingBlock/UIBlock 基底IF/Context
│   │   ├── registry.py                  # ブロック自動発見・ロード・バージョン解決
│   │   ├── processing/
│   │   │   ├── ai/
│   │   │   │   └── invoice_payment_match.py   # 例: GPTで請求-入金照合
│   │   │   ├── excel/
│   │   │   │   └── write_results.py           # Excel書き込み
│   │   │   ├── file/
│   │   │   │   └── parse_zip_2tier.py         # 2階層ZIP解析
│   │   │   ├── transforms/                    # 任意の変換/整形
│   │   │   └── validators/                    # 入力検証系
│   │   └── ui/
│   │       ├── file_uploader_evidence.py      # 証跡ZIPアップロード
│   │       ├── file_uploader_excel.py         # Excelアップロード
│   │       └── confirmation.py                # 人手確認ダイアログ
│   └── plan/                            # 新規: 設計/実行エンジン
│       ├── models.py                    # Plan/Node/Port/Binding（Pydantic）
│       ├── loader.py                    # YAML/JSON読み込み
│       ├── validator.py                 # スキーマ/配線/I/O型/依存検証
│       ├── runner.py                    # DAG実行、並列/条件/HITL/再試行/ループ/サブフロー
│       └── context.py                   # 実行コンテキスト/変数/成果物
├── block_specs/                         # 新規: ブロック宣言YAML
│   ├── processing/
│   │   ├── ai.invoice_payment_match.yaml
│   │   ├── excel.write_results.yaml
│   │   └── file.parse_zip_2tier.yaml
│   └── ui/
│       ├── ui.file_uploader.evidence_zip.yaml
│       ├── ui.file_uploader.excel.yaml
│       └── ui.confirmation.yaml
├── designs/                             # 新規: Plan（業務設計）保管
│   ├── invoice_reconciliation.yaml
│   └── common/                          # サブフロー用共通プラン（任意）
│       └── validate_inputs.yaml
├── runs/                                # 新規: 実行ログ（JSONL）
│   └── invoice_reconciliation/
│       └── 2025-08-05T12-00-00.jsonl
├── docs/
│   ├── architecture.md                  # 本書（完成形設計）
│   └── implementation_plan.md           # 実装計画
└── config/
    ├── rules.json
    └── task_configs.json                # 既存→Planへ順次移行（互換アダプタ）
```

---

## 5. 主要コンポーネントの責務

- Block Registry（`core/blocks/registry.py`）
  - `block_specs/**/*.yaml`を読み込み、`entrypoint`（`path:ClassName`）で動的ロード
  - バージョン解決（SemVer）。破壊的変更はメジャーアップ
  - ブロックのI/Oスキーマ連携（Pydantic/JSON Schema）

- Block Base（`core/blocks/base.py`）
  - `ProcessingBlock`/`UIBlock`の抽象IF
  - 共通`BlockContext`（`run_id`/`workspace`/`vars`）
  - ライフサイクル: `validate()` → `dry_run()` → `run()`

- Plan（`core/plan/models.py`）
  - `Plan`/`Node`/`Port`/`Binding`/`Policy`/`UIConfig`
  - ノード共通: `id`, `block`（処理/Ui）に加え、任意の `when` ガード式
  - ループ/サブフローの複合ノードを定義（後述）
  - 参照式: `${nodeId.outputKey}` `${vars.key}` `${env.KEY}` `${config.*}`

- Plan Validator（`core/plan/validator.py`）
  - スキーマ妥当性・DAG閉路検知・入出力型一致・未解決参照検出
  - `when`式の構文検証、`foreach.input` が配列であることの検証
  - ループ `max_iterations` の上限検証、サブフロー参照の存在確認
  - Excel疎通（`ExcelManager`で仮書込検証）

- Plan Runner（`core/plan/runner.py`）
  - トポロジカル順/並列実行、`when`条件によるノードスキップ
  - ループ（`foreach`/`while`）の並列化と集約、サブフロー呼び出し
  - ポリシー: `on_error`（halt/continue/retry）/ `retries` / `timeout_ms` / `max_concurrency`
  - UIブロックの動的レンダリング（Streamlit）
  - 構造化ログ（JSONL）とメトリクス（ループiterationId／サブフローrun_id継承）

- UI統合（`app.py`）
  - タブ:「請求書チェック」「業務設計」「業務実施」
  - 設計: ブロックカタログ/Plan一覧/エディタ/ドライラン/保存
  - 実施: Plan選択→UIブロックをPlanの`ui.layout`順に自動配置
  - ループ/サブフローはUIに折りたたみで展開表示、条件は実行ログに分岐結果を明示

- 互換アダプタ
  - 既存 `TaskEngine` → Plan Runnerの単一Plan実行ラッパとして存置
  - `task_configs.json` → Planへの移行支援（変換スクリプト/読み替え）

---

## 6. ブロック定義（YAML）仕様

```yaml
# block_specs/processing/ai.invoice_payment_match.yaml
id: ai.invoice_payment_match
version: 1.0.0
entrypoint: blocks/processing/ai/invoice_payment_match.py:InvoicePaymentMatchBlock
inputs:
  evidence_data: { $ref: "core.schemas:EvidenceData" }
  instruction: { type: string }
  output_config: { $ref: "core.schemas:OutputConfig" }
outputs:
  results: { $ref: "core.schemas:AccountingResults" }
  summary: { $ref: "core.schemas:AccountingSummary" }
requirements:
  - openai
  - pydantic
description: 請求書と入金明細の照合をGPTで行う
```

```yaml
# block_specs/ui/ui.file_uploader.evidence_zip.yaml
id: ui.file_uploader.evidence_zip
version: 1.0.0
entrypoint: blocks/ui/file_uploader_evidence.py:EvidenceZipUploader
inputs: {}
outputs:
  evidence_zip: { type: bytes }
description: 2階層ZIPフォルダのアップロードUI
```

---

## 7. Plan（設計ファイル）仕様

```yaml
# designs/invoice_reconciliation.yaml（例）
apiVersion: v1
id: invoice_reconciliation
version: 0.1.0
vars:
  instruction: "請求書・入金明細を照合し差異を出力"
  output_config: ${config.task_configs.accounting_task_1.output_config}
policy:
  on_error: continue   # halt|continue|retry
  retries: 0
  concurrency:
    default_max_workers: 4
ui:
  layout: [upload_evidence, upload_excel, match_ai, write_excel]
graph:
  - id: upload_evidence
    block: ui.file_uploader.evidence_zip
    out:
      evidence_zip: evidence_zip
  - id: parse_evidence
    block: file.parse_zip_2tier
    in:
      zip_bytes: ${upload_evidence.evidence_zip}
    out:
      evidence_data: evidence
  - id: upload_excel
    block: ui.file_uploader.excel
    out:
      workbook: workbook
  - id: match_ai
    block: ai.invoice_payment_match
    in:
      evidence_data: ${parse_evidence.evidence}
      instruction: ${vars.instruction}
    out:
      results: match_results
      summary: match_summary
  - id: write_excel
    block: excel.write_results
    in:
      workbook: ${upload_excel.workbook}
      data: ${match_ai.match_results}
      output_config: ${vars.output_config}
    out:
      write_summary: write_summary
```

### 7.1 条件分岐（whenガード）
- すべてのノードは任意の `when` を持てる。`when` が偽ならノードはスキップされる。
- `when` は式（`${...}` 参照の置換後に安全評価）または単純比較（eq/gt など）のオブジェクトを受け付ける。

```yaml
- id: notify_large_amount
  block: ui.confirmation
  when:
    expr: "${match_ai.summary.total_amount} > 1000000"  # 100万円超で確認UIを表示
  in:
    message: "高額取引です。確認してください。"
```

- 推奨: 式評価には `${nodeId.key}` `${vars.key}` `${env.KEY}` を解決後、簡易式エンジンで評価（実装計画参照）。

### 7.2 ループ（foreach/while）
- `foreach` で配列を反復。`itemVar` に各要素を束縛し、`body`（サブグラフ/サブフロー）を実行。
- `while` は `condition` が真の間ループ。必ず `max_iterations` を指定。
- 既定の集約は `collect`（各イテレーションの出力をリスト化）。

```yaml
- id: foreach_data
  type: loop
  foreach:
    input: "${parse_evidence.evidence.data}"   # 配列/辞書のvaluesを想定
    itemVar: data_item
    max_concurrency: 4
  body:
    plan:
      graph:
        - id: per_item_match
          block: ai.invoice_payment_match
          in:
            evidence_data: ${data_item}
            instruction: ${vars.instruction}
          out:
            result: item_result
      exports:
        - from: per_item_match.item_result
          as: item_result
  out:
    collect: item_result            # 結果を配列で収集 → foreach_data.item_result_list
```

- 集約方法: `collect`（リスト化）、`reduce`（単純加算/連結等、将来拡張）。
- `while` 例（簡易）:
```yaml
- id: retry_until_success
  type: loop
  while:
    condition:
      expr: "${per_item_match.status} != 'success'"
    max_iterations: 3
  body:
    plan:
      graph:
        - id: per_item_match
          block: ai.invoice_payment_match
          in: { ... }
```

### 7.3 サブフロー（再利用可能Plan呼び出し）
- サブフローノードで別のPlan（設計）を呼び出し、I/Oをマッピング。
- 呼び出し先の `exports` を親に返す。

```yaml
- id: validate_and_write
  type: subflow
  call:
    plan_id: common/validate_inputs   # designs/common/validate_inputs.yaml
    inputs:
      workbook: ${upload_excel.workbook}
      results: ${match_ai.match_results}
  out:
    exports:
      - from: write_ok
        as: ok
```

- 変数スコープ: サブフローは独立スコープ。必要な `vars` は `inputs` で明示受け渡し。`run_id` は親から派生（例: `parent#1`）。

---

## 8. 実行フロー（概要）
1) UIでPlan選択→ローディング（`loader.py`）
2) 検証（`validator.py`）: スキーマ/閉路/I-O整合/未解決参照/条件式/ループ前提
3) ドライラン（任意）: サンプルI/O、Excel仮書込み確認
4) 実行（`runner.py`）: DAG順にブロック実行、`when`/ループ/サブフロー対応
5) 出力: `ExcelManager`で書込、UIへサマリー表示
6) ログ: `runs/<plan>/<ts>.jsonl`へ構造化イベント出力（iteration/subflow/branch情報含む）

---

## 9. ロギング/監査
- JSON Lines形式（1行1イベント）。開始/終了/入出力サマリ/例外/リトライ/経過時間
- ループ: `iteration.index` / `iteration.key` を付与、集約結果サイズも記録
- サブフロー: `parent_run_id` / `child_run_id` を紐付け
- 実行`run_id`でトレース。UIでログ閲覧/ダウンロード提供

---

## 10. 非機能要件/運用
- 可観測性: ログ・メトリクス・UIの進捗
- 性能: 並列処理（デフォルト4）、大きなZIP/Excelに配慮
- セキュリティ: APIキー安全管理（.env/セッション）、一時ファイル最小化
- 信頼性: 入出力型検証、フォールバック、リトライ、タイムアウト、`while.max_iterations` 必須
- 互換性: 既存機能はPlanブロック化で段階統合、旧設定の読み替え（アダプタ）

---

## 11. バージョニング/互換性ポリシー
- ブロック: `id@semver`で参照。メジャー更新は互換警告/ピン止め推奨
- Plan: `apiVersion`と`version`を保持。Validatorで互換性診断
- `block_specs`変化時はUIで差分表示し再検証を促す
- Plan DSLの互換: `apiVersion` で条件/ループ/サブフローのサポート範囲を明示

---

## 12. 代表的ブロック（既存資産のブロック化）
- `file.parse_zip_2tier` → `FolderProcessor.process_evidence_folder` のラップ
- `ai.invoice_payment_match` → `LLMClient.process_accounting_task` のラップ
- `excel.write_results` → `ExcelManager.write_results` のラップ
- UIブロック → 既存 `CommonUIComponents` を内部利用

---

## 13. セキュリティ/コンプライアンス考慮
- アップロードデータ非永続（必要時のみメモリ/一時ファイル）
- APIキーは環境変数/入力直後にセッション格納、保存不可
- ログは機微データをサマリー化（必要に応じてマスク）

---

## 14. 将来拡張
- DAG可視化・ドラッグ&ドロップ設計エディタ
- 外部連携（会計SaaS/DB/REST）用ブロック、Webhookトリガ
- 集約演算（reduce）の拡張、分散キューによる大規模並列
- 設計の版管理・差分レビュー・承認ワークフロー

