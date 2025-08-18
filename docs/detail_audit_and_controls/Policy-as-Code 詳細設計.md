# Policy-as-Code 詳細設計

## 概要（機能面に限定）

Policy-as-Code は、ポリシー（ルール）を宣言的に定義し、Plan 実行時に検証・適用するための機能です。本書では機能面に絞り、現行のブロック/命名と整合する内容に簡潔化します。

### メタ情報
- ステータス: 部分実装（現行は `control.policy_enforce` を使用）
- 対応 Roadmap: H2
- 現行/将来: 現行 `control.policy_enforce` → 将来 `policy.validate` へ段階移行

## 設計原則

### 1. 宣言的ポリシー定義
- YAML形式による人間可読なポリシー記述
- バージョン管理とライフサイクル管理
- 階層的ポリシー構造（組織→部門→プロジェクト）

### 2. 実行時ポリシー適用（最小機能）
- Plan 実行時に検証ブロックでポリシー違反を検出
- 違反時の停止/警告の動作モード（strict/advisory）

### 3. 既存アーキテクチャとの整合
- 現行は `control.policy_enforce` を利用（最小ポリシー適用）
- 将来は `policy.validate` へ段階移行（ID/配置は `block_specs/processing/policy/*.yaml`）

## アーキテクチャ設計

### 1. ポリシー定義構造（例）
```yaml
# designs/policies/organizational_policy.yaml
apiVersion: policy/v1
kind: OrganizationalPolicy
metadata:
  name: "corporate_internal_control_policy"
  version: "2025.1.0"
...
```

### 2. ポリシーエンジン設計（要点）

<!-- 実装コード断片は本書から省略（非機能・詳細実装は別文書） -->

## ブロック（段階移行の方針）

- 現行ブロック: `control.policy_enforce`
  - ID: `control.policy_enforce`
  - 役割: items と宣言ルールを受け取り、違反一覧/可否を返す
  - Spec: `block_specs/processing/control.policy_enforce.yaml`

- 将来ブロック（計画）: `policy.validate`
  - ID: `policy.validate`
  - 役割: `validation_context` を受け、違反/スコア/推奨を返す（厳格化）
  - 配置: `block_specs/processing/policy/validate.yaml`

## Plan での利用要点（現行）

```yaml
- id: enforce_po_policy
  block: control.policy_enforce
  in:
    items: ${po_data}
    policy: ${policies.po_rules}
  out:
    violations: violations
    passed: passed
```

<!-- deploy/audit/lifecycle/周辺機能は別途検討のため本書では省略 -->

