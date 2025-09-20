## Plan-Based Agent

Plan DSLベースの汎用自動化フレームワークです。ブロックベースの処理をDAGで接続し、設計・実行・検証・可視化を統合的にサポートします。ヘッドレス実行にも対応しています。

### フォルダ構成

- `block_specs/`: ブロック仕様（YAML）。`core/blocks` の実装に対応
- `core/`: ランタイム中核
  - `blocks/`: ブロック実装
  - `plan/`: Plan のモデル/ローダ/バリデータ/ランナー/設計エンジン 等
-  - `ui/`: UIブロックおよびセッションステート等のドメイン側ユーティリティ（プレゼン層に依存しない）
- `designs/`: 業務 Plan（YAML）
- `docs/`: ドキュメント集（本 README からリンク）
- `headless/`: CLI ランナーや既定の設定/出力場所
- `ui/`: Streamlit を用いたプレゼンテーション層（画面タブ・ビュー向けユーティリティ）
  - `tabs/`: 業務設計/実施/ログ 各タブ
  - その他: `flow_viz.py`、`pending_ui.py`、`workbook_artifacts.py` などビュー向けユーティリティ
- `tests/`: pytest テスト一式
- `runs/`: 実行ログ(JSONL)や UI 状態ファイルの既定保存先

### 主要ドキュメント

- [アーキテクチャ概要](docs/architecture.md)
- [ブロックカタログ](docs/block_catalog.md)
- [ヘッドレスモード実行](docs/headless_mode.md)
- [プラン設計と設計エンジン](docs/design.md)
- [コア Plan モジュール解説](docs/core_plan.md)
- [テスト実行ガイド](docs/testing.md)
- [開発・運用ナレッジ](docs/knowledge.md)
- [監査・統制](docs/audit_and_controls.md)
- [将来構想](docs/future_vision.md) / [ロードマップ](docs/roadmap.md)
- [会計タスク要件](docs/accounting_tasks_requirements.md)
- [ユースケース（概要）](docs/use_cases.md) / [ユースケース（詳細）](docs/use_cases_detailed.md)

### クイックスタート

1) 依存関係のセットアップ

```bash
pip install -r requirements.txt
```

2) サンプル Plan をヘッドレス実行

```bash
python headless/cli_runner.py designs/retirement_benefit_q1_2025.yaml --headless -v
```

3) 実行結果/成果物の確認

- `headless/output/<plan_id>/<run_id>/artifacts/` に中間成果物
- `headless/output/<plan_id>_results.json` に最終結果サマリ

### 貢献・開発

- コーディング規約や内部 API の詳細は `docs/core_plan.md` と各モジュールの docstring を参照してください。
- 不具合や提案は Issue / PR にて歓迎します。

### 重要: UI 周辺の設計方針（今回の改修の意図）

1) レイヤ分離（可読性/保守性の担保）
- `core/ui/*`: ドメイン層（ブロック/ランナー側から利用され得るユーティリティ）。Streamlit 等のプレゼンテーション技術に依存しないこと。
- `ui/*`: プレゼン層（Streamlit 画面）。ドメイン層へは依存するが、逆依存は作らない。

2) タブごとの責務分離（肥大化の回避）
- 画面は `ui/tabs/*` に分割し、`app.py` はタブ切替と DI のみを担う。

3) 例外とログの方針統一（ユーザー通知と内部記録の両立）
- ログは `ui.logging`（実体は `core/ui/logging.py` を再エクスポート）を経由。
- 予期可能な軽微例外は `ulog.warn(..., user=False)` で記録のみ。ユーザーへの過剰通知を避ける。
- 回復にユーザー操作が必要/致命的な場合は `ulog.warn/error(..., user=True)` で UI へ通知。
- ログは JSON 構造化・回転ファイル＋コンソール。`plan_id`/`run_id`/`node_id`/`tag` を ContextVar で付加。
- 初期化は `app.py` の `ulog.configure_logging()` に集約。

4) フロー図描画は単一プレースホルダに上書き
- 実行開始時に新規 `st.empty()` を作らず、既存の `dag_area` を共有して二重描画を防止。

5) セッションキーの集中管理
- `ui/state_keys.py` の `SessionKeys` を介して参照。生文字列キーの散在を禁止。

6) UIウィジェット状態のクリア
- `ui/widget_utils.clear_ui_widget_state_for_plan(plan)` を使用し、UIブロックに紐づくキーを一括削除。

7) 成果物抽出の単一実装
- Excel成果物の抽出/表示は `ui/workbook_artifacts.py` の関数群を使用（Planのoutエイリアス優先、重複排除、b64対応）。

8) 改修時の遵守事項（PR チェックリスト）
- `core/ui` → `ui` の依存方向を逆転させない（core から ui を参照しない）。
- 新規例外ハンドリングは `ulog` を経由し、UI表示フラグの意図を明示。
- フロー図の描画先は既存の placeholder を再利用すること。
- セッションキーは必ず `SessionKeys` の定義を経由。
- 既存の共通関数を再実装しない（`ui/*_utils.py` に集約）。


