# Keiri Agent CLI Runner

コマンドラインからプランを実行するためのツールです。UIを使用せずにヘッドレスモードでプランを実行できます。

## 機能

- **ヘッドレス実行**: UIブロックを自動処理
- **ファイル入力**: 設定ファイルでファイルパスを指定
- **変数オーバーライド**: 実行時に変数を変更
- **UIモック応答**: 設定ファイルでUIブロックの応答を指定
- **結果出力**: 実行結果とファイルを指定ディレクトリに保存

## インストール

```bash
# 依存関係のインストール
pip install -r requirements.txt

# .envファイルでAPIキーを設定（LLM機能を使用する場合）
echo "OPENAI_API_KEY=your_api_key_here" > .env
```

## 基本的な使用方法

### 1. 基本的な実行

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml
```

### 2. ヘッドレスモードで実行

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml --headless
```

### 3. 変数を指定して実行

```bash
# JSON文字列として指定
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --vars '{"fiscal_year": "2025", "quarter": "Q1"}'

# ファイルから読み込み
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --vars vars.json
```

### 4. 設定ファイルから実行

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --config examples/execution_config.json
```

### 5. ファイル入力を指定

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --files examples/files_config.json
```

### 6. UIモック応答を指定

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --ui-mocks examples/ui_mocks.json
```

### 7. 出力ディレクトリを指定

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --output output/retirement_benefit_q1_2025
```

### 8. 詳細出力

```bash
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --headless --verbose
```

## 設定ファイルの形式

### execution_config.json

```json
{
  "headless_mode": true,
  "output_dir": "output/retirement_benefit_q1_2025",
  "vars": {
    "fiscal_year": "2025",
    "quarter": "Q1"
  },
  "file_inputs": {
    "employees_csv": "data/employees.csv",
    "journal_csv": "data/journal.csv"
  },
  "ui_mocks": {
    "ui.interactive_input": {
      "upload_files": {
        "collected_data": {
          "employees_csv": "auto_resolve",
          "journal_csv": "auto_resolve"
        }
      }
    }
  }
}
```

### files_config.json

```json
{
  "employees_csv": "data/employees.csv",
  "journal_csv": "data/journal.csv",
  "workbook": "data/workbook.xlsx"
}
```

### ui_mocks.json

```json
{
  "ui.interactive_input": {
    "upload_files": {
      "collected_data": {
        "employees_csv": "auto_resolve",
        "journal_csv": "auto_resolve"
      }
    }
  },
  "ui.confirmation": {
    "approved": true,
    "comment": "自動承認"
  }
}
```

## コマンドラインオプション

| オプション | 説明 |
|-----------|------|
| `plan_file` | 実行するPlan YAMLファイルのパス |
| `--headless` | ヘッドレスモードで実行（UIブロックを自動処理） |
| `--config` | 実行設定JSONファイルのパス |
| `--vars` | 変数JSONファイルまたはJSON文字列 |
| `--files` | ファイル入力設定JSONファイルのパス |
| `--ui-mocks` | UIモック応答JSONファイルのパス |
| `--output` | 結果出力ディレクトリのパス |
| `--verbose, -v` | 詳細出力を有効化 |

## ファイル入力の自動解決

`ui.interactive_input`ブロックでファイル入力が必要な場合、以下の方法で自動解決できます：

1. **設定ファイルでの指定**: `file_inputs`セクションでファイルパスを指定
2. **auto_resolve**: UIモックで`"auto_resolve"`を指定すると、設定ファイルのファイルパスから自動読み込み

## 出力

実行結果は以下の形式で出力されます：

- **標準出力**: JSON形式の実行結果
- **結果ファイル**: `{plan_id}_results.json`
- **バイナリファイル**: 実行結果に含まれるバイナリデータ（Excelファイルなど）

## 例

### 退職給付計算プランの実行

```bash
# ヘッドレスモードで実行
python cli_runner.py designs/retirement_benefit_q1_2025.yaml \
  --headless \
  --config examples/execution_config.json \
  --output output/retirement_benefit_q1_2025 \
  --verbose
```

### 請求書照合プランの実行

```bash
# カスタム変数で実行
python cli_runner.py designs/invoice_payment_reconciliation_fixed.yaml \
  --headless \
  --vars '{"company_name": "サンプル株式会社", "threshold": 1000000}' \
  --files examples/files_config.json \
  --output output/invoice_reconciliation
```

## トラブルシューティング

### よくある問題

1. **ファイルが見つからない**: ファイルパスが正しいか確認
2. **UIブロックでエラー**: UIモック応答が正しく設定されているか確認
3. **LLMエラー**: `.env`ファイルでAPIキーが設定されているか確認

### デバッグ

```bash
# 詳細出力で実行
python cli_runner.py your_plan.yaml --headless --verbose

# 設定ファイルの内容確認
cat examples/execution_config.json | jq .
```

## 制限事項

- UIブロックの複雑なインタラクションは設定ファイルでの指定が必要
- ファイル入力は事前に指定されたファイルパスからの読み込みのみ
- 動的なユーザー入力はサポートされていない

## 今後の拡張予定

- より柔軟なファイル入力処理
- 動的UIモック応答の生成
- 実行結果の可視化
- バッチ処理のサポート
