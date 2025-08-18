# Detail Audit & Controls 整理インデックス

本フォルダ内の詳細設計を、上位設計（`docs/roadmap.md`, `docs/audit_and_controls.md`）と現行実装に突き合わせて整理する。目的は以下の3点。

- 方向性の一貫性確保（Evidence-first, Policy-as-Code, Control Blocks, Reviewer Workspace）
- 実装状況の可視化（実装済/部分実装/計画）
- 命名・配置の不一致是正方針の提示

---

## トレーサビリティ（上位→詳細設計→現行コード）

| テーマ | 上位設計（Roadmap） | 詳細設計ドキュメント | 実装ステータス | 現行コード/Spec 例 |
|---|---|---|---|---|
| Control Blocks 基本3種（approval/sod/sampling） | H3: Assurance Blocks | `Control Blocks 詳細設計.md` | 実装済（基本） | `block_specs/processing/control.approval.yaml`, `control.sod_check.yaml`, `control.sampling.yaml` / `core/blocks/processing/control/*.py` |
| Control Blocks 拡張（reconciliation/validation 等） | H3: 拡張ブロック計画 | 同上 | 計画（P5） | （未実装） |
| Evidence Vault v1（保存/改ざん検知/索引/証跡） | H1, H4 | `Evidence Vault 詳細設計.md` | 部分実装 | `block_specs/processing/evidence.vault.store.yaml`, `core/blocks/processing/evidence/vault_store.py`, `core/blocks/processing/security/attestation.py`／`core/evidence/` は未実装 |
| Policy-as-Code（validate/deploy/audit） | H2 | `Policy-as-Code 詳細設計.md` | 部分実装（P3） | 既存は `control.policy_enforce` 系で代替（`block_specs/processing/control.policy_enforce.yaml`, `core/blocks/processing/control/policy_enforce.py`）／`core/policy/` は雛形のみ |
| Reviewer Workspace v1 | H3, H6 | `Reviewer Workspace 詳細設計.md` | 設計のみ（P4） | 既存UIは `ui/*` 構成（`ui/tabs/*.py` 等）。`core/ui/*` は未採用 |
| Attestation & Run Manifest | H1, H4 | 上位設計に記載 | 部分実装 | `block_specs/processing/security.attestation.sign_manifest.yaml`, `core/blocks/processing/security/attestation.py`／`runs/<plan>/<ts>/manifest.json` 生成は未確認 |
| Validator/Runner 強化 | H0 | 上位設計に記載 | 進行中 | `core/plan/validator.py`, `tests/test_validator_*.py`, `tests/test_runner_*` |

| Evidence Vault 拡張（retrieve/search/audit_report） | H1, H4 | `Evidence Vault 詳細設計.md` | 計画（P2） | Spec/実装は未作成（本READMEの実装計画参照） |
| Policy-as-Code validate（検証ブロック） | H2 | `Policy-as-Code 詳細設計.md` | 計画（P3） | Spec/実装は未作成（本READMEの実装計画参照） |

---

## 整合性ギャップと是正方針

- 命名の不一致（修正推奨）
  - 詳細設計の `evidence.store`/`evidence.search`/`evidence.audit_report` → 現行は `evidence.vault.store` のみ実装。詳細設計上は「将来の正式ID（policy.*系と同様）」として残しつつ、現行コード参照は `evidence.vault.store` に統一する注記を追記。
  - `policy.*` ブロック（validate/deploy/audit） → 現行は `control.policy_enforce`。段階移行（Phase1: control側、Phase2: policy.* へ分離）を明記。
  - UI パス表記：詳細設計の `core/ui/*` → 既存実装は `ui/*`。ドキュメントは `ui/*` に合わせ、`core/ui/*` は将来のモジュール再配置案として括弧書きに変更。

- 実装レベルの差分（明示化）
  - Evidence Vault コア（`core/evidence/vault.py`）は未実装だが、`vault_store` ブロック＋`attestation` は存在。詳細設計先頭に「実装ステータス: 部分実装（保存/署名）・未実装（索引/UI統合/検索）」を追記。
  - Reviewer Workspace は現行UIの `ui/tabs/*` を拡張する方針に合わせて、詳細設計内のクラス配置例を `ui/` ベースに差し替え。
  - Run Manifest（`runs/<plan>/<ts>/manifest.json`）は未実装。上位との重要ギャップとして各詳細設計の「証跡連携」節に TODO ではなく「次対応」の明示を追加。

---

## ドキュメント編集ガイド（各詳細設計に追記する共通枠）

- ステータス: 実装済 / 部分実装 / 計画
- 対応 Roadmap 範囲: H0/H1/H2/H3/H4 のいずれか
- 現行コード参照: 関連する `block_specs/*`, `core/*`, `ui/*`, `tests/*`
- 非互換・差分: 命名/配置/仕様の差分と暫定対応
- 次対応（2週間内）/ 今四半期の目標 / リスク

---

## 今後90日の実装優先度（上位整合）

1. Run Manifest 生成（H1）
   - 生成箇所: `core/plan/runner.py`（Plan/Spec/環境/モデル/依存ハッシュ/入出力概要）
   - テスト: `tests/` に再現性・ハッシュ一致の体系テスト
2. Evidence Vault v1 仕上げ（H1→H4布石）
   - `core/evidence/vault.py` 実装、`evidence.search`, `evidence.audit_report` Spec/Block 追加
3. Policy-as-Code 最小実装（H2）
   - `core/policy/engine.py` と `policy.validate` を先行（`control.policy_enforce` から移行ポイントを定義）
4. Control Blocks 拡張（H3）
   - `control.reconciliation`/`control.validation` のSpec雛形→実装
5. Reviewer Workspace v1（H3/H6）
   - 既存 `ui/tabs/*` を拡張（Evidence索引・Run/ノード→証跡ツリーの2クリック到達）
6. 署名/検証の運用化（H4）
   - 監査証跡JSONLのHMAC署名と検証APIの統合テスト

---

## 変更提案（ドキュメント反映の最小差分）

- `Evidence Vault 詳細設計.md`
  - 冒頭に「実装ステータス: 部分実装（vault_store/attestation）。未実装（vault/search/audit_report）」を追記
  - サンプルBlock IDを現行 `evidence.vault.store` に合わせて注記
- `Policy-as-Code 詳細設計.md`
  - Phase分離（現行: `control.policy_enforce`、次段: `policy.*`）の移行方針を追記
- `Reviewer Workspace 詳細設計.md`
  - モジュール配置を `ui/*` 前提に修正、既存 `ui/tabs/*` との統合ポイントを明記
- `Control Blocks 詳細設計.md`
  - 拡張ブロックを「計画」ラベルで明確化し、優先度を上表の90日計画に合わせる

---

## 参照

- 上位: `docs/roadmap.md`, `docs/audit_and_controls.md`
- 実装: `block_specs/processing/*`, `core/blocks/processing/*`, `core/plan/*`, `ui/*`, `tests/*`
