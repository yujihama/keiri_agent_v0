## Keiri Agent

経理業務をブロック/DAGで自動化するエージェント実行基盤です。設計（Plan）、ブロック（処理/UI）、実行/検証/可視化、ヘッドレス実行をサポートします。

### フォルダ構成

- `block_specs/`: ブロック仕様（YAML）。`core/blocks` の実装に対応
- `core/`: ランタイム中核
  - `blocks/`: ブロック実装
  - `plan/`: Plan のモデル/ローダ/バリデータ/ランナー/設計エンジン 等
- `designs/`: 業務 Plan（YAML）
- `docs/`: ドキュメント集（本 README からリンク）
- `headless/`: CLI ランナーや既定の設定/出力場所
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


