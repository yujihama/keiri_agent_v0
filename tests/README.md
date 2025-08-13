# Pytest 実行ガイド（Keiri Agent）

このドキュメントは、本リポジトリのpytest実行方法・前提条件・テスト構成・トラブルシューティングをまとめた専用の手引きです。Windows PowerShell 前提のコマンドを記載します。

## 前提条件

- Python 3.10+ 推奨
- 依存関係はプロジェクトルートの `requirements.txt` に定義
- LLMを使うテストでは `.env` に以下のいずれかが必要
  - `OPENAI_API_KEY=<your key>` もしくは `AZURE_OPENAI_API_KEY=<your key>`
  - 任意: `KEIRI_AGENT_LLM_MODEL`（既定: `gpt-4.1`）、`KEIRI_AGENT_LLM_TEMPERATURE`（既定: `0`）

## セットアップ（初回）

```powershell
cd C:\Users\nyham\work\keiri_agent
if (Test-Path .\venv\Scripts\Activate.ps1) { .\venv\Scripts\Activate.ps1 } else { py -3 -m venv venv; .\venv\Scripts\Activate.ps1 }
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
```

## データ配置

- E2Eテストは `tests/data/` 配下の実ファイルを使用します（モック/スタブ不使用）
  - 退職給付: `tests/data/retirement_data/`（CSVとExcel）
  - 請求照合: `tests/data/test_evidence.zip`, `tests/data/test_workbook.xlsx`

## テストの種類と方針

- LLM必須（実キーで実行。モック/スタブは禁止）
  - `tests/test_retirement_benefit_e2e.py`（`designs/retirement_benefit_q1_2025.yaml`）
  - `tests/test_runner_e2e.py`（`designs/invoice_payment_reconciliation_fixed.yaml`）
  - `tests/test_logging_metrics.py`（上記請求照合Planのログ検証）
  - `tests/test_design_engine.py`（LLM設計生成）。生成結果が検証要件を満たさない場合は `skip` します

- LLM不要（ロジック/実行基盤の検証）
  - `tests/test_runner_ui_layout.py`
  - `tests/test_runner_foreach_when.py`（動的に最小Planを生成）
  - `tests/test_runner_while_subflow.py`（動的に最小Planを生成）
  - `tests/test_validator_and_dryrun.py`
  - `tests/test_config_store.py`
  - `tests/test_policy_retry.py`, `tests/test_policy_timeout.py`
  - `tests/test_registry.py`

## 実行方法

- 全テスト
  ```powershell
  venv\Scripts\python -m pytest -q
  ```

- LLM不要スモークのみ（例）
  ```powershell
  $env:KEIRI_AGENT_HEADLESS='1'  # UIがあってもブロックしない
  venv\Scripts\python -m pytest -q `
    tests/test_runner_ui_layout.py `
    tests/test_runner_foreach_when.py `
    tests/test_runner_while_subflow.py `
    tests/test_validator_and_dryrun.py -q
  ```

- LLM必須E2Eのみ（.envキーが必要）
  ```powershell
  venv\Scripts\python -m pytest -q `
    tests/test_retirement_benefit_e2e.py `
    tests/test_runner_e2e.py `
    tests/test_logging_metrics.py -q
  ```

- テスト名やキーワードで絞り込み
  ```powershell
  venv\Scripts\python -m pytest -q -k retirement
  ```

## 実装上の注意（テスト設計ポリシー）

- LLM機能は本物のAPIキーを用いて実行します（モック/スタブは使用しません）
- UI入力が必要なPlanは、ランナーの状態ファイル（`runs/<plan_id>/<run_id>.state.json`）にUI出力を事前投入して自動化します
  - 例（概念）：
    ```json
    {
      "ui_outputs": {
        "upload_files": {"collected_data": {"...": "..."}},
        "ui_confirm": {"approved": true}
      },
      "pending_ui": null
    }
    ```
  - テストでは上記ファイルを作成した上で `PlanRunner.run(..., resume_run_id=...)` を呼びます
- 実行ログは `runs/<plan_id>/*.jsonl` にJSONL形式で出力されます（`start`/`node_start`/`node_finish`/`finish`）
- 設計エンジンのLLM生成テスト（`tests/test_design_engine.py`）は、LLMが要件を満たすPlanを返さない場合に `pytest.skip` でスキップします
  - 設計思想（フォールバック禁止）に合わせ、生成失敗時の自動フォールバックは使いません

## よくあるエラーと対処

- `OPENAI/AZURE... APIキーが未設定` エラー
  - `.env` に `OPENAI_API_KEY` または `AZURE_OPENAI_API_KEY` を設定してください

- LLM生成が検証で失敗（`output_schema`未設定など）
  - `tests/test_design_engine.py` はスキップ扱い。E2E（請求/退職）で実動を担保します

- PowerShell の出力が崩れる/例外（PSReadLine）
  - コマンドラインが長すぎる場合に発生することがあります。コマンドを分割して実行してください

## 環境変数（参考）

- `OPENAI_API_KEY` / `AZURE_OPENAI_API_KEY`: LLM実行で必須
- `KEIRI_AGENT_LLM_MODEL`: 既定 `gpt-4.1`
- `KEIRI_AGENT_LLM_TEMPERATURE`: 既定 `0`
- `KEIRI_AGENT_HEADLESS`: `1`でUIブロックがダミー応答（LLM不要スモーク時に有用）
- `KEIRI_AGENT_FORCE_UI`: `1`で保存済みUI出力の再利用を無効化（通常は不要）

## 付記

- `tests/` 直下の手動実行スクリプトは削除され、pytestベースに統一されています
- 実行時間や外部APIの都合で、LLM関連テストは時間がかかる場合があります


