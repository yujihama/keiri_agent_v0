## スタブ撤廃と本実装への移行計画（architecture.md 準拠）

本ドキュメントは、現在のスタブ/簡易PoC実装を完成形仕様（`docs/architecture.md`）に整合させるための置換対象と実装方針・受け入れ基準を整理したものです。

### 対象スコープ
- Plan 実行系: `core/plan/{runner.py, validator.py, loader.py}`
- 設計支援: `core/plan/design_engine.py`
- ブロック基盤/レジストリ: `core/blocks/{base.py, registry.py}` と `block_specs/**`
- UI ブロック: `core/blocks/ui/*.py`
- 処理ブロック: `core/blocks/processing/**`
- アプリ統合: `app.py`

---

### P0（最優先）

- 実行ランナーの本実装化（条件/並列/ループ/サブフロー/HITL）
  - 現状: when の安全サブセット評価・foreach/while/subflow は「minimal implementation」、未解決入力の簡易ディファ、HITL は単一 pending のJSON永続、UIノードは HITL 無指定時に即時レンダ。
    ```164:176:core/plan/runner.py
                        # foreach loop minimal implementation
                        # while loop minimal implementation
    ```
  - 仕様ギャップ（architecture 準拠）:
    - when: `${...}` 置換後の式評価を強化（数値/文字列/null/辞書アクセス、論理演算、比較の網羅）
    - foreach: itemVar スコープ、max_concurrency、イテレーションのポリシー継承/上書き、collect/（将来: reduce）
    - while: condition 式評価、max_iterations 必須・上限、break/continue 相当の制御（将来）
    - subflow: `plan_id` の相対解決、`inputs` の明示受け渡し、子→親への `out` マッピング（exports 互換）、`run_id` の親子連鎖
    - 依存解決: トポロジカル順を前提に、動的 ready-queue で参照解決を待機。辞書/ネスト alias の解決一貫化
    - HITL: 複数 pending 同時管理、永続フォーマットの型安全化（bytes b64 は現状踏襲）、再開時の衝突回避/TTL/キャンセル
    - ログ/メトリクス: ループ iteration 情報、subflow 親子 run_id、分岐結果、試行回数、経過時間の網羅
  - 受け入れ基準:
    - `tests/test_runner_e2e.py`・`test_runner_ui_layout.py`・`test_runner_foreach_when.py`・`test_runner_while_subflow.py` がグリーン
    - 同 indegree 内での依存未解決ノードが適切に待機/再実行されること
    - HITL の pending を複数プラン/複数ノードで安全に再開できること

- バリデータ強化（型/参照/DAG/Excel 事前検証）
  - 現状: when 構文は安全サブセット検査、foreach.input は vars/config の iterable 確認のみ、`dry_run_plan` はダミー文字列合成のみ。
    ```335:339:core/plan/validator.py
    # Synthesize outputs with simple placeholders
    produced[(node_id, alias)] = f"{node_id}.{local_out}#dry"
    ```
  - 仕様ギャップ:
    - BlockSpec の inputs/outputs に基づく型伝播・一致検査（JSON Schema 連携を視野）
    - env/config の存在検査に加え型検査（数値/配列/オブジェクト）
    - foreach/while/subflow 周辺の静的妥当性（`foreach.input` の参照先型、`while.max_iterations` 必須、`subflow.plan_id` 実在）
    - Excel 事前検証で `output_config` の必須キー・型チェック（既存強化）
  - 受け入れ基準:
    - `tests/test_validator_and_dryrun.py`・`test_validator_config_when.py` がグリーン
    - 不正な参照/型不一致/閉路/不足キーを網羅検出してメッセージ化

- AI 照合ブロックの本実装（ヒューリスティク撤廃）
  - 現状: 金額パターン抽出の単純集計（スタブ）
    ```41:70:core/blocks/processing/ai/invoice_payment_match.py
    # Very simple heuristic: extract amounts from text excerpts, aggregate by file
    ```
  - 仕様ギャップ:
    - `docs/architecture.md` の想定に沿い、既存資産（LLMClient/InvoiceChecker 相当）の呼び出し層を整備
    - テキスト抽出結果・請求/入金の正規化・一致判定・不一致レポート生成を責務分離
  - 受け入れ基準:
    - 入力（evidence）に対し一致/不一致の根拠を含む `results/summary` を安定出力
    - タイムアウト/再試行/エラー継続がポリシー通りに動作

---

### P1（高）

- Dry-run エンジンの現実的シミュレーション
  - ギャップ: ダミー文字列合成から、Spec 型に応じたサンプル生成/未解決参照の詳細警告/Excel 仮書込のサニティへ拡張
  - 基準: 設計タブの「検証/ドライラン」で Excel 書込が衝突なく成立することを事前に検知
  - 状況: 実装完了（型別サンプル生成・ループcollect合成・Excelメモリ上検証を追加）

- Block Registry のメタ強化と厳格化
  - ギャップ: 入出力スキーマ（JSON Schema/Trait）添付、タグ/カテゴリ、`requirements` の import 可否検査の結果提示強化
  - 基準: ブロックカタログで不足依存/互換性を明確表示、Validator と連携
  - 状況: 一部実装（`BlockSpec` に `tags/category/schema_refs` 追加、`requirements` 事前importチェック）

- UI ブロックの本実装化
  - `ui.file_uploader.evidence_zip`: サイズ制限/拡張子検査/（任意）ウイルススキャンフック、進捗表示
  - `ui.file_uploader.excel`: ワークブックの基本検査（拡張子/壊れ/最大サイズ）とメタの提示
  - `ui.confirmation`: HITL と即時レンダの切替を明示（headless 既定 True は CI 用に維持）
  - 基準: UI の戻り値が Spec と一致し、HITL 経由でも欠損なく永続・再開可能
  - 状況: アップローダで `max_mb` 検証・受領サイズプレビューを追加（CIは従来どおりheadlessで無効化）

- Excel 出力ブロックの拡充
  - ギャップ: 列見出し/書式/日時・通貨の型処理、列マッピング（列名/キー指定）
  - 基準: 可変 `columns` と型に応じたセル書式での書込み、検証用ブックでの再現性

---

### P2（中）

- Design Engine（LLM 生成）の強化
  - ギャップ: LLM Structured Output（Pydantic/Strict JSON）・要件抽出の前処理（文書サマリ/正規化）を明確化
  - 基準: 生成 JSON が `Plan` スキーマで常に parse 成功し、Validator/Dry-run を通過
  - 状況: 実装着手（Structured Output による厳格JSON受領／入力文書の軽量正規化と長さ制限／フォールバック健全化）

- Config Store の型サポート
  - ギャップ: `config.*` 参照の型（数値/配列）検査、エラーメッセージの改善、ホットリロード
  - 基準: Validator が config 型不一致を検出し、ランナーの `resolve` が一貫

---

### 実装タスクリスト（抜粋）

- runner 強化
  - 動的 ready-queue と依存解決（ネスト/alias 対応）
  - foreach/while/subflow の API 整理と一貫ログ
  - HITL 複数 pending 管理、再開・キャンセル・TTL
  - ログイベントの型と必須フィールド明確化

- validator 強化
  - BlockSpec 型→ノード入出力の型検証
  - env/config の型検査
  - dry-run: Excel 仮書込検証の内製（メモリ上）

- ブロック
  - ai.invoice_payment_match: LLM/ルール/正規化のレイヤ分離と統合
  - file.parse_zip_2tier: ディレクトリ深度/大容量向けストリーム処理、抽出ポリシー設定
  - excel.write_results: マッピング/書式/列可変対応

- UI
  - アップローダの検証/進捗/失敗時リカバリ
  - confirmation の headless/interactive の挙動統一

- registry/metadata
  - Spec に JSON Schema/タグの追加、UI カタログの詳細化

---

### 受け入れ基準（横断）

- 既存テスト群（`tests/`）がグリーン（UI 関連は headless モードで担保）
- 設計タブ: 生成→検証→ドライラン→保存が、サンプル設計（`designs/invoice_reconciliation.yaml`）で一貫して成功
- 実施タブ: HITL あり/なし双方で中断→再開が機能し、ログ/DAG 可視化が崩れない

---

### 補足（参考コード位置）

- ランナー最小実装コメント:
```79:110:core/plan/runner.py
def _build_graph(...):
    # ${node.alias} からエッジを生成する簡易実装
```

- when/while の式置換・安全評価:
```240:269:core/plan/runner.py
def evaluate_when(...):
    # ${...} 置換→安全サブセットで評価
```

- ドライランのダミー合成:
```335:339:core/plan/validator.py
produced[(node_id, alias)] = f"{node_id}.{local_out}#dry"
```

- AI 照合のヒューリスティック（置換対象）:
```41:70:core/blocks/processing/ai/invoice_payment_match.py
# 金額抽出の単純集計（スタブ）
```


