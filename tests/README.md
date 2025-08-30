## Keiri Agent テストガイド（tests/）

このディレクトリはブロック単体からプラン実行（E2E）までを網羅するpytestスイートです。短時間のスモーク確認からシナリオ別のE2E検証、LLMキー有無での分岐までを含みます。

### すぐに実行する（PowerShell）

```powershell
# ルートへ移動
Set-Location C:\Users\nyham\work\keiri_agent

# 仮想環境を有効化（既存のvenvを使用）
.\venv\Scripts\Activate.ps1

# 文字化け対策（日本語ファイル名を扱うテスト向け）
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

# 代表的なスモーク（素早い）
pytest -q tests\test_block_specs_yaml_cases.py
pytest -q tests\blocks\test_processing_blocks_individual.py -k "read_csv or rename_fields or excel"  # 一部だけ

# ヘッドレスE2E（LLMキー不要、fast-path注入）
pytest -q tests\test_plans_headless_po_and_invoice.py
pytest -q tests\test_runner_e2e.py
pytest -q tests\test_retirement_benefit_e2e.py

# LLM依存テスト（OpenAI/Azureキーが必要）
$env:OPENAI_API_KEY = "<your-key>"   # or $env:AZURE_OPENAI_API_KEY
pytest -q tests\test_plans_llm_embed_excel.py
```

### テスト分類（概要）

- **スペック駆動テスト**
  - `test_block_specs_yaml_cases.py`: `block_specs/*.yaml` を横断し、入力サンプル生成→`run/dry_run/render`→出力型チェック。UI/Processing双方を最小限の入力で検証。
  - `test_block_specs_unit.py`: スペック総数一致、エントリポイントの型（UI/Processing）確認などのメタ検証。

- **ブロック単体テスト**
  - `blocks/test_processing_blocks_individual.py`: CSV, ZIP解析、変換群、データ品質、外部API、署名、スケジューラ、ピボット等の各ブロックを個別に機能検証。
  - `test_unpivot_salary_fix.py`: アンピボット→リパボットの往復で給与シート想定の復元性を検証。

- **プラン/E2E・ヘッドレス**（LLM fast-path注入のためキー不要）
  - `test_plans_headless_po_and_invoice.py`: POコンプラと請求重複検知のプランをヘッドレス実行し、成果物・アーティファクトを検証。
  - `test_runner_e2e.py`: 請求入金照合プランのE2E。ログの基本イベントも確認。
  - `test_retirement_benefit_e2e.py`: 退職給付Q1プラン。Excel内容（シート名/C2/F2）まで検証。

- **LLM依存テスト**（APIキー必須、ない場合はskip）
  - `test_plans_llm_embed_excel.py`: LLMの要約結果がExcelに埋め込まれることを最小限に確認。

- **ランナー/ポリシー/制御構文**
  - `test_policy_retry.py`, `test_policy_timeout.py`: 再試行・タイムアウト方針の挙動。
  - `test_runner_ui_layout.py`: `ui.layout` の並び順を尊重することをイベント順から確認。
  - `test_runner_foreach_when.py`, `test_runner_while_subflow.py`: `when`/`foreach`/`while`/`subflow` の最小シナリオ検証。

- **設計/検証ユーティリティ**
  - `test_design_engine.py`: LLM設計生成→検証/ドライラン。失敗はwarning扱いで進行。
  - `test_validator_and_dryrun.py`, `test_validator_config_when.py`: バリデータの検証と `when` 条件、設定解決の確認。
  - `test_config_store.py`: コンフィグストアの解決テスト。
  - （補足）レジストリ単体のスモークは他テストで担保されるため、個別の `test_registry.py` は削除済み。

### テストデータ/依存

- 入力データは `tests/data` 配下（PO/請求/退職給付など）。
- 退職給付テストは日本語ファイル名を参照します。Windows環境では上記のUTF-8設定を推奨します。
- Excel系は `openpyxl` を使用。ネットワーク系テストは `httpbin.org` を参照しますが、ネットワーク不可環境では例外パスを許容しています。

### 実行上のヒント

- 高速スモーク（~1分）：
  - `pytest -q tests/test_block_specs_yaml_cases.py`
  - `pytest -q tests/blocks/test_processing_blocks_individual.py -k "excel or rename or read_csv"`

- E2Eのみ：
  - `pytest -q tests/test_plans_headless_po_and_invoice.py tests/test_runner_e2e.py tests/test_retirement_benefit_e2e.py`

- LLMテスト有効化：
  - `$env:OPENAI_API_KEY` または `$env:AZURE_OPENAI_API_KEY` を設定して `tests/test_plans_llm_embed_excel.py` を実行。

### 追加/メンテのガイドライン

- 新しいブロックを追加したら：
  - スペック（YAML）を配置 → `test_block_specs_unit.py::test_spec_files_count_matches` が総数一致を検知。
  - `blocks/test_processing_blocks_individual.py` に必要な最小ユニットテストを追加。

- LLMブロックを含むプランのテスト：
  - APIコールを避ける場合は plan に `evidence_data.answer` を注入して fast-path 実行に切替（既存テスト参照）。

- UIブロックのヘッドレスレンダリング：
  - `ui.interactive_input` は `st` をスタブ化（既存テストの `monkeypatch` 参照）。

### 新規ブロック追加時のテスト追加ガイド（必須/推奨）

- **必須: スペック整合性**
  - `block_specs/` にYAMLを配置し、`id`/`version`/`entrypoint`/`inputs`/`outputs` を記述。
  - `dry_run` が安全なダミー出力を返すこと（`test_block_specs_yaml_cases.py` が自動で検証）。
  - 型は可能な限り `string|number|integer|boolean|array|object` を明示。

- **必須: ユニットテスト（Processing）**
  - `tests/blocks/test_processing_blocks_individual.py` に最小のHappy/Edgeケースを追加。
  - 検証例（雛形）:

```python
from core.blocks.base import BlockContext
from core.blocks.processing.my_block import MyBlock

def test_my_block_minimal():
    ctx = BlockContext(run_id="unit")
    blk = MyBlock()
    # 最小入力（specに沿って）
    out = blk.run(ctx, {"foo": "bar"})
    assert isinstance(out, dict)
    assert "result" in out

def test_my_block_dry_run_and_validate():
    blk = MyBlock()
    blk.validate()
    out = blk.dry_run({})
    assert isinstance(out, dict)
```

- **UIブロックのテスト（ヘッドレス）**

```python
import importlib
from types import SimpleNamespace
from core.blocks.base import BlockContext
from core.plan.execution_context import ExecutionContext
from core.blocks.ui.my_ui import MyUIBlock

def test_my_ui_headless_render(monkeypatch):
    # interactive_input を使う場合に備え、streamlitをスタブ
    try:
        mod = importlib.import_module("core.blocks.ui.interactive_input")
        monkeypatch.setattr(mod, "st", SimpleNamespace(error=lambda *a, **k: None, session_state={}), raising=False)
    except Exception:
        pass
    out = MyUIBlock().render(
        BlockContext(run_id="unit"),
        {"message": "Hello"},
        execution_context=ExecutionContext(headless_mode=True)
    )
    assert isinstance(out, dict) and "metadata" in out
```

- **外部依存（HTTP/LLM等）の方針**
  - HTTP: 実環境依存の結果は型レベルで検証し、エラー時は `BlockException` を許容（既存テスト参照）。
  - LLM: 可能なら fast-path（`evidence_data.answer` 注入）を利用。外部キーが必要な場合は `@pytest.mark.llm` と `skipif(not has_llm_keys())` を付与。

- **E2E（任意/推奨）**
  - 新ブロックを含む最小プランをその場でYAML生成して `PlanRunner` で実行し、入出力の結線を検証。
  - LLMを含む場合は fast-path で安定化。

- **共通ユーティリティの活用**
  - `tests/utils.py` の利用を推奨：

```python
from tests.utils import inject_fastpath_for_llm, latest_artifacts_dir, has_llm_keys

# LLM fast-path 注入
inject_fastpath_for_llm(plan, node_outputs={"my_llm_node": {"summary": {}, "items": []}})

# 最新アーティファクト
artifacts = latest_artifacts_dir(tmp_path/"out", "my_plan_id")
```

- **マーカー**
  - E2E系は `@pytest.mark.e2e`、LLM依存は `@pytest.mark.llm` を付与。

### 既知の重複・改善ポイント（提案）

1) `test_block_specs_unit.py` と `test_block_specs_yaml_cases.py` の重複
- どちらもUIレンダ/Processingドライランのスモークを含みます。
- 提案：`unit` 側の以下を削減し、型検証などのメタテストに特化。
  - 候補: `test_processing_blocks_dry_run_smoke`, `test_ui_blocks_headless_render_smoke` は `yaml_cases` がより包括的なため削除。

2) `_latest_artifacts_dir` の重複
- `test_plans_headless_po_and_invoice.py` と `test_plans_llm_embed_excel.py` に同名実装が重複。
- 提案：`tests/utils.py` を作成し共通化。

3) LLM fast-path 注入ロジックの重複
- 複数ファイルで `ai.process_llm` に `evidence_data.answer` を注入するヘルパーが重複。
- 提案：`tests/utils.py` に `inject_fastpath_for_llm(plan)` を実装し共通化。

4) 未使用ヘルパの削除
- `test_runner_e2e.py` と `test_logging_metrics.py` の `_encode_for_json` は未使用。除去可能。

5) `test_registry.py` の冗長化
- 他のテストでレジストリ経由の多数ブロック生成が検証済み。
- 提案：`test_registry.py` は削除、もしくは将来のレジストリ回りリグレッション専用に拡張。

6) 退職給付E2Eの入力存在チェック
- 現状はフォールバック解決だが、ファイル未存在時の `skip` へフォールバックすると開発環境差異に強くなります。

7) マーカー導入（任意）
- `e2e`/`llm` 等のpytestマーカーを導入して、`-m e2e` や `-m "not llm"` で選別実行できるようにすることを推奨。

上記の削減/共通化はテスト実行時間の短縮と保守性向上に効果的です。実施前にチーム方針と合意のうえ適用してください。


