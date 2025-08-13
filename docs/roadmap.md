# Keiri Agent ロードマップ

本ロードマップは「概要（Horizon別）」と「具体（実装粒度）」の二層で記述する。日付は目安であり、価値連続性と安全性（監査可能性）を最優先する。

## 概要（Horizons）

### H0: 安定化と基盤強化（0–1ヶ月）
- 目標: 既存機能の堅牢化、I/O契約・検証・実行の一貫性を高める。
- 主要アウトカム:
  - Plan Validatorの強化（when/foreach/while/サブフローの網羅検証）。
  - Dry-runの厳格化（未定義サンプル＝失敗）。
  - 実行ログ（JSONL）の粒度統一と外部出力（CSV/Parquet）

### H1: Observability & Evidence（1–3ヶ月）
- 目標: Evidence-firstを形にする基礎機能を提供。
- 主要アウトカム:
  - Run Manifest（plan/環境/依存/ハッシュの束ね）と `runs/<plan>/<ts>/manifest.json`
  - 出力ファイル/テーブルのハッシュとメタ（provenance, schema）
  - 証跡ビューア（Streamlitタブ）とエクスポート

### H2: Governance & Policy-as-Code（2–4ヶ月）
- 目標: 組織ポリシーを宣言し、Plan/実行に拘束。
- 主要アウトカム:
  - `configs/policies/*.yaml` と検証器
  - 例外承認フロー（UIブロック）と記録
  - SoD/承認/サンプリング/しきい値の汎用ルール適用

### H3: Assurance Blocks & Reviewer Workspace（3–6ヶ月）
- 目標: 統制ブロック群と監査レビューワークスペースを提供。
- 主要アウトカム:
  - `control.*` ブロック群（approval, sod_check, sampling, reconciliation など）
  - Reviewer Workspace（差分・証跡ナビ・指摘管理・再実行）

### H4: Attestation & Evidence Vault（5–9ヶ月）
- 目標: 実行アテステーションと証跡金庫で非否認性と改ざん検知。
- 主要アウトカム:
  - 署名/検証（鍵管理はプラガブル）
  - Evidence Vault（暗号化保存・リーガルホールド・開示履歴）

### H5: Marketplace & Certification（6–12ヶ月）
- 目標: 検証済みブロック/Planの共有と認証制度。
- 主要アウトカム:
  - 署名付き配布・互換性検証・審査プロセス
  - テンプレ/SDK/ドキュメントの拡充

---

## 具体（実装粒度）

以下は代表的な作業項目。各項は「受け入れ基準（AC）」を伴う。

### 1. Validator/Runner 強化（H0–H1）
- Planバリデーションの拡張
  - when式: 安全サブセット評価、未解決参照の検出、型整合チェック（AC: 無効式の体系テスト）
  - foreach/while/subflow: スキーマ検証と上限（max_iterations等）必須化（AC: 無限ループ不可能）
- Runnerの実行順/待機ロジック
  - 参照未解決ノードの自動延期（現状の遅延判定の一般化）（AC: 依存欠落テストが緑）
  - ノード毎タイムアウト/リトライの一貫適用（AC: policyテストが緑）

### 2. Evidence-first 機能（H1）
- Run Manifest
  - `runs/<plan>/<ts>/manifest.json` に planハッシュ、specハッシュ、環境、モデルID、温度、依存ライブラリハッシュ、入力概要を格納（AC: 再現に必要な最小情報が揃う）
- 出力ハッシングとスキーマ
  - Excel/CSV/JSON出力のハッシュとスキーマスナップショット（AC: 再出力でハッシュ一致）
- 証跡ビューア
  - StreamlitタブでRun一覧→ノード→入出力→参照解決のツリー閲覧（AC: 2クリック以内に任意ノードの証跡に到達）

### 3. Policy-as-Code（H2）
- `configs/policies/*.yaml` 読込と適用
  - 例: サンプリング率、承認必須閾値、利用禁止ブロック、並列度上限（AC: 禁止ポリシー違反のPlanは検証NG）
- 例外承認フロー
  - `ui.interactive_input` に例外申請と承認UI（AC: 承認なしに例外適用不可、証跡化）

### 4. Control Blocks（H3）
- 新規ブロック（spec+実装）
  - `control.approval`: 多段承認、期限、代行、記録
  - `control.sod_check`: 職務分掌チェック（操作者/承認者）
  - `control.sampling`: 統計/属性サンプリング
  - `control.reconciliation`: 突合（マッピング/差分/閾値/例外キュー）
  - AC: 代表的な統制シナリオのE2Eテスト

### 5. Attestation & Vault（H4）
- 署名/検証
  - `core/security/attestation.py`：マニフェスト署名・検証API（AC: 鍵差替え/オフライン検証が可能）
- Evidence Vault
  - 暗号化保存、保持期間、改ざん検知（AC: 保存/取得/開示の完全証跡）

### 6. Reviewer Workspace（H3–H4）
- 機能
  - 差分比較（Plan/Run/出力/設定）
  - 証跡ナビ（参照追跡・来歴）
  - 再実行（同一Seed/環境）と部分再実行（特定ノード）
  - AC: 監査観点のユーザーテストで主要ユースケースが完了

### 7. Marketplace & Certification（H5）
- 署名付き配布
  - ブロック/Planの署名・互換性検証・インストール（AC: 未認証の資産に警告）
- 認証制度
  - 品質基準・スコアカード・自動検証（AC: 発行/失効/再審査フロー）

---

## リスクと緩和

- モデル非決定性: 重要処理でのtemperature制約、検証強化、リプレイ機構。
- 秘匿情報: Evidence Vaultの暗号化、最小限ログ方針、秘匿フィールドマスキング。
- 複雑性増大: Control Blocksのパラメータ化とテンプレ提供、UIの統一。


