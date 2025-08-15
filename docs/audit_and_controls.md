# 監査・内部監査・内部統制のための拡張設計

本書は、監査法人/内部監査/内部統制のプロフェッショナルが Keiri Agent を展開する際の設計要点をまとめる。COSO/COBIT、J-SOX を意識しつつ、Plan/BlockSpec/実行証跡を軸に「設計–実行–証跡」の一体管理を実現する。

## 設計原則（Assurance-first）

- 設計の構造化: Plan（DSL）と BlockSpec（I/O契約）を一次成果物とし、レビュー対象にする。
- 検証の厳格化: バリデーションと Dry-run を通らないPlanは保存・実行不可。
- 証跡の完全性: 実行ログ・入出力スナップショット・参照解決を JSONL/Manifest で保持。
- 例外の可視化: 例外・上書き・手作業介入はUIで承認し、証跡に残す。

## コア拡張

### 1) Policy-as-Code
- `designs/policies/*.yaml` に組織/部門/規制ポリシーを宣言（階層・適用範囲・例外を含む）。
- `core/policy/engine.py` による評価・適用とコンプライアンススコア算出。
- ブロック: `policy.validate`（検証）、`policy.deploy`（配布）、`policy.audit`（適用状況監査）をPlan/DAG内で活用。
- Runner/Validatorに拘束。違反時の動作は strict/advisory/audit_only を選択可能。
- 例外は UI で申請→承認し、Evidence Vault に証跡として記録。

### 2) Control Blocks
- 代表例:
  - `control.approval`: 多段承認、期限、代行、理由、監査証跡
  - `control.sod_check`: 職務分掌チェック（操作者≠承認者）
  - `control.sampling`: 監査サンプリング（属性/統計/リスクベース）
  - `control.reconciliation`（計画）: 突合/差分抽出/例外キュー/閾値
- すべての統制ブロックは Evidence Vault と連携し、入力/出力/履歴を型安全に証跡化（JSON Schema/Pydantic）。
- これらは会計以外の業務にも汎用適用可能（契約レビュー、在庫管理、ITGC等）。

### 3) Evidence Vault と Chain-of-Custody
- 証跡（金額表、明細、CSV、PDF、スクレイピング結果等）の暗号化保管（Fernet/AES-256）と鍵管理。
- ハッシュ検証と改ざん検知、監査証跡（Audit Trail JSONL）へのHMAC署名。
- Vault索引・タグ・関連証跡リンク、データ系譜（Lineage）とRun Manifestの維持。
- 保存期間/リーガルホールド/開示履歴の管理。

### 4) Attestation（アテステーション）
- `runs/<plan>/<ts>/manifest.json` に Plan/Spec/環境/モデル/温度/依存ハッシュ/入出力サマリを束ね、署名。
- 監査証跡エントリのHMAC署名とマニフェスト整合性検証APIにより非否認性を担保。
- 第三者検証とリプレイのための最小情報を同梱（乱数シード、定数、サンプルID等）。

### 5) Reviewer Workspace
- 監査人向けワークスペース（ダッシュボード/監査レビュー/証跡管理/ポリシー確認/レポート生成）。
- 差分（Plan/Run/出力/設定）、証跡ナビ（参照追跡）、指摘とフォローアップ、部分再実行（同一Seed/環境）。
- Evidence Vault/Policy-as-Code と統合し、調書エクスポート（PDF/Excel/JSONL）を提供。

## 統制フレームワークへの対応

- COSO/COBIT/J-SOX:
  - 統制設計: Planに統制点（ブロック）を明示。
  - 統制実施: Runnerログで実行主体・時刻・結果・例外承認を記録。
  - 統制評価: Reviewer Workspaceで差分・逸脱・再実行を確認。
  - 規制マッピング: Policy-as-Codeで規制条文とルールをマッピングし、準拠性を可視化。

## 品質保証のための標準

- テスト:
  - Validatorの網羅テスト（when/foreach/while/subflow/policy）。
  - ブロックのDry-runサンプル必須。欠落時は明確な失敗を返す。
  - Evidence Vault の保存/取得/整合性（ハッシュ/署名）テスト。
  - Policy Engine/`policy.*` ブロックの統合テスト（違反検知/例外承認/停止動作）。
- 文書:
  - BlockSpec: I/O・バリデーション・サンプル・依存の完全記述。
  - Plan: 目的、前提、制約、証跡要件、ポリシー参照の明記。

## データ保護

- 秘匿フィールドのマスキング/非保持設定。
- Evidence Vaultの暗号化とアクセス統制、保持期間・リーガルホールド。
- モデルへの投入前の最小化（prompt hygiene）と出力サニタイズ。

## 導入ガイド（概要）

1. 現行業務をPlan DSLにモデリング（固有処理は汎用ブロック＋パラメータで表現）。
2. 統制ポリシーをPolicy-as-Code化（`designs/policies`）し、`policy.validate` で検証。例外は承認＋証跡必須。
3. Dry-runでI/O健全性を確認、欠落サンプルを補完。
4. 本番RunをEvidence-first（Evidence Vault有効化、署名・保持期間設定）で実施し、Reviewer Workspaceでレビュー。
5. 改善サイクル（差分レビュー→再実行→承認→署名）を回す。


