# Detail Audit & Controls トレーサビリティ

- P1: Control Blocks 基本3種（approval / sod_check / sampling）: 実装済（基本）
  - Spec: `block_specs/processing/control.*.yaml`
  - 実装: `core/blocks/processing/control/*`
  - Plan断片: docsに反映済
- P2: Evidence Vault 拡張（retrieve / search / audit_report）: 実装済（Spec + 実装 + Plan断片）
  - Spec: `block_specs/processing/evidence.*.yaml`
  - 実装: `core/blocks/processing/evidence/*`
  - Plan断片: 本README/詳細設計に掲載
- P3: Policy-as-Code 最小実装（policy.validate 雛形）: 実装済（Spec + 実装、段階移行注記）
  - Spec: `block_specs/processing/policy.validate.yaml`
  - 実装: `core/blocks/processing/control/policy_validate.py`
  - 文書: `Policy-as-Code 詳細設計.md` に段階移行を追記
- P4: Reviewer Workspace v1（UI統合）: 実装済（新規タブ追加）
  - UI: `ui/tabs/reviewer.py`、`app.py` にタブ登録
  - 導線: 設計どおり（検索→詳細）、Evidenceと連携
- P5: Control Blocks 拡張（reconciliation / validation）: 実装済（Spec + 実装）
  - Spec: `block_specs/processing/control.reconciliation.yaml`, `control.validation.yaml`
  - 実装: `core/blocks/processing/control/reconciliation.py`, `control/validation.py`
