### 概要
`core/plan` は Plan（業務フロー定義）の読み込み・検証・実行・可視化・設計生成の中核モジュール群です。Plan はノード（ブロック）で構成された DAG を表現し、`${vars.*}`/`${env.*}`/`${config.*}`/`$${node.alias}` の参照でデータを受け渡します。

### ファイル構成と役割
- `models.py`: Plan/Node/Policy/UIConfig の Pydantic モデル定義（`in`/`out` はエイリアス対応）。
- `loader.py`: YAML/JSON から Plan を読み込み（`${...}` は未解決のまま保持）。
- `config_store.py`: `${config.*}` の解決ストア。`config/` 配下の YAML/JSON を遅延ロード。
- `validator.py`: 静的検証。Block 存在/入出力キー、`${vars.*}`/`${env.*}`/`${config.*}` チェック、参照整合、DAG 循環、`when.expr` 構文など。
- `graph_utils.py`: 参照プレースホルダから依存グラフを構築する共通関数（`build_dependency_graph`）。
- `runner.py`: 実行エンジン。参照解決、並列実行、ポリシー（retry/timeout/on_error）、UI/HITL、ループ（foreach/while）、サブフロー、JSONL ログ出力。
- `events.py`: 実行イベントの dataclass と dict 化ユーティリティ。
- `logger.py`: ラン ID と JSONL ログの紐付け、`write_event`/`export_log`/`log_metric` を提供。
- `dag_viz.py`: DAG の HTML/CSS 可視化、matplotlib による簡易図、イベント→ノード状態の算出。
- `text_extractor.py`: 添付ファイル群（txt/md/pdf/docx/xlsx）からの軽量テキスト抽出。
- `design_engine.py`: LLM による Plan 生成と検証、必要に応じたフォールバック Plan 生成（環境に応じて許可）。

### 依存グラフ（DAG）共通化
- 依存関係の抽出は `graph_utils.build_dependency_graph(plan)` に集約し、`runner`/`validator`/`dag_viz` から共通利用します。
- `${vars.*}`/`${env.*}`/`${config.*}` はエッジの対象外、`${node.alias[.path]}` を検出してエッジを追加します。
- 文字列の一部に埋め込まれた `${...}` もスキャン対象です。loop（foreach/while）の参照も考慮します。

### エラー設計
- 構造化エラーは `core/errors.py` の `BlockError` と `BlockException` を使用します。`ErrorCode` による分類、`details`/`hint`/`recoverable` を保持。
- ブロック実装では `create_input_error`/`wrap_exception` を推奨（`BlockException` を直接投げるより明快）。
- 設計思想として、Plan 検証失敗時は黙示の自動フォールバックを行わず、エラーを明確に表示する方針です。

### 典型的な使い方
- Plan の読み込み→検証→実行：
```python
from core.blocks.registry import BlockRegistry
from core.plan.loader import load_plan
from core.plan.validator import validate_plan
from core.plan.runner import PlanRunner

registry = BlockRegistry.load_from_dir("block_specs")
plan = load_plan("designs/retirement_benefit_full.yaml")

errors = validate_plan(plan, registry)
if errors:
    raise ValueError("Invalid plan:\n" + "\n".join(errors))

runner = PlanRunner(registry, runs_dir="runs", default_ui_hitl=True)
results = runner.run(plan)
print(results)
```

- LLM による Plan 生成（API キーは `.env` から自動読込可能）：
```python
from core.blocks.registry import BlockRegistry
from core.plan.design_engine import generate_plan, DesignEngineOptions

registry = BlockRegistry.load_from_dir("block_specs")
gen = generate_plan(
    instruction="請求書と入金明細の照合を自動化し差異を出力",
    documents_text=["要件メモ..."],
    registry=registry,
    options=DesignEngineOptions(suggest_when=True, suggest_foreach=True),
)
plan = gen.plan
```

### 実行ログとイベント
- すべての実行は `runs/<plan_id>/<timestamp>.jsonl` に JSONL でイベントを追記します。
- ブロック/テストからは `logger.export_log(data, ctx=ctx, tag=...)` や `logger.log_metric(name, value, ctx=ctx)` を利用可能。
- UI/HITL を有効にした実行は `pending_ui`/`ui_outputs` を `runs/<plan_id>/*.state.json` に保存し、再開・再利用を支援します。
- ヘッドレス実行の手順と標準ディレクトリは `docs/headless_mode.md` を参照してください。

### UI / HITL（Human-in-the-loop）
- `PlanRunner(..., default_ui_hitl=True)` で UI ブロックを待機モードにできます。
- 途中保存された入力は `PlanRunner.find_latest_pending_ui(plan_id)` で取得し、送信後に `runner.run(plan, resume_run_id=...)` で再開します。

### 開発ガイドライン（抜粋）
- 依存グラフは必ず `graph_utils.build_dependency_graph` を使用し、重複実装を避ける。
- `when.expr` の安全評価・構文検証の許可構文は一元管理（将来的に共通ユーティリティ化を想定）。
- 参照解決（`resolve`）はランタイムに委ね、バリデータは静的に判断可能な範囲でのみ厳格化。
- エラーは `core/errors.py` のヘルパを用いて構造化して表現し、ハンドリング方針（halt/retry/continue）は Plan の `policy` に従う。
- ログは `logger.export_log`/`log_metric` を活用し、UI/処理の入出力はサマリ化して記録（生バイトは避ける）。

### テスト
- 迅速な確認：
```bash
pytest -q
```


