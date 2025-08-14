## 開発・運用ナレッジ（Keiri Agent／社内向け）

本ドキュメントは、UI 実行とヘッドレスモード、ログの入れ方/見方、ブロックの考え方、新規ブロック作成時の作法・設計思想、そして pytest による検証ガイドを社内向けに詳細化したものです。

### 実行モード: UI とヘッドレス

- UI 実行
  - UI ブロック（`ui.*`）は Streamlit で描画され、ユーザーの入力/承認を収集します。
  - 実行エンジンの `PlanRunner(..., default_ui_hitl=True)` を用いると、UI ブロックで待機し、人手入力を受け付ける運用が可能です。
  - 実行状態（`pending_ui`/`ui_outputs`）は `runs/<plan_id>/*.state.json` に保存され、途中再開ができます。

- ヘッドレス実行
  - UI を使わず CLI で自動実行します。CI/CD・サーバー実行に適します。
  - 推奨: ルートから次のコマンド（詳細は `docs/headless_mode.md`）。
    ```bash
    python headless/cli_runner.py designs/your_plan.yaml --headless \
      --files headless/configs/files_config.json \
      --ui-mocks headless/configs/ui_mocks.json \
      --output headless/output/your_plan
    ```
  - `--files` は UI 入力の代替（ファイルID → 実ファイルパス）。`--ui-mocks` は UI ブロックのモック応答。
  - 中間成果物は `<output>/<plan_id>/<run_id>/artifacts/`（未指定時は `headless/output/...`。ライブラリ直呼びで未設定の場合は `runs/...`）。

### ログの入れ方・見方

- どこに出力されるか
  - すべての実行イベントは JSONL として `runs/<plan_id>/<timestamp>.jsonl` に追記されます。
  - ヘッドレス時は各ノード出力スナップショットが `<...>/artifacts/<node_id>_outputs.json` に保存されます（`bytes` は Base64 化）。

- ブロックからのログ出力
  - 便利関数を利用します（`ctx` は `BlockContext`）。
    ```python
    from core.plan.logger import export_log, log_metric

    # デバッグ/構造化ログ（type=debug, tagで絞り込みやすく）
    export_log({"rows": 120, "sheet": "Employees"}, ctx=ctx, tag="excel.read_data")

    # メトリクス（type=metric）
    log_metric("rows_processed", 120, ctx=ctx, tags={"table": "employees"})
    ```
  - 大きな配列/バイト列はそのまま出さず、件数やサイズのサマリを推奨。

- ログの見方（PowerShell 例）
  - 最新の JSONL を見る:
    ```powershell
    Get-ChildItem runs/<plan_id>/*.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 200
    ```
  - メトリクスのみ抽出:
    ```powershell
    $log = Get-ChildItem runs/<plan_id>/*.jsonl | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Get-Content $log | ForEach-Object { $_ | ConvertFrom-Json } | Where-Object { $_.type -eq 'metric' }
    ```

### ブロックの考え方

- ブロック種別
  - 処理ブロック: `ProcessingBlock` を継承し `run(ctx, inputs)` を実装。可能な限りステートレス・副作用なし。
  - UI ブロック: `UIBlock` を継承し `render(ctx, inputs, execution_context=None)` を実装。Streamlit で描画し、ヘッドレス時は自動応答。

- スペック（YAML）とレジストリ
  - `block_specs/` に `id`, `version`, `entrypoint`, `inputs`, `outputs`, `requirements` 等を記述。
  - 実行時は `BlockRegistry.load_specs()` が YAML を読み込み、`entrypoint` 先のクラスを動的にインスタンス化します。
  - 同じ `id` に複数バージョンがある場合、基本的に最も高いセマンティックバージョンが選ばれます。

- 参照とデータフロー
  - Plan（DAG）内では `${nodeId.outputKey}` や `${vars.name}` のような参照でデータを受け渡します。
  - ランタイムが参照を解決し、ブロック `inputs` に渡します。

### 新規ブロック作成: 作法と設計思想

1) スペック（YAML）の追加
   - 例:
     ```yaml
     id: my.company.normalize_text
     version: 0.1.0
     entrypoint: blocks/processing/text/normalize.py:NormalizeTextBlock
     inputs:
       text: { type: string, description: "入力テキスト" }
     outputs:
       normalized: { type: string, description: "正規化済みテキスト" }
     requirements: []
     description: "テキスト正規化（全角/半角、空白、改行など）"
     ```

2) 実装クラス（Python）
   - 例（処理ブロック）:
     ```python
     from typing import Dict, Any
     from core.blocks.base import ProcessingBlock, BlockContext
     from core.plan.logger import export_log
     from core.errors import create_input_error, ErrorCode, BlockException

     class NormalizeTextBlock(ProcessingBlock):
         id = "my.company.normalize_text"
         version = "0.1.0"

         def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
             text = inputs.get("text")
             if not isinstance(text, str):
                 raise create_input_error("text", "string", text)

             normalized = self._normalize(text)
             export_log({"len_before": len(text), "len_after": len(normalized)}, ctx=ctx, tag="normalize_text")
             return {"normalized": normalized}

         def _normalize(self, s: str) -> str:
             # 必要な正規化のみ。外部状態や副作用は避ける
             return " ".join(s.split())
     ```

   - 例（UI ブロックのヘッドレス対応ポイント）:
     ```python
     from core.blocks.base import UIBlock, BlockContext
     from typing import Dict, Any, Optional

     class MyUIBlock(UIBlock):
         id = "ui.my_block"
         version = "0.1.0"

         def render(self, ctx: BlockContext, inputs: Dict[str, Any], execution_context: Optional[Any] = None) -> Dict[str, Any]:
             if execution_context and getattr(execution_context, "headless_mode", False):
                 mock = execution_context.get_ui_mock_response(self.id, inputs.get("node_id", ""))
                 return mock or {"approved": True, "metadata": {"submitted": True}}
             # ここで Streamlit UI を描画して値を返す
             ...
     ```

3) エラーハンドリング
   - 入力検証エラーなどは `core.errors` のヘルパを使用して構造化します。
     ```python
     from core.errors import create_input_error, wrap_exception, ErrorCode, BlockException
     # 例: 型不一致
     if not isinstance(x, int):
         raise create_input_error("x", "int", x)
     # 例: 外部呼び出しのラップ
     try:
         call_external()
     except Exception as e:
         raise wrap_exception(e, ErrorCode.EXTERNAL_API_ERROR, inputs)
     ```
   - 例外は極力 `BlockException` に包み、`details`/`hint`/`recoverable` を活用して利用者に解決策を示します。

4) ロギング指針
   - 大きなデータはサマリ（件数、長さ、代表値）をログに出し、個人情報・生バイトは避けます。
   - `tag` は `<カテゴリ>.<ブロックID>` などで一貫性を持たせてフィルタしやすくします。

5) 出力形式の作法
   - バイナリを返す場合は `{ name: "file.xlsx", bytes: <bytes> }` または `{ name: "file.bin", base64: "..." }` とする（ヘッドレス時に自動保存されます）。
   - JSON 互換の値を基本とし、日時は ISO 文字列を推奨。

6) 依存・バージョニング
   - 外部依存はスペックの `requirements` に列挙し、必要に応じて `requirements.txt` を更新。
   - 後方互換を壊す変更は `major` を上げて新バージョンとして提供（旧版は残す）。

7) テスト
   - 可能なら pytest で最小の動作テストを用意。`tests/` の例や `docs/testing.md` を参照。

### 社内ベストプラクティス（開発標準）

- 命名規約
  - ブロックID: `<ドメイン>.<カテゴリ>.<機能>` で小文字・ドット区切り（例: `excel.read_data`, `table.pivot`, `ai.process_llm`）。社内固有は `jp.<dept>.<feature>` などのプレフィックスを検討。
  - Plan/Node ID: 英小文字と `_` 推奨。意味のある名詞句（例: `read_salary`, `match_with_ledger`）。
  - 出力のエイリアス: 消費側から見て意味が明確な名詞句（例: `rows`, `workbook_updated`, `item_result_list`）。

- データとセキュリティ
  - PII/機微情報はログに生値を出さない。必ず件数・長さ・ハッシュなどのサマリで記録。
  - `.env` の API キーや資格情報はログに出力しない。`export_log` でも値をマスクする。
  - ファイル入出力は `ExecutionContext.output_dir` とアーティファクト自動保存を活用し、作業ファイルをリポジトリ外に出す。

- 例外と復旧
  - 入力不正や外部連携エラーは `core.errors` のヘルパで構造化し、`hint` に具体的対処を記載。
  - リトライ/タイムアウト等は Plan の `policy` で制御。ブロック側では無制限待ち/リトライを実装しない。

- 実行特性
  - 決定的に（同じ入力で同じ出力）。非決定化が必要な場合は理由と制約を docstring で明示。
  - 大きな処理はストリーミング/チャンク化を検討し、メモリスパイクを避ける。
  - ThreadPool 等の並列化はランナー側が担う。ブロック内の独自スレッドは避ける。

- ログ運用
  - `export_log` の `tag` は `<カテゴリ>.<ブロックID>` か `<機能>.<詳細>` で統一。
  - メトリクスは `log_metric(name, value, tags={...})` を使い、ダッシュボード化を意識した粒度で。

- レビュー観点
  - スペック（YAML）と実装の入出力キー/型の齟齬がないか。
  - エラーハンドリングが `BlockException` で構造化されているか。
  - ヘッドレス対応（UI ブロック）と `ExecutionContext` 利用が適切か。
  - テストで `tmp_path` を使い副作用を隔離しているか。

### pytest 実務ガイド（社内用詳細）

- 実行の基本
  - 全体実行: `venv\Scripts\python -m pytest -q`
  - 部分実行（キーワード）: `-k <keyword>` 例: `-k retirement`
  - 再実行（失敗のみ）: `-q --last-failed`（必要に応じて）

- LLM 必須/不要テストの扱い
  - LLM 不要スモーク（ロジック検証）: `tests/test_runner_ui_layout.py`, `tests/test_runner_foreach_when.py`, `tests/test_runner_while_subflow.py`, `tests/test_validator_and_dryrun.py` など。
  - LLM 必須 E2E: `tests/test_retirement_benefit_e2e.py`, `tests/test_runner_e2e.py`。`.env` に `OPENAI_API_KEY` または `AZURE_OPENAI_API_KEY` が必要。
  - 社内運用の推奨: CI は LLM 不要スモークを既定、E2E は nightly や手動トリガで実行。

- テスト実装パターン
  - `tmp_path` を利用して出力/ランログ/アーティファクトを隔離。
  - UI 依存の回避: `ExecutionContext(headless_mode=True, ui_mock_responses=...)` を使い、UI を自動応答化。
  - ファイル入力は `file_inputs={id: Path(...)}` で渡す（`ui.interactive_input` の `auto_resolve` と連動）。
  - LLM ブロックの高速化: 既存テストのように `evidence_data.answer` を事前注入し、ネットワーク呼び出しを省略。
  - ログ検証: `runs/<plan_id>/*.jsonl` を読み、`start/node_start/node_finish/finish` の整合を確認。

- 例: 最小のヘッドレス実行テスト
  ```python
  from pathlib import Path
  from core.blocks.registry import BlockRegistry
  from core.plan.loader import load_plan
  from core.plan.runner import PlanRunner
  from core.plan.execution_context import ExecutionContext

  def test_headless_min(tmp_path: Path):
      reg = BlockRegistry(); reg.load_specs()
      plan = load_plan(Path("designs/your_plan.yaml"))
      exec_ctx = ExecutionContext(headless_mode=True, output_dir=tmp_path/"out")
      runner = PlanRunner(registry=reg, runs_dir=tmp_path/"runs")
      res = runner.run(plan, execution_context=exec_ctx)
      assert isinstance(res, dict)
  ```

- マーキング（任意の社内規約）
  - 将来的に `@pytest.mark.llm` や `@pytest.mark.e2e` を導入する場合は、`pytest.ini` に登録し `-m llm` などで切替可能にする運用を推奨（現状のテスト群は未マーク）。

- Windows PowerShell Tips
  - 長いコマンドはバッククォートで改行（`-k` や複数ファイル指定時）。
  - JSON 文字列を引数で渡す場合はクォートを厳密に。ファイルで渡す方が安全。

### 参考リンク

### 参考リンク

- 実行ガイド（ヘッドレス）: `docs/headless_mode.md`
- コア Plan モジュール: `docs/core_plan.md`
- ブロックカタログ: `docs/block_catalog.md`
- テストガイド: `docs/testing.md`
  - 実際のテストファイル/構成、PowerShell 前提の実行コマンド、LLM 必須/不要の切り分け例を掲載。


