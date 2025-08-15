# Policy-as-Code 詳細設計

## 概要

Policy-as-Codeは、組織の内部統制ポリシー、コンプライアンス要件、監査基準をコードとして定義・管理し、Keiri Agentの実行時に自動適用する機能です。既存のPlan DSL構造を拡張し、ポリシーの宣言的定義と動的実行を実現します。

## 設計原則

### 1. 宣言的ポリシー定義
- YAML形式による人間可読なポリシー記述
- バージョン管理とライフサイクル管理
- 階層的ポリシー構造（組織→部門→プロジェクト）

### 2. 実行時ポリシー適用
- Plan実行時の自動ポリシー検証
- ブロック実行前後のポリシーチェック
- 違反時の自動停止・警告・記録

### 3. 既存アーキテクチャとの統合
- 既存のPlan DSL構造の拡張
- `designs/policies/`ディレクトリでのポリシー管理
- BlockContextを通じたポリシー情報の伝播

### 4. 監査・コンプライアンス対応
- ポリシー適用履歴の完全記録
- 規制要件への自動マッピング
- 例外承認プロセスの組み込み

## アーキテクチャ設計

### 1. ポリシー定義構造

#### 基本ポリシーフォーマット
```yaml
# designs/policies/organizational_policy.yaml
apiVersion: policy/v1
kind: OrganizationalPolicy
metadata:
  name: "corporate_internal_control_policy"
  version: "2025.1.0"
  effective_date: "2025-01-01"
  expiry_date: "2025-12-31"
  owner: "internal_audit_department"
  description: "企業内部統制ポリシー"

spec:
  scope:
    applies_to:
      - plan_types: ["audit", "reconciliation", "approval"]
      - departments: ["finance", "accounting", "procurement"]
      - risk_levels: ["medium", "high", "critical"]
    
  policies:
    # 承認統制ポリシー
    approval_control:
      name: "多段承認要件"
      description: "金額に応じた承認レベルの強制"
      rules:
        - rule_id: "approval_001"
          condition: "amount >= 1000000"
          requirement:
            min_approvers: 2
            required_roles: ["manager", "director"]
            max_approval_time_hours: 24
          enforcement: "mandatory"
          violation_action: "block"
        
        - rule_id: "approval_002"
          condition: "amount >= 10000000"
          requirement:
            min_approvers: 3
            required_roles: ["director", "cfo", "ceo"]
            max_approval_time_hours: 48
            board_notification: true
          enforcement: "mandatory"
          violation_action: "block"
    
    # 職務分掌ポリシー
    segregation_of_duties:
      name: "職務分掌要件"
      description: "利益相反の防止"
      rules:
        - rule_id: "sod_001"
          condition: "transaction_type == 'payment'"
          requirement:
            different_persons: ["initiator", "approver", "processor"]
            incompatible_roles:
              - ["payment_initiator", "payment_approver"]
              - ["vendor_manager", "payment_processor"]
          enforcement: "mandatory"
          violation_action: "block"
    
    # データ品質ポリシー
    data_quality:
      name: "データ品質要件"
      description: "データの完全性と正確性の確保"
      rules:
        - rule_id: "dq_001"
          condition: "data_type == 'financial'"
          requirement:
            completeness_threshold: 0.95
            accuracy_threshold: 0.99
            timeliness_max_delay_hours: 24
          enforcement: "advisory"
          violation_action: "warn"
    
    # 証跡管理ポリシー
    evidence_management:
      name: "証跡管理要件"
      description: "監査証跡の保存と管理"
      rules:
        - rule_id: "evidence_001"
          condition: "always"
          requirement:
            retention_period_days: 2555  # 7年
            encryption_required: true
            integrity_verification: true
            access_logging: true
          enforcement: "mandatory"
          violation_action: "block"

  exceptions:
    approval_process:
      - exception_id: "emergency_payment"
        description: "緊急支払い時の承認簡素化"
        conditions:
          - "emergency_flag == true"
          - "amount < 5000000"
        modified_requirements:
          min_approvers: 1
          required_roles: ["emergency_approver"]
          post_approval_review: true
        approval_required: true
        approver_roles: ["cfo", "ceo"]

  compliance_mapping:
    regulations:
      - name: "SOX法"
        sections: ["302", "404"]
        mapped_rules: ["approval_001", "approval_002", "sod_001"]
      - name: "会社法"
        sections: ["362条", "432条"]
        mapped_rules: ["approval_002", "evidence_001"]
      - name: "金融商品取引法"
        sections: ["24条の4の4"]
        mapped_rules: ["evidence_001", "dq_001"]
```

#### 部門別ポリシー
```yaml
# designs/policies/finance_department_policy.yaml
apiVersion: policy/v1
kind: DepartmentPolicy
metadata:
  name: "finance_department_policy"
  version: "2025.1.0"
  parent_policy: "corporate_internal_control_policy"
  department: "finance"

spec:
  inherits_from: "corporate_internal_control_policy"
  
  overrides:
    approval_control:
      rules:
        - rule_id: "approval_001"
          condition: "amount >= 500000"  # より厳格な閾値
          requirement:
            min_approvers: 2
            required_roles: ["finance_manager", "finance_director"]
  
  additional_policies:
    month_end_close:
      name: "月次決算統制"
      description: "月次決算プロセスの統制"
      rules:
        - rule_id: "close_001"
          condition: "process_type == 'month_end_close'"
          requirement:
            cutoff_verification: true
            reconciliation_completion: true
            variance_analysis_threshold: 0.01
          enforcement: "mandatory"
          violation_action: "block"
```

### 2. ポリシーエンジン設計

#### PolicyEngine基底クラス
```python
# core/policy/engine.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path
import yaml
import json
from pydantic import BaseModel, Field
from enum import Enum

class EnforcementLevel(str, Enum):
    MANDATORY = "mandatory"
    ADVISORY = "advisory"
    INFORMATIONAL = "informational"

class ViolationAction(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    LOG = "log"
    ESCALATE = "escalate"

class PolicyRule(BaseModel):
    rule_id: str
    condition: str
    requirement: Dict[str, Any]
    enforcement: EnforcementLevel
    violation_action: ViolationAction
    description: Optional[str] = None

class PolicySection(BaseModel):
    name: str
    description: str
    rules: List[PolicyRule]

class PolicyException(BaseModel):
    exception_id: str
    description: str
    conditions: List[str]
    modified_requirements: Dict[str, Any]
    approval_required: bool = True
    approver_roles: List[str] = []

class PolicyMetadata(BaseModel):
    name: str
    version: str
    effective_date: datetime
    expiry_date: Optional[datetime] = None
    owner: str
    description: str

class PolicyDefinition(BaseModel):
    api_version: str = Field(alias='apiVersion')
    kind: str
    metadata: PolicyMetadata
    spec: Dict[str, Any]

class PolicyViolation(BaseModel):
    violation_id: str
    rule_id: str
    policy_name: str
    severity: str
    description: str
    context: Dict[str, Any]
    timestamp: datetime
    action_taken: ViolationAction

class PolicyEngine:
    """ポリシーエンジン"""
    
    def __init__(self, policy_directory: str):
        self.policy_directory = Path(policy_directory)
        self.loaded_policies: Dict[str, PolicyDefinition] = {}
        self.policy_cache: Dict[str, Any] = {}
        self._load_policies()
    
    def _load_policies(self):
        """ポリシーファイルの読み込み"""
        if not self.policy_directory.exists():
            return
        
        for policy_file in self.policy_directory.glob('**/*.yaml'):
            try:
                with open(policy_file, 'r', encoding='utf-8') as f:
                    policy_data = yaml.safe_load(f)
                
                policy = PolicyDefinition(**policy_data)
                self.loaded_policies[policy.metadata.name] = policy
                
            except Exception as e:
                print(f"ポリシー読み込みエラー {policy_file}: {e}")
    
    def evaluate_policies(self, context: Dict[str, Any], 
                         applicable_policies: Optional[List[str]] = None) -> List[PolicyViolation]:
        """ポリシー評価の実行"""
        violations = []
        
        # 適用可能なポリシーの決定
        if applicable_policies is None:
            applicable_policies = self._determine_applicable_policies(context)
        
        for policy_name in applicable_policies:
            if policy_name in self.loaded_policies:
                policy = self.loaded_policies[policy_name]
                policy_violations = self._evaluate_single_policy(policy, context)
                violations.extend(policy_violations)
        
        return violations
    
    def _determine_applicable_policies(self, context: Dict[str, Any]) -> List[str]:
        """適用可能なポリシーの決定"""
        applicable = []
        
        for policy_name, policy in self.loaded_policies.items():
            if self._is_policy_applicable(policy, context):
                applicable.append(policy_name)
        
        return applicable
    
    def _is_policy_applicable(self, policy: PolicyDefinition, context: Dict[str, Any]) -> bool:
        """ポリシー適用可能性の判定"""
        scope = policy.spec.get('scope', {})
        applies_to = scope.get('applies_to', {})
        
        # 日付範囲チェック
        now = datetime.now()
        if now < policy.metadata.effective_date:
            return False
        if policy.metadata.expiry_date and now > policy.metadata.expiry_date:
            return False
        
        # プランタイプチェック
        plan_types = applies_to.get('plan_types', [])
        if plan_types and context.get('plan_type') not in plan_types:
            return False
        
        # 部門チェック
        departments = applies_to.get('departments', [])
        if departments and context.get('department') not in departments:
            return False
        
        # リスクレベルチェック
        risk_levels = applies_to.get('risk_levels', [])
        if risk_levels and context.get('risk_level') not in risk_levels:
            return False
        
        return True
    
    def _evaluate_single_policy(self, policy: PolicyDefinition, 
                               context: Dict[str, Any]) -> List[PolicyViolation]:
        """単一ポリシーの評価"""
        violations = []
        
        policies_spec = policy.spec.get('policies', {})
        
        for section_name, section_data in policies_spec.items():
            section = PolicySection(**section_data)
            
            for rule in section.rules:
                violation = self._evaluate_rule(rule, policy.metadata.name, context)
                if violation:
                    violations.append(violation)
        
        return violations
    
    def _evaluate_rule(self, rule: PolicyRule, policy_name: str, 
                      context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """個別ルールの評価"""
        try:
            # 条件式の評価
            if not self._evaluate_condition(rule.condition, context):
                return None  # 条件に該当しない
            
            # 要件チェック
            requirement_met = self._check_requirement(rule.requirement, context)
            
            if not requirement_met:
                return PolicyViolation(
                    violation_id=f"violation_{rule.rule_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    rule_id=rule.rule_id,
                    policy_name=policy_name,
                    severity=rule.enforcement.value,
                    description=f"ポリシー違反: {rule.description or rule.rule_id}",
                    context=context,
                    timestamp=datetime.now(),
                    action_taken=rule.violation_action
                )
            
            return None
            
        except Exception as e:
            # 評価エラーも違反として扱う
            return PolicyViolation(
                violation_id=f"error_{rule.rule_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                rule_id=rule.rule_id,
                policy_name=policy_name,
                severity="high",
                description=f"ポリシー評価エラー: {str(e)}",
                context=context,
                timestamp=datetime.now(),
                action_taken=ViolationAction.WARN
            )
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """条件式の評価"""
        if condition == "always":
            return True
        
        # 簡単な条件式評価（実際にはより高度なパーサーが必要）
        try:
            # 安全な評価のため、許可された変数のみを使用
            safe_context = {k: v for k, v in context.items() 
                          if isinstance(v, (str, int, float, bool))}
            
            # 基本的な比較演算子をサポート
            condition = condition.replace('==', ' == ').replace('>=', ' >= ').replace('<=', ' <= ')
            
            # eval使用（本番環境では専用パーサーを推奨）
            return eval(condition, {"__builtins__": {}}, safe_context)
            
        except Exception:
            return False
    
    def _check_requirement(self, requirement: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """要件チェック"""
        for req_key, req_value in requirement.items():
            if req_key == "min_approvers":
                current_approvers = context.get('approver_count', 0)
                if current_approvers < req_value:
                    return False
            
            elif req_key == "required_roles":
                current_roles = set(context.get('approver_roles', []))
                required_roles = set(req_value)
                if not required_roles.issubset(current_roles):
                    return False
            
            elif req_key == "different_persons":
                persons = [context.get(role) for role in req_value]
                if len(set(persons)) != len(persons):
                    return False
            
            elif req_key == "completeness_threshold":
                current_completeness = context.get('data_completeness', 0)
                if current_completeness < req_value:
                    return False
            
            # 他の要件タイプも同様に実装
        
        return True
```


### 3. ポリシー統合ブロック

#### policy.validate ブロック
```yaml
# block_specs/processing/policy/validate.yaml
id: policy.validate
version: 1.0.0
entrypoint: blocks/processing/policy/validate.py:PolicyValidateBlock
description: ポリシー違反の検証と報告

inputs:
  validation_context:
    type: object
    description: 検証コンテキスト
    properties:
      plan_type:
        type: string
        description: プランタイプ
      department:
        type: string
        description: 部門
      risk_level:
        type: string
        enum: [low, medium, high, critical]
        description: リスクレベル
      transaction_data:
        type: object
        description: 取引データ
      user_context:
        type: object
        description: ユーザーコンテキスト
    required: [plan_type]

  applicable_policies:
    type: array
    items:
      type: string
    description: 適用ポリシー名（指定時）

  enforcement_mode:
    type: string
    enum: [strict, advisory, audit_only]
    default: strict
    description: 実行モード

output_schema:
  type: object
  properties:
    validation_result:
      type: string
      enum: [compliant, violation, warning]
      description: 検証結果
    violations:
      type: array
      description: 違反事項
      items:
        type: object
        properties:
          violation_id:
            type: string
          rule_id:
            type: string
          policy_name:
            type: string
          severity:
            type: string
          description:
            type: string
          action_taken:
            type: string
    compliance_score:
      type: number
      minimum: 0
      maximum: 100
      description: コンプライアンススコア
    recommendations:
      type: array
      description: 推奨事項
      items:
        type: object
        properties:
          recommendation_id:
            type: string
          priority:
            type: string
            enum: [low, medium, high, critical]
          description:
            type: string
          remediation_steps:
            type: array
            items:
              type: string
    policy_evidence:
      type: array
      description: ポリシー適用証跡
      items:
        type: string
  required: [validation_result, violations, compliance_score, policy_evidence]
```

#### PolicyValidateBlock実装
```python
# core/blocks/processing/policy/validate.py
from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime
import uuid
import json
import os

from core.blocks.base import ProcessingBlock, BlockContext
from core.policy.engine import PolicyEngine, PolicyViolation
from core.errors import BlockExecutionError

class PolicyValidateBlock(ProcessingBlock):
    """ポリシー検証ブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """ポリシー検証の実行"""
        try:
            # ポリシーエンジンの初期化
            policy_directory = os.path.join(os.path.dirname(context.workspace or '.'), 'designs/policies')
            policy_engine = PolicyEngine(policy_directory)
            
            # 検証コンテキストの準備
            validation_context = inputs['validation_context']
            applicable_policies = inputs.get('applicable_policies')
            enforcement_mode = inputs.get('enforcement_mode', 'strict')
            
            # ポリシー評価の実行
            violations = policy_engine.evaluate_policies(validation_context, applicable_policies)
            
            # 結果の分析
            validation_result = self._determine_validation_result(violations, enforcement_mode)
            compliance_score = self._calculate_compliance_score(violations)
            recommendations = self._generate_recommendations(violations)
            
            # 証跡の生成
            policy_evidence = self._generate_policy_evidence(
                validation_context, violations, context
            )
            
            # 違反時のアクション実行
            if violations and enforcement_mode == 'strict':
                self._execute_violation_actions(violations)
            
            return {
                'validation_result': validation_result,
                'violations': [violation.dict() for violation in violations],
                'compliance_score': compliance_score,
                'recommendations': recommendations,
                'policy_evidence': policy_evidence
            }
            
        except Exception as e:
            raise BlockExecutionError(f"ポリシー検証でエラーが発生しました: {str(e)}")
    
    def _determine_validation_result(self, violations: List[PolicyViolation], 
                                   enforcement_mode: str) -> str:
        """検証結果の判定"""
        if not violations:
            return 'compliant'
        
        critical_violations = [v for v in violations if v.severity in ['mandatory', 'high']]
        
        if critical_violations and enforcement_mode == 'strict':
            return 'violation'
        elif violations:
            return 'warning'
        else:
            return 'compliant'
    
    def _calculate_compliance_score(self, violations: List[PolicyViolation]) -> float:
        """コンプライアンススコア計算"""
        if not violations:
            return 100.0
        
        severity_weights = {
            'mandatory': 25,
            'advisory': 10,
            'informational': 5
        }
        
        total_deduction = sum(severity_weights.get(v.severity, 15) for v in violations)
        score = max(0, 100 - total_deduction)
        
        return score
    
    def _generate_recommendations(self, violations: List[PolicyViolation]) -> List[Dict[str, Any]]:
        """推奨事項の生成"""
        recommendations = []
        
        for violation in violations:
            recommendation = {
                'recommendation_id': f"rec_{violation.rule_id}_{uuid.uuid4().hex[:8]}",
                'priority': self._map_severity_to_priority(violation.severity),
                'description': f"ポリシー違反の修正: {violation.description}",
                'remediation_steps': self._generate_remediation_steps(violation)
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _map_severity_to_priority(self, severity: str) -> str:
        """重要度から優先度へのマッピング"""
        mapping = {
            'mandatory': 'critical',
            'advisory': 'medium',
            'informational': 'low'
        }
        return mapping.get(severity, 'medium')
    
    def _generate_remediation_steps(self, violation: PolicyViolation) -> List[str]:
        """修正手順の生成"""
        steps = []
        
        if 'approval' in violation.rule_id:
            steps.extend([
                "承認者の追加または変更を実施してください",
                "承認プロセスの見直しを行ってください",
                "承認権限マトリックスを確認してください"
            ])
        elif 'sod' in violation.rule_id:
            steps.extend([
                "職務分掌の見直しを実施してください",
                "担当者の変更を検討してください",
                "利益相反の解消を図ってください"
            ])
        else:
            steps.append("ポリシー要件を満たすよう修正してください")
        
        return steps
    
    def _generate_policy_evidence(self, context: Dict[str, Any], 
                                violations: List[PolicyViolation],
                                block_context: BlockContext) -> List[str]:
        """ポリシー適用証跡の生成"""
        evidence_files = []
        
        if block_context.workspace:
            # ポリシー検証結果ファイル
            evidence_data = {
                'validation_timestamp': datetime.now().isoformat(),
                'context': context,
                'violations': [v.dict() for v in violations],
                'policies_evaluated': list(set(v.policy_name for v in violations))
            }
            
            evidence_file = os.path.join(
                block_context.workspace, 
                f"policy_validation_{block_context.run_id}.json"
            )
            
            with open(evidence_file, 'w', encoding='utf-8') as f:
                json.dump(evidence_data, f, ensure_ascii=False, indent=2, default=str)
            
            evidence_files.append(evidence_file)
        
        return evidence_files
    
    def _execute_violation_actions(self, violations: List[PolicyViolation]):
        """違反時アクションの実行"""
        for violation in violations:
            if violation.action_taken == 'block':
                raise BlockExecutionError(
                    f"ポリシー違反により処理を停止: {violation.description}"
                )
            elif violation.action_taken == 'warn':
                print(f"警告: {violation.description}")
            # 他のアクションも実装
```

### 4. Plan DSL拡張

#### ポリシー統合Plan例
```yaml
# designs/policy_integrated_audit.yaml
apiVersion: v1
id: policy_integrated_audit
description: ポリシー統合監査プラン
version: 1.0.0

vars:
  department: "finance"
  risk_level: "high"
  audit_type: "internal_control"

# ポリシー設定の追加
policy:
  on_error: stop
  retries: 1
  policy_enforcement:
    mode: "strict"  # strict, advisory, audit_only
    applicable_policies:
      - "corporate_internal_control_policy"
      - "finance_department_policy"
    pre_execution_validation: true
    post_execution_validation: true
    continuous_monitoring: true

ui:
  layout:
    - ui_policy_setup
    - ui_audit_execution
    - ui_compliance_review

graph:
  # 1. ポリシー設定確認
  - id: ui_policy_setup
    description: ポリシー設定の確認
    block: ui.interactive_input
    in:
      mode: confirm
      message: |
        以下のポリシーが適用されます：
        - 企業内部統制ポリシー v2025.1.0
        - 財務部門ポリシー v2025.1.0
        
        実行モード: 厳格（違反時停止）
        
        監査を開始しますか？
      display_data:
        - label: "部門"
          value: "${department}"
        - label: "リスクレベル"
          value: "${risk_level}"
        - label: "監査タイプ"
          value: "${audit_type}"

  # 2. 事前ポリシー検証
  - id: pre_execution_policy_check
    description: 実行前ポリシー検証
    block: policy.validate
    in:
      validation_context:
        plan_type: "${audit_type}"
        department: "${department}"
        risk_level: "${risk_level}"
        execution_phase: "pre_execution"
      enforcement_mode: "strict"
    out:
      pre_validation_result: validation_result
      pre_violations: violations

  # 3. 監査データ収集
  - id: collect_audit_data
    description: 監査データの収集
    block: excel.read_data
    in:
      source: ${ui_policy_setup.collected_data}
      path: audit_data
    out:
      audit_data: data
    when:
      condition: ${pre_execution_policy_check.pre_validation_result} == "compliant"

  # 4. データ品質ポリシー検証
  - id: data_quality_policy_check
    description: データ品質ポリシー検証
    block: policy.validate
    in:
      validation_context:
        plan_type: "${audit_type}"
        department: "${department}"
        risk_level: "${risk_level}"
        data_completeness: ${collect_audit_data.audit_data.completeness}
        data_accuracy: ${collect_audit_data.audit_data.accuracy}
        data_type: "financial"
      enforcement_mode: "advisory"
    out:
      data_quality_result: validation_result
      data_quality_violations: violations

  # 5. 承認統制テスト
  - id: approval_control_test
    description: 承認統制テスト
    block: control.approval
    in:
      approval_request:
        request_id: "test_approval_001"
        requester: "test_user"
        amount: 5000000
        description: "ポリシー準拠テスト"
      approval_policy:
        levels:
          - level: 1
            min_amount: 0
            max_amount: 10000000
            required_approvers: 2
            approver_roles: ["manager", "director"]
      current_approvals:
        - approver: "manager_001"
          status: "approved"
          timestamp: "2025-01-15T10:00:00"
    out:
      approval_test_result: approval_status

  # 6. 承認統制ポリシー検証
  - id: approval_policy_check
    description: 承認統制ポリシー検証
    block: policy.validate
    in:
      validation_context:
        plan_type: "${audit_type}"
        department: "${department}"
        risk_level: "${risk_level}"
        amount: 5000000
        approver_count: 1
        approver_roles: ["manager"]
        transaction_type: "payment"
      enforcement_mode: "strict"
    out:
      approval_policy_result: validation_result
      approval_violations: violations

  # 7. 職務分掌テスト
  - id: sod_control_test
    description: 職務分掌テスト
    block: control.sod_check
    in:
      transaction_data:
        transaction_id: "test_sod_001"
        transaction_type: "payment"
        amount: 5000000
        initiator: "user_001"
        approver: "user_001"  # 意図的な違反
        processor: "user_002"
      sod_matrix:
        user_roles:
          user_001: ["payment_initiator", "payment_approver"]
          user_002: ["payment_processor"]
        incompatible_roles:
          - role1: "payment_initiator"
            role2: "payment_approver"
            reason: "利益相反防止"
    out:
      sod_test_result: sod_status

  # 8. 職務分掌ポリシー検証
  - id: sod_policy_check
    description: 職務分掌ポリシー検証
    block: policy.validate
    in:
      validation_context:
        plan_type: "${audit_type}"
        department: "${department}"
        risk_level: "${risk_level}"
        transaction_type: "payment"
        initiator: "user_001"
        approver: "user_001"
        processor: "user_002"
      enforcement_mode: "strict"
    out:
      sod_policy_result: validation_result
      sod_violations: violations

  # 9. 統合コンプライアンス評価
  - id: integrated_compliance_assessment
    description: 統合コンプライアンス評価
    block: ai.process_llm
    in:
      evidence_data:
        pre_validation: ${pre_execution_policy_check}
        data_quality: ${data_quality_policy_check}
        approval_test: ${approval_control_test}
        approval_policy: ${approval_policy_check}
        sod_test: ${sod_control_test}
        sod_policy: ${sod_policy_check}
      instruction: |
        以下のポリシー検証結果を分析し、統合コンプライアンス評価を実施してください：
        
        1. 各ポリシー領域の遵守状況
        2. 違反事項の重要度分析
        3. リスク評価と影響度
        4. 改善提案と優先順位
        5. 総合コンプライアンススコア
        
        組織のリスク管理と内部統制の観点から評価してください。
      system_prompt: |
        あなたは内部統制とコンプライアンスの専門家です。
        ポリシー違反の分析において以下を重視してください：
        - 規制要件への影響
        - 業務リスクの評価
        - 実現可能な改善策
        - 継続的改善の観点
      output_schema:
        type: object
        properties:
          overall_compliance_score:
            type: number
            minimum: 0
            maximum: 100
          policy_area_scores:
            type: object
            properties:
              approval_control:
                type: number
              segregation_of_duties:
                type: number
              data_quality:
                type: number
          critical_findings:
            type: array
            items:
              type: object
              properties:
                finding_id:
                  type: string
                severity:
                  type: string
                description:
                  type: string
                impact:
                  type: string
                recommendation:
                  type: string
          improvement_roadmap:
            type: array
            items:
              type: object
              properties:
                priority:
                  type: string
                  enum: [immediate, short_term, medium_term, long_term]
                action:
                  type: string
                expected_impact:
                  type: string
    out:
      compliance_assessment: output_schema

  # 10. コンプライアンスレビューUI
  - id: ui_compliance_review
    description: コンプライアンス結果のレビュー
    block: ui.interactive_input
    in:
      mode: review
      display_data:
        - label: "総合コンプライアンススコア"
          value: ${integrated_compliance_assessment.compliance_assessment.overall_compliance_score}
        - label: "重要な発見事項"
          value: ${integrated_compliance_assessment.compliance_assessment.critical_findings.length}
        - label: "承認統制スコア"
          value: ${integrated_compliance_assessment.compliance_assessment.policy_area_scores.approval_control}
        - label: "職務分掌スコア"
          value: ${integrated_compliance_assessment.compliance_assessment.policy_area_scores.segregation_of_duties}
      message: "コンプライアンス評価結果を確認し、承認してください。"
    out:
      compliance_approved: approved

  # 11. 最終ポリシー検証
  - id: post_execution_policy_check
    description: 実行後ポリシー検証
    block: policy.validate
    in:
      validation_context:
        plan_type: "${audit_type}"
        department: "${department}"
        risk_level: "${risk_level}"
        execution_phase: "post_execution"
        compliance_score: ${integrated_compliance_assessment.compliance_assessment.overall_compliance_score}
        critical_findings_count: ${integrated_compliance_assessment.compliance_assessment.critical_findings.length}
      enforcement_mode: "audit_only"
    when:
      condition: ${ui_compliance_review.compliance_approved}
    out:
      final_validation_result: validation_result
      final_violations: violations
```


### 5. ポリシー管理機能

#### policy.deploy ブロック
```yaml
# block_specs/processing/policy/deploy.yaml
id: policy.deploy
version: 1.0.0
entrypoint: blocks/processing/policy/deploy.py:PolicyDeployBlock
description: ポリシーの配布と有効化

inputs:
  policy_definition:
    type: object
    description: ポリシー定義
    properties:
      policy_file_path:
        type: string
        description: ポリシーファイルパス
      deployment_scope:
        type: object
        properties:
          departments:
            type: array
            items:
              type: string
          environments:
            type: array
            items:
              type: string
              enum: [development, staging, production]
          effective_date:
            type: string
            format: date-time
      approval_required:
        type: boolean
        default: true
    required: [policy_file_path, deployment_scope]

  deployment_options:
    type: object
    description: 配布オプション
    properties:
      validation_mode:
        type: string
        enum: [strict, permissive]
        default: strict
      rollback_enabled:
        type: boolean
        default: true
      notification_recipients:
        type: array
        items:
          type: string

output_schema:
  type: object
  properties:
    deployment_id:
      type: string
      description: 配布ID
    deployment_status:
      type: string
      enum: [pending, deployed, failed, rolled_back]
    affected_systems:
      type: array
      items:
        type: string
    validation_results:
      type: object
      properties:
        syntax_valid:
          type: boolean
        semantic_valid:
          type: boolean
        conflicts_detected:
          type: array
          items:
            type: string
    deployment_evidence:
      type: array
      items:
        type: string
  required: [deployment_id, deployment_status, affected_systems, validation_results]
```

#### policy.audit ブロック
```yaml
# block_specs/processing/policy/audit.yaml
id: policy.audit
version: 1.0.0
entrypoint: blocks/processing/policy/audit.py:PolicyAuditBlock
description: ポリシー適用状況の監査

inputs:
  audit_scope:
    type: object
    description: 監査範囲
    properties:
      time_period:
        type: object
        properties:
          start_date:
            type: string
            format: date-time
          end_date:
            type: string
            format: date-time
      departments:
        type: array
        items:
          type: string
      policy_names:
        type: array
        items:
          type: string
      violation_severity:
        type: array
        items:
          type: string
          enum: [low, medium, high, critical]

  audit_options:
    type: object
    description: 監査オプション
    properties:
      include_compliant:
        type: boolean
        default: false
      detailed_analysis:
        type: boolean
        default: true
      trend_analysis:
        type: boolean
        default: true

output_schema:
  type: object
  properties:
    audit_summary:
      type: object
      properties:
        total_evaluations:
          type: integer
        total_violations:
          type: integer
        compliance_rate:
          type: number
        trend_direction:
          type: string
          enum: [improving, stable, declining]
    violation_breakdown:
      type: object
      properties:
        by_severity:
          type: object
          additionalProperties:
            type: integer
        by_policy:
          type: object
          additionalProperties:
            type: integer
        by_department:
          type: object
          additionalProperties:
            type: integer
    recommendations:
      type: array
      items:
        type: object
        properties:
          recommendation_type:
            type: string
            enum: [policy_update, training, process_improvement, system_enhancement]
          priority:
            type: string
          description:
            type: string
          estimated_impact:
            type: string
    audit_evidence:
      type: array
      items:
        type: string
  required: [audit_summary, violation_breakdown, recommendations, audit_evidence]
```

### 6. ポリシーライフサイクル管理

#### ポリシーバージョン管理
```yaml
# designs/policies/policy_lifecycle.yaml
apiVersion: policy/v1
kind: PolicyLifecycle
metadata:
  name: "policy_lifecycle_management"
  version: "1.0.0"

spec:
  versioning:
    scheme: "semantic"  # semantic, date-based, sequential
    auto_increment: true
    
  approval_workflow:
    stages:
      - stage: "draft"
        approvers: ["policy_author"]
        actions: ["edit", "submit_for_review"]
      
      - stage: "review"
        approvers: ["department_head", "compliance_officer"]
        actions: ["approve", "reject", "request_changes"]
        required_approvals: 2
        
      - stage: "approved"
        approvers: ["ciso", "cfo"]
        actions: ["deploy", "schedule_deployment"]
        required_approvals: 1
        
      - stage: "deployed"
        approvers: ["system_admin"]
        actions: ["monitor", "rollback"]
        
      - stage: "deprecated"
        approvers: ["compliance_officer"]
        actions: ["archive"]

  deployment_rules:
    environments:
      development:
        auto_deploy: true
        approval_required: false
      staging:
        auto_deploy: false
        approval_required: true
        approvers: ["qa_lead"]
      production:
        auto_deploy: false
        approval_required: true
        approvers: ["ciso", "cfo"]
        
  monitoring:
    compliance_tracking: true
    violation_alerting: true
    performance_metrics: true
    
  retention:
    active_policy_retention_years: 7
    deprecated_policy_retention_years: 10
    audit_log_retention_years: 7
```

### 7. 実装ディレクトリ構造

```
keiri_agent_v0/
├── designs/
│   └── policies/
│       ├── organizational/
│       │   ├── corporate_internal_control_policy.yaml
│       │   ├── data_governance_policy.yaml
│       │   └── security_policy.yaml
│       ├── departmental/
│       │   ├── finance_department_policy.yaml
│       │   ├── hr_department_policy.yaml
│       │   └── it_department_policy.yaml
│       ├── regulatory/
│       │   ├── sox_compliance_policy.yaml
│       │   ├── gdpr_compliance_policy.yaml
│       │   └── local_regulations_policy.yaml
│       └── lifecycle/
│           ├── policy_lifecycle.yaml
│           └── approval_workflows.yaml
├── core/
│   ├── policy/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── validator.py
│   │   ├── deployer.py
│   │   └── auditor.py
│   └── blocks/
│       └── processing/
│           └── policy/
│               ├── __init__.py
│               ├── validate.py
│               ├── deploy.py
│               └── audit.py
├── block_specs/
│   └── processing/
│       └── policy/
│           ├── validate.yaml
│           ├── deploy.yaml
│           └── audit.yaml
└── templates/
    ├── policy_templates/
    │   ├── approval_control_template.yaml
    │   ├── sod_template.yaml
    │   └── data_quality_template.yaml
    └── reports/
        ├── policy_compliance_report.xlsx
        └── policy_audit_report.xlsx
```

### 8. 統合テストシナリオ

#### シナリオ1: ポリシー違反検知
```yaml
# tests/policy_scenarios/violation_detection.yaml
test_scenario: "policy_violation_detection"
description: "ポリシー違反の検知と対応"

setup:
  policies:
    - "corporate_internal_control_policy"
  test_data:
    transaction:
      amount: 15000000  # 高額取引
      approvers: ["manager_001"]  # 不十分な承認
      initiator: "user_001"
      approver: "user_001"  # 同一人物

expected_violations:
  - rule_id: "approval_002"
    severity: "mandatory"
    action: "block"
  - rule_id: "sod_001"
    severity: "mandatory"
    action: "block"

expected_outcome:
  validation_result: "violation"
  execution_blocked: true
```

#### シナリオ2: ポリシー例外処理
```yaml
# tests/policy_scenarios/exception_handling.yaml
test_scenario: "policy_exception_handling"
description: "緊急時ポリシー例外の処理"

setup:
  policies:
    - "corporate_internal_control_policy"
  test_data:
    transaction:
      amount: 3000000
      emergency_flag: true
      approvers: ["emergency_approver_001"]

expected_outcome:
  validation_result: "compliant"
  exception_applied: "emergency_payment"
  post_approval_review_required: true
```

### 9. 期待効果

#### コンプライアンス強化
- **自動ポリシー適用**: 100%の一貫性確保
- **リアルタイム違反検知**: 即座の対応
- **規制要件マッピング**: 自動コンプライアンス確認

#### 運用効率化
- **ポリシー管理の自動化**: 手動作業を80%削減
- **違反対応の迅速化**: 検知から対応まで90%短縮
- **監査準備の効率化**: 証跡収集を自動化

#### リスク管理向上
- **予防的統制**: 事前のリスク回避
- **継続的監視**: 24/7のポリシー監視
- **トレンド分析**: データドリブンな改善

