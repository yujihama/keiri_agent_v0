# Runner 改善計画（保守性・拡張性・ユーザビリティ）

## 目的
- 実装の重複/責務集中を解消し、テスト容易性と将来拡張性を高める
- ログ/状態管理の標準化により、観測性と運用性を向上する
- UIのフロー体験を改善（意図しないクリアを防ぐ）

## 優先度（P0 が最優先）
- P0（直近リリース）
  - 標準イベントAPI（EventFactory/型）導入とイベントスキーマの固定化
  - State公開APIの整備（`get_state/save_state/find_latest_pending_ui`）でPrivate参照を排除
  - 再試行/タイムアウト実行の共通化（RetryExecutor）で重複コード削減
  - エラーログ拡充（`error_code/recoverable/error_details/traceback(上限)`）と`finish_summary`追加
- P1（次期）
  - スケジューラ戦略のクラス化（Loop/Subflow/UI/Processing で責務分離）
  - 依存未解決の再評価フローの一元化（レベル内/グローバルの重複解消）
  - コンカレンシー制御の柔軟化（カテゴリ別max/タグ別制限）
  - DAG成功状態の永続化（UIのクリアボタン以外ではクリアしない設計の強化）
- P2（将来）
  - DAG構築の前処理/キャッシュ化（loader側ユーティリティへ寄せる）
  - Hook/Pluginポイント拡充（typedコールバック: `on_before_node` 等）
  - run_id/ファイル命名の衝突回避強化（ミリ秒/UUID suffix）
  - while式評価の共通化と仕様明文化（`None`扱いなど）
  - シリアライゼーション共通化（b64bytes encode/decode のユーティリティ化）

---

## 詳細設計

### 1) 標準イベントAPI（P0）
- 目的: イベント生成の重複/揺れを解消し、変更影響を局所化
- 方針:
  - `core/plan/events.py` に dataclass（例: `NodeFinish`/`ErrorEvent`/`ScheduleStart`…）
  - Runner は `emit(EventClass(...).asdict(run_id))` で出力
  - イベント共通フィールド（`ts/plan/run_id/schema`）は既存のロガーで補完
- 受入基準:
  - 既存テストがグリーン
  - ログのフィールドがドキュメント通りで安定

### 2) State 公開API（P0）
- 目的: `app.py` から Private (`_state_dir/_state_path`) を排除
- 方針:
  - `PlanRunner` に以下を追加:
    - `get_state(plan_id, run_id) -> dict | None`
    - `save_state(plan_id, run_id, state: dict) -> None`
    - `find_latest_pending_ui(plan_id, prefer_run_id=None) -> (pending, run_id)`
- 受入基準:
  - `app.py` 側の直接参照削除
  - UIの保留検出/再開が動作

### 3) RetryExecutor で実行制御統一（P0）
- 目的: `_exec/_exec_block` の重複/差異を解消し、例外→イベント変換を共通化
- 方針:
  - `RetryExecutor.run(callable, retries, timeout_ms, policy)` を用意
  - 成功/失敗/再試行/継続のイベント出力を一箇所で実施
- 受入基準:
  - ノード成功/失敗時のイベント/挙動が変わらない

### 4) エラーログ/終端サマリの拡充（P0）
- 目的: 可観測性（SLO/SLA/分析）強化
- 方針:
  - `error`: `error_code/recoverable/error_details/traceback(上限文字数)` を標準化
  - `finish_summary`: 総ノード数/成功/スキップ/エラー/総経過ms/総リトライ回数
- 受入基準:
  - 代表E2Eログでサマリが出力される

### 5) スケジューラ戦略のクラス化（P1）
- 目的: ループ/サブフロー/UI/通常処理の責務分離と機能拡張
- 方針:
  - `INodeStrategy`（`can_handle(node)`/`run(node, ctx, ...)`）を定義
  - 現状ロジックを各Strategyへ分割
- 受入基準:
  - 機能等価でテストグリーン

### 6) 依存未解決ノードの再評価統一（P1）
- 目的: レベル内fallback/グローバルパスの重複削減
- 方針:
  - `resolve_deferred_nodes_once()` を汎用化し両パスで使用
- 受入基準:
  - ログ/挙動の非退行

### 7) コンカレンシー制御の柔軟化（P1）
- 目的: 大規模Planでのスループット安定
- 方針:
  - `policy.concurrency = { default_max_workers, ui_max, processing_max, loop_max }` 等
- 受入基準:
  - 既存Planでの実行/ログに変化なし（デフォルト）

### 8) DAG成功状態の永続化（P1）
- 目的: UIでクリアボタン押下までフロー図をクリアしない（ユーザビリティ）
- 現状:
  - `app.py` は `st.session_state['flow_success::<plan_id>']` を保持し、クリアボタンでのみ削除
  - セッション再起動/ブラウザ更新で状態が消える
- 方針:
  - `runs/<plan_id>/<run_id>.state.json` へ `ui_outputs` と同様に成功ノード集合を永続化
  - 画面表示時に最も新しい `run_id` の成功集合を読み出して反映
- 受入基準:
  - クリアボタン押下以外でフロー図が初期化されない（セッション跨ぎでも継続）

### 9) その他（P2）
- DAG構築の前処理/キャッシュ化、Hook/Plugin、run_id衝突回避、while評価共通化、b64bytesユーティリティ

---

## ログ仕様（v1）要点
- 自動付与: `ts/plan/run_id/schema("v1")`
- 代表イベント:
  - `start/finish`, `schedule_*`, `node_start/node_finish/node_defer/node_skip`, `ui_wait/ui_submit/ui_reuse`, `error`
  - `debug`（`export_log()`）：ユーザー入力/処理サマリ/出力サマリ
- `debug` 例:
```json
{"type":"debug","tag":"ui.inquire","data":{"event":"chat_user","message":"Q1をお願いします"}}
```

---

## UIのユーザビリティ方針
- フロー図の成功状態は「クリア」押下まで保持
  - 実装: セッション内保持＋（P1で）状態ファイルへ永続化
  - 「クリア」押下時のみ `ui_outputs/pending_ui/flow_success` を削除
- 入力保留UIの再開を優先（自動検出/再開ID記憶）
- Excel成果物のダウンロード/保存は Plan の `out` を優先して自動提示

---

## 実施順序（マイルストーン）
1. P0: イベントAPI/State公開API/RetryExecutor/エラーログ拡充（1〜2PR）
2. P1: 戦略化/再評価統一/コンカレンシー/成功状態永続化（2〜3PR）
3. P2: 構造/Hook/run_id/while/serialize（段階的）

---

## 互換性/移行
- 既存のログ閲覧（`app.py`）はイベントスキーマv1を前提
- Runner APIのPublic化により、`app.py`からのPrivate参照を廃止
- 変更は段階的に導入し、PRごとにテスト充実・ドキュメント更新

---

## 進捗（P0）
- 追加: `core/plan/events.py`（イベントdataclass群）
- 変更: `core/plan/runner.py`
  - `StartEvent/ScheduleLevel*` の使用に置換
  - `finish_summary` イベントを追加
- テスト: 既存テスト一式グリーン（14 passed, 3 skipped）
- 追加（本ステップ）: State公開API（`get_state/save_state/find_latest_pending_ui/clear_state_files`）
- 追加（本ステップ）: フロー図成功状態の永続化（`success_nodes` を state.json に保持）
- 次: RetryExecutor 導入（再試行/タイムアウトの共通実装化）
