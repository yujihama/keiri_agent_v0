## プラン自動生成 仕様と実装計画（機能仕様）

### 目的・範囲
- **目的**: 指示テキストと参考ドキュメントから、誤設計を最小化しつつ即実行可能な Plan YAML を高精度に自動生成する。
- **範囲**: 生成のための機能仕様（UI/UX、テンプレート、LLM生成、検証、チャット収集、テンプレ合成、自己修復）。非機能（性能/運用/テスト/セキュリティ詳細）は対象外。

### 用語
- **ブロックカタログ**: `block_specs/` に定義されたブロックスペックの一覧。
- **テンプレート**: 再利用可能な部分フローの定義（YAML）。`designs/templates/` に配置。
- **合成**: 複数テンプレートを I/O 契約に従って安全に連結すること。
- **設計チャット（Designチャット）**: 設計時に不足要件を対話で収集する UI（`ui.interactive_input` の `mode: inquire` 相当の機能を Design タブ内で提供）。
- **実行チャット（Runtimeチャット）**: 実行時に Plan 先頭へ `ui.interactive_input` ノードを挿入し、必要情報を収集する仕組み。

---

## 現状実装サマリ（2025-08 時点）
- **LLM生成の中核**: `core/plan/design_engine.py` の `generate_plan()` が、LLM へブロック一覧（`id/inputs/outputs/description`）と指示/文書を渡し、構造化出力（Pydantic）で `LLMDesignModel` を受領し Plan を構築。
  - 構造化出力は `with_structured_output(LLMDesignModel, method="function_calling")` を使用。
  - 連結ドキュメントは最終的に約 4,000 文字へ正規化（内部正規化＋`docs_joined[:4000]`）。
- **静的検証/ドライラン**: `core/plan/validator.py` の `validate_plan()` と `dry_run_plan()` を使用。検証失敗時はフォールバックしない（設計思想）。
  - 例外的に `KEIRI_AGENT_LLM_FALLBACK` が `1/true/yes` の場合のみ安全なフォールバック Plan を返す。
- **文書抽出**: `core/plan/text_extractor.py` が `.txt/.md/.pdf/.docx/.xlsx` をサポートし、最大合計 ~100,000 文字まで抽出 → 生成側で ~4,000 文字に圧縮。
- **Designタブ UI**: `ui/tabs/design.py` で指示テキスト、ファイルアップロード、`自動生成` ボタン、検証/ドライラン実行、YAML 表示/編集に対応。
- **LLM ブロック**: `ai.process_llm` は `output_schema`（非空オブジェクト）必須。`prompt` 未指定時は `instruction` を利用。画像の添付や表の先頭行取り込み閾値は入力/環境変数で制御可能。

注: 本ドキュメントに記載の「テンプレート合成」「Top-K Retrieval」「自己修復の反復」などは仕様として定義し、実装は段階的に導入する（未実装/部分実装箇所あり）。

---

## 理想的な仕様

### 1. ユーザーフロー（Designタブ）
1) ユーザーは以下を入力/選択する。
   - 指示テキスト
   - 参考ドキュメント（任意、複数）
   - テンプレート（複数選択可・任意）
2) 「自動生成」ボタンを押下すると生成を開始。
3) プラン生成のために不足項目がある場合、自律的にDesignチャットで対話収集（複数ターン）。チャットは「C:\Users\nyham\work\keiri_agent\block_specs\ui\ui.interactive_input.yaml」を流用すること。
4) 生成器は下記の規則で Plan を構築し、検証/ドライラン、エラーの場合は修復まで行う。
5) 問題なければ YAML を編集可能領域に表示し、ユーザーは「検証/ドライラン」「登録」で保存。

### 2. 文書抽出と正規化
- サポート拡張子: `.txt`, `.md`, `.pdf`, `.docx`, `.xlsx`。
- 抽出レイヤ（extractor）: 最大合計 ~100,000 文字まで抽出し、ファイル毎に軽量パース（PDF は先頭 20 ページ、XLSX は先頭シートの左上範囲をテキスト化）。
- 生成レイヤ（design engine）: 抽出結果を空白圧縮・冗長削除のうえ、最終連結 ~4,000 文字へ正規化（トークン安定のため）。
- 実装要点:
  - 例外時は無音失敗せず、抽出ゼロ扱いとして LLM プロンプト内でシグナル化（"no documents provided"）。
  - セキュリティ: 取り込みは平文化済みのみに限定し、暗号/埋め込み画像データは無視。

### 3. ブロック候補の Top-K 絞り込み（Retrieval）
- 目的: LLM の探索空間を縮小し、誤設計とハルシネーション（hallucination）を抑制。
- アルゴリズム（段階導入）:
  1) ルールベース: `id/description` の BM25 類似度、`inputs/outputs` の語彙マッチ、カテゴリタグで事前フィルタ。
  2) 埋め込み: ブロック `id/description/入出力名` を埋め込み化し、指示/文書の埋め込みとコサイン類似で Top-K。
  3) ハイブリッド: 1) と 2) のスコアを正規化合成。
- 出力: カテゴリ別に最大 K=5〜8 件（合計 30 件以内）を LLM へ提示。UI にも候補一覧を表示。
- 実装メモ: 初期は 1) のみ、後続で 2)/3) を追加。

### 4. テンプレート活用
- ユーザーは `designs/templates/` のテンプレを複数選択可能。
- 選択テンプレの骨子（要約）とスニペットを Few-shot/制約として LLM に投入し、尊重生成を促す。
- テンプレのメタ定義（最小仕様）:
  - `id`, `title`, `description`, `tags`
  - `imports`: 期待入力（論理名→型）
  - `exports`: 提供出力（エイリアス→型）
  - `graph_snippet`: そのまま `graph` に差し込める部分 YAML
- 合成ルール（compose）:
  - ノード `id` はユニーク化（テンプレ ID を接頭辞に付与）。
  - `imports` は Plan の `vars`/既存出力へバインド。欠落は `${vars.*}` として明示。
  - `exports` は上位 Plan の `out` エイリアスへ連結可能。競合は明示解決（UI 提示）。

### 5. プラン生成（LLM）
- 構造化出力（関数呼び出し/JSON Schema 準拠）で `LLMDesignModel` を返す。
- 動的制約:
  - `block` は Top-K 候補とテンプレ内ブロックに限定（リストを `Literal[...]` としてモデル化）。
  - `in/out` のキーは各ブロック定義のホワイトリストに限定。
  - `ai.process_llm` には `output_schema`（非空オブジェクト）必須、`prompt` または `instruction` の少なくとも一方必須。
- 2段生成:
  - 段1（骨子）: 入→変換→出力の大まかな流れ、必要 UI、ループ/サブフローの有無を決定。
  - 段2（配線）: 段1の骨子を固定し、`in/out` を型・語彙近似・テンプレ契約に基づき自動接続。曖昧箇所は `${vars.*}` を明示し、`vars` に必ず定義。
- 各段において不足情報があれば上述の通り自律的に問い合わせを行う。

#### 5.1 プロンプト設計（実装準拠）
- System: 「あなたは業務設計エンジン…」＋制約列挙＋出力は JSON のみ。
- Human: 指示テキスト、正規化済み文書（~4,000 字）、Top-K ブロックのカタログ（`id/inputs/outputs/description`）、選択テンプレの要約/スニペット。
- 構造化出力: `llm.with_structured_output(LLMDesignModel, method="function_calling")` でパース（失敗時のみ Free-form→JSON 抽出）。

#### 5.2 LLMDesignModel（概念）
```json
{
  "id": "string",
  "version": "string",
  "vars": {"key": "any"},
  "policy": {"on_error": "continue|stop", "retries": 0},
  "ui": {"layout": ["string"]},
  "graph": [
    {
      "id": "string",
      "block": "optional string",
      "type": "optional string",  
      "in": {"key": "value-or-${...}"},
      "out": {"local_out_key": "alias"},
      "when": {"expr": "${...} == ..."},
      "foreach": {"items": "${...}", "var": "item"},
      "while": {"condition": {"expr": "..."}, "max_iterations": 3},
      "body": {"plan": {"graph": [/* nodes */]}},
      "call": {"plan_id": "string", "inputs": {"...": "..."}}
    }
  ]
}
```

#### 5.3 生成後処理
- `Plan` 変換時に `by_alias` で正規化し、`validate_plan()` を直後に実行。
- `KEIRI_AGENT_LLM_FALLBACK` 無効時は検証エラーをそのまま表示し、フォールバックしない（設計思想）。
- 有効時のみ `_build_fallback_plan()` を使用。

### 6. 自己修復
- 静的検証でのエラー（キー不一致/型不整合/未定義参照/循環/DAG不正/`ai.process_llm` 規則違反 など）を要点化し、最大 N 回まで LLM へ差し戻し。
- 差し戻しプロンプトには以下を含める:
  - エラー概要のリスト（人間可読）
  - 対象ブロック spec 抜粋（入力/出力キー/型/説明）
  - 直前出力との差分（ノード単位の変更点）
  - テンプレ契約の該当部（必要時）
- 成功条件: 検証エラーが 0。失敗時は UI にエラーを提示し、修正提案（不足項目→チャット起動、テンプレ追加の推奨）を表示。
- 実装段階: v1 は 0 回（差し戻しなし）→ v1.1 で `max_attempts=2` の反復を追加。

### 7. Designチャット
- プラン生成において不足している情報があれば `requirements` を生成し、「C:\Users\nyham\work\keiri_agent\block_specs\ui\ui.interactive_input.yaml」の inquire モードを流用して情報収集する。
- 要件ビルダーの仕様（概念）:
  - 入力: `plan` または `validate_plan()` のエラー一覧
  - 出力: `Requirement[]`
```json
{
  "id": "string",
  "type": "text|select|boolean|number|file|table|enum",
  "label": "表示名（任意）",
  "description": "補足（任意）",
  "options": ["..."],
  "required": true,
  "accept": ".csv,.xlsx",
  "hint": "例: '請求書CSVの列名'",
  "validation": {"regex": "^.+$"}
}
```
- マッピング規則例:
  - 未解決 `${vars.foo}` → `type=text` の `foo`
  - ブロック `excel.read_data` に必要な `path/sheet/range` 欠落 → `type=file|text` の複合要件
  - `ai.process_llm.output_schema` 未指定 → スキーマ選択テンプレ（enum）


### 9. バリデーション方針
- 既存バリデータの規則を厳守。検証エラー時は自動成功にフォールバックしない。エラー内容を UI に提示する。
- 主な検証ルール（実装準拠）:
  - ノード ID の一意性（重複不可）
  - ブロック存在/入出力キーの妥当性（spec にないキーはエラー）
  - `when.expr` の構文チェック（安全なサブセット）
  - 参照解決（`${node.alias}` 依存の DAG 辺構築、未解決/循環の検知）
  - 型伝播の整合（出力エイリアス→入力の型互換、未知型は緩和）
  - UI 整合（`ui.layout` と `graph` の対応）
  - ドライラン前提の健全性（`topological_sort` 成功）

### 10. 出力
- 生成 Plan は `id`, `version`, `vars`, `policy`, `ui.layout`, `graph` を含む。
- 保存は `designs/<plan_id>_<yyyymmddHHMM>.yaml`。

---

## UI 仕様（Designタブ）

### 画面構成
- 入力: 指示テキスト、ドキュメントアップロード
- テンプレート選択: マルチセレクト＋タグ/検索
- 候補ブロック一覧（Top-K）: id/入出力キー/説明。
- 不足項目表示: 未解決の `${vars.*}`、必須 UI、不整合のサマリー。
- チャット: `requirements` に従い対話収集、進捗と確定値のプレビュー。
- アクション: 「自動生成」「検証/ドライラン」「登録」

### 操作シーケンス（標準）
1) 入力・テンプレ選択 → 2) 自動生成 → 3) 検証/ドライラン → 4) 登録

### 追加 UI 挙動（現行/拡張）
- 候補ブロック表示: Top-K 候補の `id/inputs/outputs/description` を一覧。選択固定で LLM 制約を強化可能。
- チャット: `Requirement[]` を逐次解決し、確定値は `vars` プレビューに反映。

---

## インタフェース定義（関数/モデル）

### 生成API（実装＋拡張案）
- `generate_plan(instruction, documents_text, registry, options, selected_templates=None, apply_mode="compose|hint|llm-only") -> GeneratedPlan`
  - `instruction: str`: 必須
  - `documents_text: list[str] | None`: 抽出済みテキスト
  - `registry: BlockRegistry`: ブロックカタログ
  - `options: DesignEngineOptions | None`
  - `selected_templates: list[str] | None`: `TemplateSpec.id` の配列
  - `apply_mode`:
    - `hint`: テンプレを Few-shot/制約として投入（現行推奨）
    - `llm-only`: テンプレ未使用（現行実装）

### オプション
- `DesignEngineOptions`
  - `suggest_when: bool`
  - `suggest_foreach: bool`
  - `foreach_var_name: str`
  - 将来: `topk_per_category: int`, `max_docs_chars: int`

### テンプレートモデル（提案）
- `TemplateSpec`（Pydantic）
  - `id: str`
  - `title: str`
  - `description: str | None`
  - `tags: list[str]`
  - `imports: dict[str, {type: str, description?: str}]`
  - `exports: dict[str, {type: str, description?: str}]`
  - `vars_defaults: dict[str, any] | None`
  - `ui_suggestions: { layout?: list[str] } | None`
  - `graph_snippet: list[NodeLike]`（Plan の `graph` と同形）

### 要件ビルダー
- `build_requirements(plan_or_errors) -> list[Requirement]`
  - `Requirement`: `{ id, type, label?, description?, options?, required=true, accept?, hint?, validation? }`
  - 入力型の決定規則・`enum→options` 変換・ヒント付与を実装。

### 返却モデル
- `GeneratedPlan`: `{ plan: Plan, reasoning: str }`
  - `reasoning`: 生成過程メモ（"fallback"/"structured" など）

### 環境変数
- `OPENAI_API_KEY | AZURE_OPENAI_API_KEY`: 必須（なければ生成不可）。`.env` での設定を推奨（アプリ起動時に環境変数へ読み込み）。
- `KEIRI_AGENT_LLM_FALLBACK`: `1|true|yes` で LLM 失敗時にフォールバック Plan を返す

---

## 自己修復仕様
- 反復回数: 例 `max_attempts=2`（将来拡張可）。
- 差し戻しプロンプト: エラー概要、該当ブロック spec 抜粋、テンプレ契約の該当部、前回出力との差分。
- 成功条件: 検証エラーが 0。失敗時は UI にエラーを提示し、修正提案（不足項目→チャット起動、テンプレ追加の推奨）を表示。

---

## ログ/監査・メトリクス
- 生成イベントを JSONL で `logs/keiri_agent.log` とラン別ファイルへ記録（将来: `design_engine.generate` 専用タグ）。
- 主要メトリクス: 生成試行回数、検証エラー件数、自己修復反復回数、ドライラン所要時間、採用ブロック分布。

---

## CLI/ヘッドレス連携（将来）
- 例（PowerShell）:
```powershell
python .\headless\cli_runner.py --generate-plan --instruction "請求書重複検知のPlanを作成" --docs .\docs\rules.md,.\specs\invoices.xlsx --out designs\generated\invoice_dupes_$(Get-Date -Format yyyyMMddHHmm).yaml
```
- オプション: `--templates a,b --apply-mode hint|compose|llm-only --fallback 0|1`

---

## 詰めておくべきポイント（要合意事項）
- Top-K Retrieval の初期実装レベル（BM25 のみか、埋め込み併用か）と K 値
　　→ Openai/azureopenaiのembeddingモデルで埋め込みを生成し、コサイン類似度とする。K値はパラメータで保持。
- テンプレートの配置場所/命名規則（`designs/templates/<category>/<id>.yaml` など）
　　→ 配置場所、命名ははそこでOK
- `Requirement.type` の最小セットと UI マッピング（特に `file|table|enum`）
- `when/foreach/while` の表現統一（`docs/architecture.md` とモデルの突合）
- 自己修復の初期リリース段階（反復 0 回 vs 2 回）
- 生成ポリシー既定値（`on_error`, `retries`, `timeout` 等）
- LLM モデル選定/温度/トークン上限（`core/plan/llm_factory.py` の既定と整合）

---

## 実装タスク（段階導入）
1) 現行の `generate_plan()` に Top-K Retrievalを追加し、LLM への提示を限定化。
2) `TemplateSpec` の定義/ローダ/バリデータを追加し、`apply_mode=hint` をまず実装。
3) `build_requirements()` を実装し、Designタブに Designチャットを統合。
4) 自己修復（`max_attempts=2`）を実装し、UI に差分提示を追加。
5) メトリクス記録と UI 表示（エラー率/所要時間）。
6) CLI 対応（ヘッドレス生成）。
