# 実装計画（詳細）

本計画は、完成形アーキテクチャ（`docs/architecture.md`）を段階的に実装するための実行計画です。低リスクで既存機能と共存しつつ、設計駆動・ブロック化・ドライラン・ログ出力を実現します。

---

## 0. 前提/ガードレール
- 言語/環境: Python 3.10+, Streamlit, Pydantic v2
- LLM: OpenAI/Azure OpenAI gpt-4.1
- 厳守事項: LangChainを使用し、LLMの出力はPydanticによるStructured Outputで型安全に取得する
- 追加ライブラリ: `PyYAML`, `jsonschema`（任意）, `networkx`（DAG/閉路検知）, 必要に応じて `typing-extensions`
- 実装場所: `keiri_agent` ワークスペースに新規構築（`extract_invoice` は参照のみ）
- セキュリティ: APIキー管理（.env/サイドバー入力）、ログのPII最小化

---

## 1. フェーズ分割とマイルストーン（各フェーズの完了基準つき）

### フェーズ1: スケルトン/足場（1週）
- 進捗: 完了（テスト緑）
- 目的: 最小限の骨組み（ブロックIF/レジストリ/Planモデル/ローダ）を導入
- 成果物:
  - `core/blocks/base.py`（IF/Context）
  - `core/blocks/registry.py`（spec読込・動的ロード）
  - `core/plan/models.py`（Pydanticモデル）
  - `core/plan/loader.py`（YAML/JSONローダ）
  - ディレクトリ作成（`blocks/` `block_specs/` `designs/` `runs/`）
- 完了基準（Definition of Done）:
  1. keiri_agent 直下に以下が存在し、import可能であること
     - `core/blocks/base.py` に `ProcessingBlock`/`UIBlock`/`BlockContext`
     - `core/blocks/registry.py` に `BlockRegistry`（`load_specs()`/`get(block_id)`）
     - `core/plan/models.py` に `Plan`/`Node`/`Policy` など主要モデル
     - `core/plan/loader.py` に `load_plan(path)`
  2. サンプルspec（`block_specs/ui/ui.placeholder.yaml`）を配置し、`BlockRegistry.load_specs()` 実行でIDが1件以上登録されること
  3. 単体テスト（最低1本）で spec 読込→クラス動的ロードが成功すること（pytest基準: 緑）

- 最小実装の範囲:
  - ★優先★ブロックIFは `ProcessingBlock.run(ctx, inputs) -> dict`, `UIBlock.render(ctx, inputs) -> dict` のみを実装（状態や副作用は最小）
  - `BlockRegistry` は YAML の `id/version/entrypoint/inputs/outputs/...` を読み込み、`entrypoint` はファイルパスまたはドットパスに対応
  - バージョン解決は `packaging.Version` による単純な最新選択（SemVerの互換性診断やピン止めは未実装）
  - ★優先★I/O スキーマはまだ JSON Schema/Pydantic による厳密検証を行っていない（名称レベルの取扱いに留まる）

- 残タスク:
  - `requirements` の自動インストール/検証、ブロックスキーマのPydantic化と保存
  - SemVer互換診断/ピン止め設定、プラグインのホットリロード/差分検知
  - スキーマドキュメント生成（カタログ表示用）

### フェーズ2: バリデーション/ドライラン（1週）
- 進捗: 完了（`validate_plan`/`dry_run_plan` 実装、ユニット2本緑）
- 目的: 配線/I-O型/閉路検証とExcel疎通のドライラン
- 成果物:
  - `core/plan/validator.py`（スキーマ/参照/閉路/I-O整合）
  - Excel仮書込検証（`ExcelManager`連携のモック/スタブで可）
  - 代表Plan `designs/invoice_reconciliation.yaml` 作成
- 完了基準:
  1. Validatorが以下を検出できること
     - 未解決参照（`${...}`）/ I-O型不一致 / DAG閉路
  2. 代表Planの検証がエラー0で通過し、ドライラン（Excel仮書込含む）が成功（True/OK）を返すこと
  3. 単体テストで正常系/異常系（少なくとも未解決参照と型不一致）を網羅（2系統以上）

- 最小実装の範囲:
  - 検証は以下を実施
    - ノードID重複、未知ブロックID、入力/出力キー（名称レベル）の存在チェック
    - 参照 `${node.alias}` の解決（`vars./env./config.` は未解決のまま許容）
    - DAG閉路検知、UIレイアウトのノード存在確認
    - ループ/サブフローは基本前提のみ（`foreach.input`/`while.max_iterations`/`call.plan_id`）
  - ドライランは出力を擬似生成（`<node>.<out>#dry`）し、外部I/OやUIを呼ばない

- 残タスク:
  - ★優先★I/O型の厳密検証（JSON Schema/Pydantic）、`env/config` 解決の静的検証
  - ★優先★Excel疎通ドライラン（`ExcelManager` スタブ連携）、`when`式の構文/安全性チェックの強化
  - ★優先★サブフロー参照の存在・エクスポートマッピング検証、ループ本体の型/集約検証

（対応状況）
- `env` 静的検証: 完了（未設定キーを検出）
- 入出力の型名一致チェック（名称レベル）: 完了
- Excel出力設定 `output_config` の基本検証: 追加済み（シート名/開始行/列配列）
- `config` 静的検証/JSON Schemaによる厳密検証: 未

### フェーズ3: ランナー最小実装（1-2週）
- 進捗: 完了（E2E含むテスト緑、JSONLログ出力確認）
- 目的: DAG逐次/並列実行、UIブロックの動的描画、人手介在（簡易版）
- 成果物:
  - `core/plan/runner.py`（トポロジカル実行、並列、HITL最小）
  - 構造化ログ（JSONL）出力
  - 代表ブロック（既存資産のラップ）
    - `blocks/processing/file/parse_zip_2tier.py`（`FolderProcessor`相当）
    - `blocks/processing/ai/invoice_payment_match.py`（`LLMClient`相当）
    - `blocks/processing/excel/write_results.py`（`ExcelManager`相当）
- 完了基準:
  1. RunnerがPlanをトポロジカル順に実行し、並列（ThreadPool）で複数ノードを処理できること
  2. UIブロックの簡易描画（スタブ）を通じて入力→出力の受け渡しが可能であること
  3. 実行ログ（`runs/<plan>/<ts>.jsonl`）に start/finish/event が1行以上出力されること
  4. E2E最小Plan（ZIP→AI→Excelの擬似/モック）で成功し、出力が定義通りに得られること

- 最小実装の範囲:
  - トポロジカル順実行（同一in-degreeグループをThreadPoolで並列化）
  - イベント: `start/node_start/node_finish/finish/error` をJSONLに記録
  - ★優先★UIブロックはスタブで即時返却（人手介在HITLは未実装）

- 残タスク:
  - ★優先★ノード単位の最大同時実行数/グローバル同時実行数の制御、優先度/キュー化
  - ★優先★メトリクス収集（経過時間/スループット）と集計、HITL実装

（対応状況）
- `node.max_workers` と `priority` をRunnerに反映（部分対応）。グローバル制御/キュー化: 未
- ログJSONLのスレッドセーフ化: 完了
- HITL（人手介在）最小実装: 完了（中断/再開・`ui_wait/ui_submit`・state永続化）

### フェーズ4: 条件分岐/ループ/サブフロー（1-2週）
- 進捗: 完了（`when`/`foreach`/`while`/`subflow` 最小実装、テスト緑）
- 目的: Plan DSLとRunnerを拡張し、`when`/`foreach`/`while`/`subflow` を実装
- 成果物:
  - `Plan.models` 拡張: `when`, `loop(foreach/while)`, `subflow`
  - Validator拡張: `when`式妥当性、`foreach.input`型検証、`while.max_iterations`必須、サブフロー存在確認
  - Runner拡張: 分岐スキップ、ループ実行（並列/集約）、サブフロー呼出（`loader`再帰）
  - ログ拡張: `branch`, `iteration`, `subflow(parent/child_run_id)`
- 完了基準:
  1. 条件分岐: `when` True/False の双方でノードの実行/スキップが期待通りとなる（ログに分岐結果が記録）
  2. ループ: `foreach` でN件入力→N件の子実行が行われ、`collect`で配列が得られる（件数一致）
  3. ループ: `while` で `max_iterations` 超過時に停止し、実行回数=上限であること
  4. サブフロー: 親Planから子Planを呼び出し、exportsが親にマッピングされること（run_idの親子紐付け記録）
  5. 上記を検証する自動テストが4系統以上（分岐/foreach/while/subflow）で緑

- 最小実装の範囲:
  - ★優先★`when`: 簡易ASTベースの安全評価（比較/論理のみ）。プレースホルダ `${...}` は値へ置換後に評価
  - ★優先★`foreach`: `itemVar` を `vars` に束縛し子Planを並列実行、`collect` 出力で配列集約
  - ★優先★`while`: `max_iterations` 上限付きで条件式を反復評価し実行、`collect` で結果配列
  - ★優先★`subflow`: `designs/<plan_id>.yaml` を読み込み実行、子の結果を親の `outputs` マッピングで返却（入力マッピングは未実装）
  - ★優先★ログ: `loop_start/loop_finish/subflow_finish/node_skip` など最小の分岐/ループイベントを出力

- 残タスク:
  - ★優先★`subflow.call.inputs/outputs` の詳細マッピング、`run_id` の親子紐付け、iterationごとの詳細ログ（index/key）
  - ★優先★`foreach/while` の途中エラー時ポリシー、並列上限の動的制御、集約の `reduce` 拡張
  - 式評価のサンドボックス強化（属性アクセス禁止の保証、許可トークン制限）

（対応状況）
- `subflow.call.inputs` の親→子varsマッピング: 完了
- `parent_run_id` 付与と `loop_iter_start/finish`（index）イベント: 完了（keyは未）
- `outputs` 詳細マッピング、`reduce` 集約、サンドボックス強化: 未

—

補足（★優先★対応済の改善）:
- フェーズ2: env参照の静的検証（未設定なら検証エラー）と、入力/出力の型名付き照合（名称一致）を追加
- フェーズ3: ログJSONLのスレッドセーフ化（並列書き込み時の破損防止）
- フェーズ4: subflowのinputsマッピング（親→子vars）をRunnerに実装

### フェーズ5: UI統合（1週）
- 進捗: 完了（`keiri_agent/app.py` 実装、進捗/ログビューア強化、設計フロー統合）
- 目的: 「業務設計」「業務実施」タブの拡張（分岐/ループ表示、サブフロー選択）
- 成果物:
  - 設計タブ: YAMLエディタにテンプレート挿入（`when`/`foreach`/`subflow` スニペット）
  - 実施タブ: ループ/サブフローの進捗/集約結果の可視化、分岐ログの要約
- 完了基準:
  1. UI上でPlanを選択・検証・ドライラン・実行できる（すべてUI操作で完結）
  2. 実行中に分岐結果とループ進捗（完了/総数%表示）が可視化されること
  3. 実行後にログダウンロード（JSONL）が可能で、branch/iteration/subflow項目が含まれること

- 最小実装の範囲:
  - 設計タブ: YAMLエディタ＋検証/ドライラン/保存、Plan自動生成→即時検証/ドライラン→YAML編集→再検証→登録の一連動線
  - 実施タブ: イベントコールバックにより進捗バー/イベント表示、結果JSON表示
  - ログタブ: JSONL読込→イベント種別フィルタ表示、JSON表示、ダウンロード

- 残タスク:
  - ループ/サブフローのネスト可視化（折りたたみ、iteration進捗%）、分岐サマリ（`when`条件/結果）
  - DAG可視化、Planテンプレート作成UI、UIブロックの実装（実ファイルアップロード等）
  - ★優先★APIキー/環境変数の安全入力UI、実行パラメータ（vars）編集UI（対応済）

（対応状況）
- `vars` 編集UI: 追加済み（実行前に数値/真偽/文字で上書き）
- APIキー入力UI: 追加済み（セッションで `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY` を安全格納）

### フェーズ6: 信頼性/体験向上（1週）
- 進捗: 部分達成（`on_error/retry/timeout_ms` 実装・テスト済、ログビューア最低限）
- 目的: リトライ/タイムアウト/条件分岐評価の安全強化、ログビューア
- 成果物:
  - ランナーのポリシー強化（`on_error/retries/timeout`）
  - 条件式サンドボックス化/安全評価（allowlist式）
  - 実行ログの閲覧/ダウンロードUI
- 完了基準:
  1. `on_error=retry` のとき所定回数リトライされる（ログで試行回数が確認可能）
  2. `timeout_ms` 設定時に、長時間処理ノードが中断される（ログにtimeout記録）
  3. 条件式が禁止関数/属性にアクセスできないことをテストで確認（サンドボックス有効）
  4. UIからログ閲覧（最新N件）とダウンロードが可能

- 最小実装の範囲:
  - ポリシー: `on_error`（halt/continue/retry）、`retries`、`timeout_ms`（スレッドFutureで実装）
  - `continue` は空出力として扱い、エイリアスへ未マッピング（None混入を回避）
  - エラーイベントをログに記録、簡易ビューアで表示

- 残タスク:
  - ノード別/カテゴリ別の個別ポリシー、バックオフ/ジッター、キャンセル/中断、UIブロックのタイムアウト
  - より厳格な式サンドボックス、性能計測（cpu/mem/時間）とタイムアウトの強化
  - ログビューアの検索/集計/エクスポート強化、最新N件の取得、警告/異常検知

### フェーズ7: 仕上げ（0.5-1週）
- 目的: ドキュメント整備、サンプル拡充、CI整備
- 成果物:
  - ドキュメント更新（アーキテクチャ/実装計画/使用方法）
  - 代表Plan複数（分岐/ループ/サブフロー含む）
  - CIでフルテスト・Lint・ドライラン検証の自動実行
- 完了基準:
  1. README/Docsが最新仕様（分岐/ループ/サブフロー）を反映
  2. 代表Plan 3本以上が`make test` または `pytest` で全て緑
  3. CI（GitHub Actions等）で Lint+Unit+E2E が緑（最低1回連続実行）

- 進捗: 部分達成（GitHub Actionsでpytest実行まで導入）
- 最小実装の範囲:
  - Ubuntu/Python3.11で `pytest` のみ実行。キャッシュ/並列/アーティファクト保存は未対応
- 残タスク:
  - Lint（ruff/flake8）、型検査（mypy）、カバレッジ収集と閾値、OS/Pythonバージョンmatrix
  - E2E/Streamlitのヘッドレス検証、設計/サンプルPlanの自動ドライラン検証
  - `datetime.utcnow()` の非推奨対応（UTC aware）や警告ゼロ化

---

## 2. ディレクトリ作成（PowerShell）
```powershell
# 実行場所は keiri_agent ワークスペース直下
mkdir core\blocks\processing\ai, core\blocks\processing\excel, core\blocks\processing\file, core\blocks\processing\transforms, core\blocks\processing\validators, core\blocks\ui, core\plan, block_specs\processing, block_specs\ui, designs, designs\common, runs
```

---

## 3. 実装詳細（ファイル別）

### 3.1 core/blocks/base.py
- `BlockContext(BaseModel)`: `run_id`, `workspace`, `vars: dict`
- `class ProcessingBlock:`
  - 属性: `id: str`, `version: str`
  - メソッド: `validate(self)`, `dry_run(self, inputs) -> dict`, `run(self, ctx, inputs) -> dict`
- `class UIBlock:`
  - メソッド: `render(self, ctx, inputs) -> dict`（Streamlitへ描画し、出力返却）

### 3.2 core/blocks/registry.py
- 機能: `block_specs/**/*.yaml` を走査
  - YAMLキー: `id`, `version`, `entrypoint`, `inputs`, `outputs`, `requirements`, `description`
  - `entrypoint`を`importlib`でロードしインスタンス化
  - バージョン解決（最新互換優先/ピン止め）
  - I/OスキーマをPydanticモデル/JSON Schemaで保存

### 3.3 core/plan/models.py
- 追加: `WhenGuard`, `LoopNode(foreach/while)`, `SubflowNode`
- `Plan`, `Node`, `Port`, `Binding`, `Policy`, `UIConfig` を拡張
- 参照式: `${node.output}` `${vars.key}` `${env.KEY}` `${config.task_configs...}`

### 3.4 core/plan/loader.py
- YAML/JSON読込、Pydanticでパース
- 変数解決（env/config/vars）: 検証前は未解決プレースホルダを保持

### 3.5 core/plan/validator.py
- DAG検証: `networkx`で閉路検出
- I/O整合: RegistryのスキーマとPlan配線の型一致
- 未解決参照: `${...}`を静的チェック
- 条件式: `when.expr` の安全評価前検証（許可トークン/関数）
- ループ: `foreach.input` が iterable、`while.max_iterations` 必須
- サブフロー: `plan_id` の存在、入出力マッピング整合
- Excel疎通: `ExcelManager`で`output_config`の列キー/開始行の検査（プレビュー書込）

### 3.6 core/plan/runner.py
- 分岐: `when` 判定→Falseならノードスキップ（ログに分岐結果記録）
- ループ: 
  - `foreach`: 入力の各要素/値で `body.plan` を（最大 `max_concurrency`）並列実行し、`collect`で集約
  - `while`: `condition` を反復評価し上限まで実行
- サブフロー: `loader` で指定 `plan_id` を読み込み、親の一時スコープを継承しつつ実行→exportsを親へ返却
- ポリシー: `on_error`（halt/continue/retry）/ `retries` / `timeout_ms`
- ログ: `branch`, `iteration`, `subflow(parent/child_run_id)`

### 3.7 代表ブロックの実装
- `blocks/processing/file/parse_zip_2tier.py`
  - `FolderProcessor`相当を呼び出しI/O整形
- `blocks/processing/ai/invoice_payment_match.py`
  - `LLMClient.process_accounting_task`相当呼出
- `blocks/processing/excel/write_results.py`
  - `ExcelManager.write_results`相当呼出
- `blocks/ui/file_uploader_evidence.py`, `file_uploader_excel.py`, `confirmation.py`
  - Streamlit UIで入出力を受け渡し

### 3.8 block_specs YAMLの用意
- 代表3処理＋3UIブロックのspecを作成
- CIでspecのスキーマ検証

### 3.9 designs のPlan作成
- `designs/invoice_reconciliation.yaml` を作成
- ループ版（`foreach_data` を含む）とサブフロー版（`designs/common/validate_inputs.yaml`）も追加
- ドライラン合格をゲートにする

### 3.10 UI統合（app.py）
- 新タブ: 「業務設計」「業務実施」
- 設計タブ:
  - ブロックカタログ（Registry一覧）
  - Plan一覧/新規作成（テンプレート）
  - YAMLエディタにスニペット挿入（`when`/`foreach`/`subflow`）
  - 検証/ドライラン/保存
- 実施タブ:
  - Plan選択 → Runner実行
  - 分岐/ループ/サブフローの進捗・結果を可視化
  - 進捗/ログ/結果表示（`CommonUIComponents`再利用）

---

## 4. 既存コードの統合方針
- 考慮不要（`extract_invoice` は参考コードとして参照するのみ。新規構築は `keiri_agent` に実装）

---

## 5. テスト計画
- 単体: Registryロード、参照解決、型検証、DAG閉路検知、ランナーのポリシー挙動
- 条件分岐: `when` True/False 時のスキップ/実行、式評価の安全性
- ループ: `foreach` の並列/集約、`while` の上限制御
- サブフロー: 入出力マッピング、`run_id` の親子紐付け
- 結合: 代表PlanでのE2E（ZIP→AI→Excel）

---

## 6. リスクと軽減策
- 条件式の任意評価 → サンドボックス/許可トークンのみに限定
- 無限/過大ループ → `while.max_iterations` 必須、`foreach.max_concurrency` 上限
- サブフローの深い再帰 → `max_depth` 制限、検証時に警告
- 型ズレ/配線不整合 → 厳密なValidator＆ドライランをゲート

---

## 7. 受け入れ条件（フェーズ横断の総括）
- P1〜P7 の各「完了基準」を満たし、CIで Lint+Unit+E2E が緑であること
- 代表Plan（分岐/ループ/サブフロー含む）でE2E成功、ログが要件を満たすこと
- ドキュメントが最新で、導入者がドキュメントのみで再現可能であること

---

## 8. 工数/目安スケジュール
- 合計 6〜8 週（並行開発可）
  - P1: 1週 / P2: 1週 / P3: 1-2週 / P4: 1-2週 / P5: 1週 / P6: 1週 / P7: 0.5-1週

---

## 9. 変更点一覧（requirements.txt 追記案）
```
PyYAML>=6.0
jsonschema>=4.20
networkx>=3.3
matplotlib>=3.8.0
```

---

## 10. ローンチ後の改善バックログ
- 条件分岐式ビルダー/サジェスト、DAGドラッグ&ドロップ
- 外部SaaS/DB連携ブロック、Webhookトリガ
- 集約演算（reduce）の拡張、分散キューによる大規模並列
- 実行ログのグラフ可視化/ダッシュボード

---

## 11. フェーズ8: 完成形設計の不足実装（architecture.md の反映）

- 目的: 完成形アーキテクチャ（`docs/architecture.md`）に記載の不足実装を補完し、実運用レベルへ引き上げる
- 対象（不足項目）:
  1) 設計/Runner の時刻・タイムゾーン対応（UTC aware）
  2) `${env.KEY}` 参照の解決（安全に読み取り）
  3) サブフロー `call.inputs` のマッピング（親→子vars）
  4) UI可視化の強化（ループ/サブフロー進捗、簡易DAG表示）
  5) CI強化（Lint/型検査/カバレッジ）

- 最小実装（追加済）:
  - RunnerのUTC対応（`datetime.now(datetime.UTC)`）
  - `${env.KEY}` の解決（`os.environ`）、`${config.*}` は将来対応
  - サブフロー `call.inputs` を `vars_overrides` として子へ伝搬
  - UI: 実行進捗のイベントコールバック対応、ログの簡易フィルタ/ダウンロード
  - CI: GitHub Actionsでpytest実行

- 残タスク:
  - UIでのネスト表示（DAG可視化はフェーズ10で対応済）
  - Lint（ruff）/型検査（mypy）/カバレッジ閾値（coverage.py）をCIへ統合
  - `${config.*}` の読み込み機構（設定ファイル/環境変数のマージ）
  - ランナーイベントに `iteration.index`/`parent_run_id` を付加し、トレース性向上

## 12. フェーズ9: 業務設計エンジン（Plan自動生成）

- 目的: ユーザー指示および手順書/マニュアル（pdf/docx/xlsx/md/txt）からPlan（YAML/JSON）を自動生成し、検証/ドライラン/保存まで一気通貫で実行可能にする
- 成果物:
  - `core/plan/design_engine.py`（もしくは `core/design/engine.py`）: 設計エンジン本体
  - Pydanticモデル: 要件抽出レスポンススキーマ（タスク/ブロック候補/入出力/分岐/ループ/サブフロー/UI要件）
  - LLMプロンプト/テンプレ: LangChain + GPT-4.1 + PydanticOutputParser による抽出/整形
  - ブロック選定/配線ロジック: BlockCatalogメタ（tags/I-F）→ノード列・依存・`ui.layout` 生成
  - UI統合（設計タブ）: 指示入力→文書アップロード→プレビュー→ドライラン→保存の操作フロー
- 完了基準（Definition of Done）:
  1. 指示テキスト＋1つ以上の文書を入力し、生成されたPlanが `core/plan/validator.validate()` をエラー0で通過すること
  2. 生成Planのドライラン（Excel仮書込含む）が成功（OK）を返すこと
  3. 生成Planには最低1つ以上のUIブロック（例: ファイルアップロード/確認）が自動挿入されていること
  4. 未解決プレースホルダ（`${vars.*}` 等）が存在する場合、UIに一覧表示され、編集→再検証→保存の一連が可能であること
  5. 保存時に `designs/<slug>_<yyyymmddHHMM>.yaml` 形式でファイルが生成され、UIから選択→実行できること
  6. 自動テスト（少なくとも3系統）
     - 逐次フロー（UI→処理→Excel）
     - UI介在を含む分岐（`when`）
     - 繰り返し（`foreach`）を含むフロー
     がいずれも検証/ドライラン合格かつPlan保存まで成功すること
- 最小実装の範囲:
  - 文書インジェストはテキスト抽出のみ（要約/正規化は簡易）。複数ファイルは結合（上限長でトリム）
  - LLM（LangChain + OpenAI）を標準ルートとし、Pydanticモデルで構造化検証。失敗時はヒューリスティックにフォールバック
  - ブロック選定はカタログ（id/inputs/outputs/description）をプロンプトに渡し、`in/out`キー整合を強制
  - `when`/`foreach` の自動挿入はオプション（UIでON/OFF、CIでは環境変数で制御）
  - 生成後に即時で Validator/ドライランを自動実行。エラーがなければYAML編集→再検証→登録の動線をUI提供
- 残タスク:
  - 抽出精度向上（セクション分類/要件推論/優先度解決）、候補ブロックのランキング改善
  - 高度な配線（サブフロー自動抽出/共通化）、スキーマ充足度のスコア計算
  - テンプレ群の整備（典型業務: 照合/集計/台帳記載 など）、多言語文書の前処理
  - UIでのインタラクティブ修正（DAG可視化/ドラッグ&ドロップ）と差分マージ
  - LLMプロンプト/モデル選択をUIで切替、生成ログの保存/再現

## 13. フェーズ10: 実運用強化（UIブロック実装/`ui.layout`準拠/設定ストア/検証と可観測性の強化）

- 目的: UIブロックの実UI化と実行動線の完成、`${config.*}` 設定ストア対応、Validatorとログ/メトリクスの強化により、プロダクション運用可能な体験・信頼性へ引き上げる。
- 期間目安: 1〜2週

- 成果物:
  - UIブロックのStreamlit実装（スタブ除去）
    - `blocks/ui/file_uploader_evidence.py`: `st.file_uploader(type=["zip"])` で bytes を返却
    - `blocks/ui/file_uploader_excel.py`: `st.file_uploader(type=["xlsx"])` で Workbook もしくは bytes を返却
    - `blocks/ui/confirmation.py`: 選択とコメント入力を提供
  - Runnerの`ui.layout`準拠実行
    - UIブロックは `ui.layout` の順序で逐次実行し、入力が揃うまで後続ノードを待機
    - 非UIブロックは従来通りトポロジカル順＋並列実行
  - 設定ストア（`${config.*}`）の実装
    - `config/` 配下のYAML（例: `task_configs.yaml`, `defaults.yaml`）と環境変数をマージして参照解決
    - UIからプレビュー/一時上書き（実行セッション限定）
  - Validator強化
    - `when.expr` の構文事前検証（許可トークン/比較・論理演算のみ）
    - `foreach.input` が iterable であることの検証（静的に解決可能な場合）
    - `subflow.call.plan_id` の存在と `out` マッピング整合の検証
    - `${config.*}` キー存在の静的検証
  - 可観測性強化（ログ/メトリクス）
    - 各ノードに `elapsed_ms`、リトライ回数、スキップ理由を記録
    - foreachに `iteration.index` に加え可能なら `iteration.key` を記録
    - ログビューアでフィルタ/件数/要約（成功/失敗/スキップ）を表示
  - BlockSpecの `requirements` 活用
    - 依存パッケージ/キーの事前チェックとUI警告（インストール/設定誘導）
  - ドキュメント更新（ユーザーガイド/管理ガイド/設定ガイド）

- 完了基準（Definition of Done）:
  1. 代表Plan（`designs/invoice_reconciliation.yaml`）を、実UI（ファイル選択/承認）でE2E完走できること（スタブに依存しない）
  2. UIブロックの実行順序が `ui.layout` に従い、`when` 条件によりガード/スキップが正しく機能すること
  3. `${config.task_configs...}` などの参照が解決され、キー欠落時はValidatorで検出されること
  4. ログに `elapsed_ms`/`attempt`/`node_skip`/`ui_wait`/`ui_submit` が出力され、ビューアで要約/フィルタ可能であること
  5. テストが追加され、CIで緑（少なくとも5本: UIブロックE2E/`ui.layout`順/`config`解決/Validator強化/ログ属性検証）

- 最小実装の範囲:
  - UIブロック
    - 既存クラスの `render()` をStreamlit実装へ差し替え。テスト時は `KEIRI_AGENT_HEADLESS=1` でスタブ動作にフォールバック
  - Runner
    - 実行順序: トポロジカル順を基準に、UIノードは `ui.layout` の順序で安定ソートして逐次実行
    - `elapsed_ms` を `time.perf_counter()` で計測、イベントに付与
  - 設定ストア
    - `core/plan/config_store.py` を新設し、`load_all()` と `resolve(path: str)` を提供
    - Runnerの `${config.*}` 解決で `config_store.resolve()` を使用
    - Validatorでキー存在と基本型（str/int/bool/list/dict）を静的検証
  - Validator
    - `when.expr` をASTで構文チェック（比較/論理/定数のみ許容）。プレースホルダはダミー値に置換して検証
    - `foreach.input` が `${...}` の場合、解決先の型ヒント/スキーマから配列性を推定（不明時は警告）
    - `subflow.call.plan_id` 参照の存在確認、`out` のキー整合
  - 可観測性
    - ログに `attempt`/`elapsed_ms`/`iteration.{index,key}` を追加
    - ビューアに成功/失敗/スキップ件数のサマリ行を追加
  - テスト/CI
    - 新規テスト: `test_ui_blocks_e2e.py`, `test_validator_config_when.py`, `test_runner_ui_layout.py`, `test_logging_metrics.py`, `test_config_store.py`
    - CIで `KEIRI_AGENT_HEADLESS=1` を設定してUI依存テストをヘッドレス実行

-- 残タスク:
  - 実行時の折りたたみ表示（DAGノード状態の色分けは対応済）
  - ループ集約 `reduce` の追加、途中エラー時のポリシー細分化（per-iteration制御）
  - `requirements` の自動インストール支援（許可された範囲での提案/ドライラン）
  - UIブロックのタイムアウト/キャンセル、部分再実行（ノード/サブグラフ単位）
  - JSON SchemaによるI/O厳密検証（`$ref` 解決と型整合の強化）

- リスクと軽減策:
  - UI依存のテスト不安定 → ヘッドレスモード/スタブ切替、UI部は単体＋統合で二層検証
  - 設定ファイルの肥大化 → 名前空間分割（`defaults.yaml`/`task_configs.yaml`）と読み取り専用のUIプレビュー
  - `when` 式安全性 → AST許可ノード限定と長さ制限、Runner側でも再評価はサンドボックスで実行

- 工数/体制:
  - 実装: 5〜7人日、レビュー/テスト/ドキュメント: 2〜3人日、合計 1〜2週

（対応状況）
- UIブロックのStreamlit実装: 完了（`ui.file_uploader.*`/`ui.confirmation` はヘッドレス時スタブにフォールバック）
- Runnerの`ui.layout`準拠/タイミング計測: 完了（UIノードは`ui.layout`順優先、`elapsed_ms`/`attempts` を `node_finish` に記録）
- 既定HITLオプション: 完了（`PlanRunner(default_ui_hitl)` と `app.py` チェックボックスを追加）
- 設定ストア(`${config.*}`): 完了（YAML/JSON ローダ + `resolve()` 実装、Runner解決/Validator静的検証、UIプレビュー）
- Validator強化: 部分達成（`when.expr` 構文チェック/`${config.*}` 存在検証は完了、`foreach.input` iterable検証は未）
- 可観測性: 部分達成（`elapsed_ms`/`attempts` とログタブのサマリ表示は完了、`iteration.key` は未）
- BlockSpec `requirements` 活用: 未
- テスト/CI: フェーズ10向けの追加テストを追加し、ローカルで16件すべて緑（ヘッドレス）。追加分: `test_config_store.py`, `test_runner_ui_layout.py`, `test_validator_config_when.py`, `test_logging_metrics.py`
