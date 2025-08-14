## ヘッドレスモード実行ガイド

このドキュメントでは、Keiri Agent を UI を使わずにコマンドベースで実行する「ヘッドレスモード」の使い方を説明します。CI/CD パイプラインやサーバー上でのバッチ実行に適しています。

### 概要

- ヘッドレスモードでは、人手を介する UI ブロック（例: `ui.interactive_input`, `ui.confirmation`）を自動処理します。
- ファイルアップロードなどの入力は設定ファイルや引数で与えることができます。
- すべてのノード出力（中間成果物・最終成果物）は自動的に保存されます。

### 事前準備

1. 依存関係のインストール
   - `pip install -r requirements.txt`
2. LLM を利用するプランでは `.env` に API キーを設定
   - `OPENAI_API_KEY` または `AZURE_OPENAI_API_KEY` を設定

### 実行コマンド（プロジェクトルートから）

ヘッドレス実行は `headless/cli_runner.py` を利用します。

```bash
# 基本
python headless/cli_runner.py designs/your_plan.yaml --headless

# 変数の指定（ファイル or JSON 文字列）
python headless/cli_runner.py designs/your_plan.yaml --headless --vars vars.json
python headless/cli_runner.py designs/your_plan.yaml --headless --vars '{"key":"value"}'

# ファイル入力の指定
python headless/cli_runner.py designs/your_plan.yaml --headless --files headless/configs/files_config.json

# UI モック応答の指定
python headless/cli_runner.py designs/your_plan.yaml --headless --ui-mocks headless/configs/ui_mocks.json

# 出力ディレクトリの指定
python headless/cli_runner.py designs/your_plan.yaml --headless --output headless/output/your_plan
```

### 設定ファイル形式と既定値

- `--config`（統合設定。任意の JSON ファイルを指定）
- `--files`（ファイル入力）: 省略時は `headless/configs/files_config.json` が存在すれば自動採用
- `--ui-mocks`（UI ブロックの応答）: 省略時は `headless/configs/ui_mocks.json` が存在すれば自動採用

### 中間成果物の保存（ヘッドレス時の既定動作）

ヘッドレスモードでは、各ノードの出力を自動的に保存します。保存場所は以下です。

- `--output` 指定あり: `<output>/<plan_id>/<run_id>/artifacts/`
- `--output` 指定なし（CLI 既定）: `headless/output/<plan_id>/<run_id>/artifacts/`
- ライブラリ利用で出力先未設定の場合: `runs/<plan_id>/<run_id>/artifacts/`

保存内容:
- `<node_id>_outputs.json`: ノード出力のスナップショット（`bytes` は Base64 でエンコード）
- バイナリ成果物（Excel など）: 出力辞書に `bytes`（または `base64`）が含まれる場合は自動的にファイルとして保存
  - `name` キーがあればファイル名に利用（なければ `<node_id>_...` 由来の安全なファイル名）

例:
- `excel.update_workbook` の出力 `{ name: "result.xlsx", bytes: <...> }` は `result.xlsx` として保存
- `... { base64: "..." }` の場合は Base64 をデコードして保存

### UI ブロックの挙動

- `ui.interactive_input`:
  - `--files` で指定された `file_id` と一致する項目は自動で読み込み
  - その他フィールドは `default` 値または簡易な自動入力で補完
  - `--ui-mocks` が指定されている場合はその応答を最優先で採用
- `ui.confirmation` / `ui.placeholder`: 既定で自動承認/自動確定

### 例: 退職給付計算プランの実行

```bash
# 1) 統合設定 + 出力先指定
python headless/cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --headless \
  --config path/to/execution_config.json \
  --output headless/output/retirement_benefit_q1_2025

# 2) 変数/ファイル個別指定
python headless/cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --headless \
  --vars '{"fiscal_year":"2025","quarter":"Q1"}' \
  --files headless/configs/files_config.json \
  --output headless/output/retirement_benefit_q1_2025
```

### トラブルシューティング

- LLM キーが未設定: `.env` に `OPENAI_API_KEY` または `AZURE_OPENAI_API_KEY` を設定してください
- ファイルが見つからない: `--files` のパスと `ui.interactive_input` の `id` を確認
- 文字列 JSON（PowerShell）: 引数のクォート方法に注意。ファイルで渡すのが安全です

### 実装メモ（開発者向け）

- ランナーは `execution_context.headless_mode` を参照し、UI ブロックを自動処理
- 中間成果物保存は `PlanRunner._save_node_outputs` にて実装
  - `bytes`/`base64` を検出してファイル保存
  - 常に `<node_id>_outputs.json` を併せて保存
- 出力先は `--output` または未指定時の既定に応じて `<plan_id>/<run_id>/artifacts/` を利用
