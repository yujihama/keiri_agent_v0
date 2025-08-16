# Control Blocks 詳細設計

## 概要

Control Blocksは、監査・内部統制業務に特化したブロック群です。既存のKeiri Agentアーキテクチャを活用し、監査・内部統制の専門的な処理を標準化・自動化します。

## 設計原則

### 1. 既存アーキテクチャとの整合性
- `core/blocks/base.py`の`ProcessingBlock`を継承
- `block_specs/processing/control/`ディレクトリに仕様定義
- `core/blocks/processing/control/`ディレクトリに実装

### 2. 証跡管理の徹底
- すべての統制処理で完全な監査証跡を生成
- `BlockContext.run_id`による実行トレーサビリティ
- `BlockContext.workspace`での証跡ファイル保存

### 3. 型安全性の確保
- Pydantic BaseModelによる厳格な入出力定義
- JSON-Schemaによる実行時バリデーション
- 構造化エラーによる透明な失敗処理

## Control Blocks一覧

### Phase 1: 基本統制ブロック

#### 1. control.approval（承認統制）
- 多段承認フローの実行
- 承認履歴の記録
- 期限管理・エスカレーション

#### 2. control.sod_check（職務分掌チェック）
- 操作者/承認者の分離検証
- 利益相反の検知
- 権限マトリックスの適用

#### 3. control.sampling（サンプリング）
- 統計的サンプリング
- 属性サンプリング
- リスクベースサンプリング

### Phase 2: 高度統制ブロック

#### 4. control.reconciliation（突合・照合）
- 自動マッピング
- 差分分析
- 例外処理

#### 5. control.validation（妥当性検証）
- データ整合性チェック
- ビジネスルール検証
- 閾値監視

#### 6. control.documentation（文書化）
- 統制実施記録の生成
- 証跡の構造化
- レポート作成

### Phase 3: 専門統制ブロック

#### 7. control.risk_assessment（リスク評価）
- リスク識別・評価
- 統制有効性評価
- リスクマトリックス生成

#### 8. control.compliance_check（コンプライアンスチェック）
- 法規制要件の検証
- 内部規程の適用
- 違反検知・報告

#### 9. control.audit_trail（監査証跡）
- 証跡の完全性検証
- タイムスタンプ管理
- デジタル署名


## 1. control.approval（承認統制）詳細設計

### ブロック仕様（YAML）

```yaml
# block_specs/processing/control/approval.yaml
id: control.approval
version: 1.0.0
entrypoint: blocks/processing/control/approval.py:ApprovalBlock
description: 多段承認フローの実行と承認履歴の管理

inputs:
  approval_request:
    type: object
    description: 承認要求データ
    properties:
      request_id:
        type: string
        description: 承認要求ID
      requester:
        type: string
        description: 申請者
      amount:
        type: number
        description: 金額（承認レベル判定用）
      description:
        type: string
        description: 承認要求の説明
      attachments:
        type: array
        description: 添付ファイル
        items:
          type: string
    required: [request_id, requester, amount, description]

  approval_policy:
    type: object
    description: 承認ポリシー設定
    properties:
      levels:
        type: array
        description: 承認レベル定義
        items:
          type: object
          properties:
            level:
              type: integer
              description: 承認レベル
            min_amount:
              type: number
              description: 最小金額
            max_amount:
              type: number
              description: 最大金額
            required_approvers:
              type: integer
              description: 必要承認者数
            approver_roles:
              type: array
              description: 承認者ロール
              items:
                type: string
            timeout_hours:
              type: integer
              description: 承認期限（時間）
      escalation_policy:
        type: object
        description: エスカレーションポリシー
        properties:
          enabled:
            type: boolean
            description: エスカレーション有効化
          escalation_hours:
            type: integer
            description: エスカレーション時間
          escalation_roles:
            type: array
            description: エスカレーション先ロール
            items:
              type: string

  current_approvals:
    type: array
    description: 既存の承認状況
    items:
      type: object
      properties:
        approver:
          type: string
          description: 承認者
        status:
          type: string
          enum: [pending, approved, rejected]
          description: 承認状況
        timestamp:
          type: string
          format: date-time
          description: 承認日時
        comment:
          type: string
          description: 承認コメント

output_schema:
  type: object
  properties:
    approval_status:
      type: string
      enum: [pending, approved, rejected, escalated]
      description: 全体承認状況
    required_approvals:
      type: array
      description: 必要な承認
      items:
        type: object
        properties:
          level:
            type: integer
            description: 承認レベル
          approver_role:
            type: string
            description: 承認者ロール
          status:
            type: string
            enum: [pending, approved, rejected]
            description: 承認状況
          deadline:
            type: string
            format: date-time
            description: 承認期限
    approval_history:
      type: array
      description: 承認履歴
      items:
        type: object
        properties:
          approver:
            type: string
            description: 承認者
          action:
            type: string
            enum: [approved, rejected, escalated]
            description: 承認アクション
          timestamp:
            type: string
            format: date-time
            description: アクション日時
          comment:
            type: string
            description: コメント
    next_actions:
      type: array
      description: 次のアクション
      items:
        type: object
        properties:
          action_type:
            type: string
            enum: [wait_approval, escalate, complete, reject]
            description: アクションタイプ
          target_role:
            type: string
            description: 対象ロール
          deadline:
            type: string
            format: date-time
            description: 実行期限
    evidence_files:
      type: array
      description: 生成された証跡ファイル
      items:
        type: string
        description: ファイルパス
  required: [approval_status, required_approvals, approval_history, next_actions, evidence_files]
```

### 実装クラス設計

```python
# core/blocks/processing/control/approval.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import json
import os

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError

class ApprovalRequest(BaseModel):
    request_id: str
    requester: str
    amount: float
    description: str
    attachments: List[str] = []

class ApprovalLevel(BaseModel):
    level: int
    min_amount: float
    max_amount: float
    required_approvers: int
    approver_roles: List[str]
    timeout_hours: int

class EscalationPolicy(BaseModel):
    enabled: bool = False
    escalation_hours: int = 24
    escalation_roles: List[str] = []

class ApprovalPolicy(BaseModel):
    levels: List[ApprovalLevel]
    escalation_policy: EscalationPolicy

class CurrentApproval(BaseModel):
    approver: str
    status: str  # pending, approved, rejected
    timestamp: datetime
    comment: Optional[str] = None

class ApprovalBlock(ProcessingBlock):
    """承認統制ブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """承認フローの実行"""
        try:
            # 入力データの検証
            approval_request = ApprovalRequest(**inputs['approval_request'])
            approval_policy = ApprovalPolicy(**inputs['approval_policy'])
            current_approvals = [CurrentApproval(**approval) for approval in inputs.get('current_approvals', [])]
            
            # 承認レベルの決定
            required_level = self._determine_approval_level(approval_request.amount, approval_policy.levels)
            
            # 承認状況の評価
            approval_status = self._evaluate_approval_status(required_level, current_approvals, approval_policy)
            
            # 承認履歴の生成
            approval_history = self._generate_approval_history(current_approvals)
            
            # 次のアクションの決定
            next_actions = self._determine_next_actions(approval_status, required_level, current_approvals, approval_policy)
            
            # 証跡ファイルの生成
            evidence_files = self._generate_evidence_files(
                approval_request, approval_policy, current_approvals, 
                approval_status, context
            )
            
            return {
                'approval_status': approval_status,
                'required_approvals': self._format_required_approvals(required_level, current_approvals),
                'approval_history': approval_history,
                'next_actions': next_actions,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"承認統制処理でエラーが発生しました: {str(e)}")
    
    def _determine_approval_level(self, amount: float, levels: List[ApprovalLevel]) -> ApprovalLevel:
        """金額に基づく承認レベルの決定"""
        for level in sorted(levels, key=lambda x: x.min_amount):
            if level.min_amount <= amount <= level.max_amount:
                return level
        
        # 最高レベルを返す
        return max(levels, key=lambda x: x.level)
    
    def _evaluate_approval_status(self, required_level: ApprovalLevel, 
                                current_approvals: List[CurrentApproval],
                                policy: ApprovalPolicy) -> str:
        """承認状況の評価"""
        approved_count = sum(1 for approval in current_approvals if approval.status == 'approved')
        rejected_count = sum(1 for approval in current_approvals if approval.status == 'rejected')
        
        # 拒否がある場合
        if rejected_count > 0:
            return 'rejected'
        
        # 必要承認数に達している場合
        if approved_count >= required_level.required_approvers:
            return 'approved'
        
        # エスカレーション判定
        if policy.escalation_policy.enabled:
            oldest_pending = min(
                (approval.timestamp for approval in current_approvals if approval.status == 'pending'),
                default=datetime.now()
            )
            if datetime.now() - oldest_pending > timedelta(hours=policy.escalation_policy.escalation_hours):
                return 'escalated'
        
        return 'pending'
    
    def _generate_evidence_files(self, request: ApprovalRequest, policy: ApprovalPolicy,
                               approvals: List[CurrentApproval], status: str,
                               context: BlockContext) -> List[str]:
        """証跡ファイルの生成"""
        evidence_files = []
        
        if context.workspace:
            # 承認要求ファイル
            request_file = os.path.join(context.workspace, f"approval_request_{request.request_id}_{context.run_id}.json")
            with open(request_file, 'w', encoding='utf-8') as f:
                json.dump(request.dict(), f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(request_file)
            
            # 承認履歴ファイル
            history_file = os.path.join(context.workspace, f"approval_history_{request.request_id}_{context.run_id}.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([approval.dict() for approval in approvals], f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(history_file)
            
            # 承認ポリシーファイル
            policy_file = os.path.join(context.workspace, f"approval_policy_{request.request_id}_{context.run_id}.json")
            with open(policy_file, 'w', encoding='utf-8') as f:
                json.dump(policy.dict(), f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(policy_file)
        
        return evidence_files
```


## 2. control.sod_check（職務分掌チェック）詳細設計

### ブロック仕様（YAML）

```yaml
# block_specs/processing/control/sod_check.yaml
id: control.sod_check
version: 1.0.0
entrypoint: blocks/processing/control/sod_check.py:SodCheckBlock
description: 職務分掌の検証と利益相反の検知

inputs:
  transaction_data:
    type: object
    description: 取引データ
    properties:
      transaction_id:
        type: string
        description: 取引ID
      transaction_type:
        type: string
        description: 取引種別
      amount:
        type: number
        description: 取引金額
      initiator:
        type: string
        description: 取引開始者
      approver:
        type: string
        description: 承認者
      processor:
        type: string
        description: 処理者
      reviewer:
        type: string
        description: レビューワー
      timestamp:
        type: string
        format: date-time
        description: 取引日時
    required: [transaction_id, transaction_type, initiator]

  sod_matrix:
    type: object
    description: 職務分掌マトリックス
    properties:
      roles:
        type: array
        description: ロール定義
        items:
          type: object
          properties:
            role_id:
              type: string
              description: ロールID
            role_name:
              type: string
              description: ロール名
            permissions:
              type: array
              description: 権限リスト
              items:
                type: string
      incompatible_roles:
        type: array
        description: 非互換ロール組み合わせ
        items:
          type: object
          properties:
            role1:
              type: string
              description: ロール1
            role2:
              type: string
              description: ロール2
            reason:
              type: string
              description: 非互換理由
      user_roles:
        type: object
        description: ユーザーロール割り当て
        additionalProperties:
          type: array
          items:
            type: string

  conflict_rules:
    type: array
    description: 利益相反ルール
    items:
      type: object
      properties:
        rule_id:
          type: string
          description: ルールID
        rule_name:
          type: string
          description: ルール名
        condition:
          type: string
          description: 条件式
        severity:
          type: string
          enum: [low, medium, high, critical]
          description: 重要度
        description:
          type: string
          description: ルール説明

output_schema:
  type: object
  properties:
    sod_status:
      type: string
      enum: [compliant, violation, warning]
      description: 職務分掌状況
    violations:
      type: array
      description: 違反事項
      items:
        type: object
        properties:
          violation_type:
            type: string
            enum: [role_conflict, permission_overlap, same_person_multiple_roles]
            description: 違反タイプ
          severity:
            type: string
            enum: [low, medium, high, critical]
            description: 重要度
          description:
            type: string
            description: 違反内容
          involved_users:
            type: array
            description: 関与ユーザー
            items:
              type: string
          involved_roles:
            type: array
            description: 関与ロール
            items:
              type: string
          recommendation:
            type: string
            description: 推奨対応
    role_analysis:
      type: object
      description: ロール分析結果
      properties:
        initiator_roles:
          type: array
          description: 開始者ロール
          items:
            type: string
        approver_roles:
          type: array
          description: 承認者ロール
          items:
            type: string
        processor_roles:
          type: array
          description: 処理者ロール
          items:
            type: string
        reviewer_roles:
          type: array
          description: レビューワーロール
          items:
            type: string
    compliance_score:
      type: number
      minimum: 0
      maximum: 100
      description: コンプライアンススコア
    evidence_files:
      type: array
      description: 生成された証跡ファイル
      items:
        type: string
        description: ファイルパス
  required: [sod_status, violations, role_analysis, compliance_score, evidence_files]
```

### 実装クラス設計

```python
# core/blocks/processing/control/sod_check.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field
import json
import os

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError

class TransactionData(BaseModel):
    transaction_id: str
    transaction_type: str
    amount: Optional[float] = None
    initiator: str
    approver: Optional[str] = None
    processor: Optional[str] = None
    reviewer: Optional[str] = None
    timestamp: Optional[datetime] = None

class Role(BaseModel):
    role_id: str
    role_name: str
    permissions: List[str]

class IncompatibleRole(BaseModel):
    role1: str
    role2: str
    reason: str

class SodMatrix(BaseModel):
    roles: List[Role]
    incompatible_roles: List[IncompatibleRole]
    user_roles: Dict[str, List[str]]

class ConflictRule(BaseModel):
    rule_id: str
    rule_name: str
    condition: str
    severity: str  # low, medium, high, critical
    description: str

class Violation(BaseModel):
    violation_type: str
    severity: str
    description: str
    involved_users: List[str]
    involved_roles: List[str]
    recommendation: str

class SodCheckBlock(ProcessingBlock):
    """職務分掌チェックブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """職務分掌チェックの実行"""
        try:
            # 入力データの検証
            transaction = TransactionData(**inputs['transaction_data'])
            sod_matrix = SodMatrix(**inputs['sod_matrix'])
            conflict_rules = [ConflictRule(**rule) for rule in inputs.get('conflict_rules', [])]
            
            # ロール分析
            role_analysis = self._analyze_roles(transaction, sod_matrix)
            
            # 違反検知
            violations = self._detect_violations(transaction, sod_matrix, conflict_rules, role_analysis)
            
            # 状況判定
            sod_status = self._determine_sod_status(violations)
            
            # コンプライアンススコア計算
            compliance_score = self._calculate_compliance_score(violations)
            
            # 証跡ファイル生成
            evidence_files = self._generate_evidence_files(
                transaction, sod_matrix, violations, role_analysis, context
            )
            
            return {
                'sod_status': sod_status,
                'violations': [violation.dict() for violation in violations],
                'role_analysis': role_analysis,
                'compliance_score': compliance_score,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"職務分掌チェックでエラーが発生しました: {str(e)}")
    
    def _analyze_roles(self, transaction: TransactionData, sod_matrix: SodMatrix) -> Dict[str, Any]:
        """ロール分析"""
        analysis = {
            'initiator_roles': sod_matrix.user_roles.get(transaction.initiator, []),
            'approver_roles': sod_matrix.user_roles.get(transaction.approver, []) if transaction.approver else [],
            'processor_roles': sod_matrix.user_roles.get(transaction.processor, []) if transaction.processor else [],
            'reviewer_roles': sod_matrix.user_roles.get(transaction.reviewer, []) if transaction.reviewer else []
        }
        return analysis
    
    def _detect_violations(self, transaction: TransactionData, sod_matrix: SodMatrix,
                          conflict_rules: List[ConflictRule], role_analysis: Dict[str, Any]) -> List[Violation]:
        """違反検知"""
        violations = []
        
        # 同一人物による複数ロール実行チェック
        violations.extend(self._check_same_person_multiple_roles(transaction, role_analysis))
        
        # 非互換ロール組み合わせチェック
        violations.extend(self._check_incompatible_roles(transaction, sod_matrix, role_analysis))
        
        # カスタム利益相反ルールチェック
        violations.extend(self._check_conflict_rules(transaction, conflict_rules, role_analysis))
        
        return violations
    
    def _check_same_person_multiple_roles(self, transaction: TransactionData, 
                                        role_analysis: Dict[str, Any]) -> List[Violation]:
        """同一人物による複数ロール実行チェック"""
        violations = []
        users = []
        
        if transaction.initiator:
            users.append(('initiator', transaction.initiator))
        if transaction.approver:
            users.append(('approver', transaction.approver))
        if transaction.processor:
            users.append(('processor', transaction.processor))
        if transaction.reviewer:
            users.append(('reviewer', transaction.reviewer))
        
        # 同一人物チェック
        user_roles = {}
        for role_type, user in users:
            if user in user_roles:
                user_roles[user].append(role_type)
            else:
                user_roles[user] = [role_type]
        
        for user, roles in user_roles.items():
            if len(roles) > 1:
                violations.append(Violation(
                    violation_type='same_person_multiple_roles',
                    severity='high',
                    description=f'同一人物 {user} が複数の役割を実行: {", ".join(roles)}',
                    involved_users=[user],
                    involved_roles=roles,
                    recommendation='異なる担当者による役割分担を実施してください'
                ))
        
        return violations
    
    def _check_incompatible_roles(self, transaction: TransactionData, sod_matrix: SodMatrix,
                                role_analysis: Dict[str, Any]) -> List[Violation]:
        """非互換ロール組み合わせチェック"""
        violations = []
        
        # 全ユーザーのロールを収集
        all_user_roles = []
        for user_type, roles in role_analysis.items():
            for role in roles:
                all_user_roles.append((user_type, role))
        
        # 非互換ロールチェック
        for incompatible in sod_matrix.incompatible_roles:
            role1_found = any(role == incompatible.role1 for _, role in all_user_roles)
            role2_found = any(role == incompatible.role2 for _, role in all_user_roles)
            
            if role1_found and role2_found:
                violations.append(Violation(
                    violation_type='role_conflict',
                    severity='critical',
                    description=f'非互換ロールの組み合わせ: {incompatible.role1} と {incompatible.role2}',
                    involved_users=[],
                    involved_roles=[incompatible.role1, incompatible.role2],
                    recommendation=f'理由: {incompatible.reason}。ロール分離を実施してください'
                ))
        
        return violations
    
    def _determine_sod_status(self, violations: List[Violation]) -> str:
        """職務分掌状況の判定"""
        if not violations:
            return 'compliant'
        
        critical_violations = [v for v in violations if v.severity == 'critical']
        high_violations = [v for v in violations if v.severity == 'high']
        
        if critical_violations or high_violations:
            return 'violation'
        else:
            return 'warning'
    
    def _calculate_compliance_score(self, violations: List[Violation]) -> float:
        """コンプライアンススコア計算"""
        if not violations:
            return 100.0
        
        severity_weights = {
            'low': 5,
            'medium': 15,
            'high': 30,
            'critical': 50
        }
        
        total_deduction = sum(severity_weights.get(v.severity, 0) for v in violations)
        score = max(0, 100 - total_deduction)
        
        return score
```


## 3. control.sampling（サンプリング）詳細設計

### ブロック仕様（YAML）

```yaml
# block_specs/processing/control/sampling.yaml
id: control.sampling
version: 1.0.0
entrypoint: blocks/processing/control/sampling.py:SamplingBlock
description: 統計的・属性・リスクベースサンプリングの実行

inputs:
  population_data:
    type: object
    description: 母集団データ
    properties:
      data_source:
        type: string
        description: データソース
      total_items:
        type: integer
        description: 総アイテム数
      total_value:
        type: number
        description: 総金額
      items:
        type: array
        description: 個別アイテム
        items:
          type: object
          properties:
            item_id:
              type: string
              description: アイテムID
            value:
              type: number
              description: 金額
            risk_score:
              type: number
              description: リスクスコア
            attributes:
              type: object
              description: 属性データ
    required: [data_source, total_items, items]

  sampling_parameters:
    type: object
    description: サンプリングパラメータ
    properties:
      method:
        type: string
        enum: [statistical, attribute, risk_based, systematic, random]
        description: サンプリング手法
      confidence_level:
        type: number
        minimum: 0.8
        maximum: 0.99
        description: 信頼水準
      tolerable_error_rate:
        type: number
        minimum: 0.01
        maximum: 0.2
        description: 許容誤謬率
      expected_error_rate:
        type: number
        minimum: 0
        maximum: 0.5
        description: 予想誤謬率
      sample_size:
        type: integer
        minimum: 1
        description: サンプルサイズ（指定時）
      stratification:
        type: object
        description: 層化設定
        properties:
          enabled:
            type: boolean
            description: 層化有効化
          strata_field:
            type: string
            description: 層化フィールド
          strata_weights:
            type: object
            description: 層別重み
      risk_criteria:
        type: object
        description: リスク基準
        properties:
          high_risk_threshold:
            type: number
            description: 高リスク閾値
          medium_risk_threshold:
            type: number
            description: 中リスク閾値
          high_risk_percentage:
            type: number
            description: 高リスク選択割合
    required: [method]

output_schema:
  type: object
  properties:
    sampling_result:
      type: object
      description: サンプリング結果
      properties:
        method_used:
          type: string
          description: 使用手法
        sample_size:
          type: integer
          description: 実際のサンプルサイズ
        population_size:
          type: integer
          description: 母集団サイズ
        sampling_ratio:
          type: number
          description: サンプリング比率
        confidence_level:
          type: number
          description: 信頼水準
        margin_of_error:
          type: number
          description: 誤差範囲
    selected_items:
      type: array
      description: 選択されたアイテム
      items:
        type: object
        properties:
          item_id:
            type: string
            description: アイテムID
          value:
            type: number
            description: 金額
          risk_score:
            type: number
            description: リスクスコア
          selection_reason:
            type: string
            description: 選択理由
          stratum:
            type: string
            description: 層（層化時）
    sampling_statistics:
      type: object
      description: サンプリング統計
      properties:
        total_sample_value:
          type: number
          description: サンプル総金額
        average_item_value:
          type: number
          description: 平均アイテム金額
        value_coverage_ratio:
          type: number
          description: 金額カバー率
        risk_distribution:
          type: object
          description: リスク分布
          properties:
            high_risk_count:
              type: integer
              description: 高リスクアイテム数
            medium_risk_count:
              type: integer
              description: 中リスクアイテム数
            low_risk_count:
              type: integer
              description: 低リスクアイテム数
    evidence_files:
      type: array
      description: 生成された証跡ファイル
      items:
        type: string
        description: ファイルパス
  required: [sampling_result, selected_items, sampling_statistics, evidence_files]
```

### 実装クラス設計

```python
# core/blocks/processing/control/sampling.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
import random
import math
import json
import os
from datetime import datetime
from pydantic import BaseModel, Field

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError

class PopulationItem(BaseModel):
    item_id: str
    value: float
    risk_score: Optional[float] = 0.0
    attributes: Dict[str, Any] = {}

class PopulationData(BaseModel):
    data_source: str
    total_items: int
    total_value: Optional[float] = None
    items: List[PopulationItem]

class StratificationConfig(BaseModel):
    enabled: bool = False
    strata_field: Optional[str] = None
    strata_weights: Dict[str, float] = {}

class RiskCriteria(BaseModel):
    high_risk_threshold: float = 0.7
    medium_risk_threshold: float = 0.3
    high_risk_percentage: float = 0.8

class SamplingParameters(BaseModel):
    method: str  # statistical, attribute, risk_based, systematic, random
    confidence_level: Optional[float] = 0.95
    tolerable_error_rate: Optional[float] = 0.05
    expected_error_rate: Optional[float] = 0.02
    sample_size: Optional[int] = None
    stratification: StratificationConfig = StratificationConfig()
    risk_criteria: RiskCriteria = RiskCriteria()

class SelectedItem(BaseModel):
    item_id: str
    value: float
    risk_score: float
    selection_reason: str
    stratum: Optional[str] = None

class SamplingBlock(ProcessingBlock):
    """サンプリングブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """サンプリングの実行"""
        try:
            # 入力データの検証
            population = PopulationData(**inputs['population_data'])
            parameters = SamplingParameters(**inputs['sampling_parameters'])
            
            # サンプリング実行
            if parameters.method == 'statistical':
                selected_items, sampling_result = self._statistical_sampling(population, parameters)
            elif parameters.method == 'attribute':
                selected_items, sampling_result = self._attribute_sampling(population, parameters)
            elif parameters.method == 'risk_based':
                selected_items, sampling_result = self._risk_based_sampling(population, parameters)
            elif parameters.method == 'systematic':
                selected_items, sampling_result = self._systematic_sampling(population, parameters)
            elif parameters.method == 'random':
                selected_items, sampling_result = self._random_sampling(population, parameters)
            else:
                raise ValueError(f"未対応のサンプリング手法: {parameters.method}")
            
            # 統計計算
            sampling_statistics = self._calculate_statistics(selected_items, population)
            
            # 証跡ファイル生成
            evidence_files = self._generate_evidence_files(
                population, parameters, selected_items, sampling_result, context
            )
            
            return {
                'sampling_result': sampling_result,
                'selected_items': [item.dict() for item in selected_items],
                'sampling_statistics': sampling_statistics,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"サンプリング処理でエラーが発生しました: {str(e)}")
    
    def _statistical_sampling(self, population: PopulationData, 
                            parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """統計的サンプリング"""
        # サンプルサイズ計算
        if parameters.sample_size:
            sample_size = parameters.sample_size
        else:
            sample_size = self._calculate_statistical_sample_size(
                population.total_items,
                parameters.confidence_level,
                parameters.tolerable_error_rate,
                parameters.expected_error_rate
            )
        
        # ランダムサンプリング実行
        selected_indices = random.sample(range(len(population.items)), min(sample_size, len(population.items)))
        selected_items = []
        
        for idx in selected_indices:
            item = population.items[idx]
            selected_items.append(SelectedItem(
                item_id=item.item_id,
                value=item.value,
                risk_score=item.risk_score,
                selection_reason='統計的ランダムサンプリング'
            ))
        
        sampling_result = {
            'method_used': 'statistical',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level)
        }
        
        return selected_items, sampling_result
    
    def _risk_based_sampling(self, population: PopulationData,
                           parameters: SamplingParameters) -> tuple[List[SelectedItem], Dict[str, Any]]:
        """リスクベースサンプリング"""
        # リスクレベル別分類
        high_risk_items = [item for item in population.items 
                          if item.risk_score >= parameters.risk_criteria.high_risk_threshold]
        medium_risk_items = [item for item in population.items 
                           if parameters.risk_criteria.medium_risk_threshold <= item.risk_score < parameters.risk_criteria.high_risk_threshold]
        low_risk_items = [item for item in population.items 
                         if item.risk_score < parameters.risk_criteria.medium_risk_threshold]
        
        selected_items = []
        
        # 高リスクアイテムの選択
        high_risk_sample_size = int(len(high_risk_items) * parameters.risk_criteria.high_risk_percentage)
        if high_risk_sample_size > 0:
            high_risk_selected = random.sample(high_risk_items, min(high_risk_sample_size, len(high_risk_items)))
            for item in high_risk_selected:
                selected_items.append(SelectedItem(
                    item_id=item.item_id,
                    value=item.value,
                    risk_score=item.risk_score,
                    selection_reason='高リスクアイテム'
                ))
        
        # 残りのサンプルサイズ計算
        remaining_sample_size = (parameters.sample_size or 50) - len(selected_items)
        if remaining_sample_size > 0:
            remaining_items = medium_risk_items + low_risk_items
            if remaining_items:
                additional_selected = random.sample(remaining_items, min(remaining_sample_size, len(remaining_items)))
                for item in additional_selected:
                    risk_level = 'medium' if item.risk_score >= parameters.risk_criteria.medium_risk_threshold else 'low'
                    selected_items.append(SelectedItem(
                        item_id=item.item_id,
                        value=item.value,
                        risk_score=item.risk_score,
                        selection_reason=f'{risk_level}リスクアイテム'
                    ))
        
        sampling_result = {
            'method_used': 'risk_based',
            'sample_size': len(selected_items),
            'population_size': population.total_items,
            'sampling_ratio': len(selected_items) / population.total_items,
            'confidence_level': parameters.confidence_level or 0.95,
            'margin_of_error': self._calculate_margin_of_error(len(selected_items), parameters.confidence_level or 0.95)
        }
        
        return selected_items, sampling_result
    
    def _calculate_statistical_sample_size(self, population_size: int, confidence_level: float,
                                         tolerable_error_rate: float, expected_error_rate: float) -> int:
        """統計的サンプルサイズ計算"""
        # Z値の計算
        z_values = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_values.get(confidence_level, 1.96)
        
        # サンプルサイズ計算（属性サンプリング用）
        numerator = (z ** 2) * expected_error_rate * (1 - expected_error_rate)
        denominator = tolerable_error_rate ** 2
        
        sample_size = math.ceil(numerator / denominator)
        
        # 有限母集団修正
        if population_size < 10000:
            sample_size = math.ceil(sample_size / (1 + (sample_size - 1) / population_size))
        
        return min(sample_size, population_size)
    
    def _calculate_margin_of_error(self, sample_size: int, confidence_level: float) -> float:
        """誤差範囲計算"""
        z_values = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
        z = z_values.get(confidence_level, 1.96)
        
        return z / math.sqrt(sample_size)
    
    def _calculate_statistics(self, selected_items: List[SelectedItem], 
                            population: PopulationData) -> Dict[str, Any]:
        """サンプリング統計計算"""
        total_sample_value = sum(item.value for item in selected_items)
        average_item_value = total_sample_value / len(selected_items) if selected_items else 0
        
        # リスク分布
        high_risk_count = sum(1 for item in selected_items if item.risk_score >= 0.7)
        medium_risk_count = sum(1 for item in selected_items if 0.3 <= item.risk_score < 0.7)
        low_risk_count = sum(1 for item in selected_items if item.risk_score < 0.3)
        
        # 金額カバー率
        population_total_value = population.total_value or sum(item.value for item in population.items)
        value_coverage_ratio = total_sample_value / population_total_value if population_total_value > 0 else 0
        
        return {
            'total_sample_value': total_sample_value,
            'average_item_value': average_item_value,
            'value_coverage_ratio': value_coverage_ratio,
            'risk_distribution': {
                'high_risk_count': high_risk_count,
                'medium_risk_count': medium_risk_count,
                'low_risk_count': low_risk_count
            }
        }
```


## Control Blocks統合設計

### Plan DSL統合例

```yaml
# designs/internal_control_audit.yaml
apiVersion: v1
id: internal_control_audit
description: 内部統制監査の自動化プラン
version: 1.0.0

vars:
  audit_period: "2025年第1四半期"
  auditor: "監査チーム"
  control_framework: "COSO"

policy:
  on_error: stop
  retries: 1
  evidence_retention_days: 2555  # 7年間

ui:
  layout:
    - ui_audit_setup
    - ui_control_execution
    - ui_review_results

graph:
  # 1. 監査セットアップ
  - id: ui_audit_setup
    description: 監査パラメータの設定
    block: ui.interactive_input
    in:
      mode: collect
      requirements:
        - id: transaction_data
          label: 取引データファイル
          type: file
          accept: .xlsx,.csv
          required: true
        - id: approval_policy
          label: 承認ポリシー設定
          type: file
          accept: .json,.yaml
          required: true
        - id: sod_matrix
          label: 職務分掌マトリックス
          type: file
          accept: .json,.yaml
          required: true

  # 2. 取引データ読み込み
  - id: load_transaction_data
    description: 取引データの読み込みと前処理
    block: excel.read_data
    in:
      source: ${ui_audit_setup.collected_data}
      path: transaction_data
    out:
      transactions: data

  # 3. 承認統制チェック
  - id: approval_control_check
    description: 承認統制の検証
    block: control.approval
    in:
      approval_request:
        request_id: ${transactions.transaction_id}
        requester: ${transactions.initiator}
        amount: ${transactions.amount}
        description: ${transactions.description}
      approval_policy: ${ui_audit_setup.collected_data.approval_policy}
      current_approvals: ${transactions.approval_history}
    out:
      approval_results: approval_status
      approval_evidence: evidence_files

  # 4. 職務分掌チェック
  - id: sod_control_check
    description: 職務分掌の検証
    block: control.sod_check
    in:
      transaction_data:
        transaction_id: ${transactions.transaction_id}
        transaction_type: ${transactions.type}
        amount: ${transactions.amount}
        initiator: ${transactions.initiator}
        approver: ${transactions.approver}
        processor: ${transactions.processor}
      sod_matrix: ${ui_audit_setup.collected_data.sod_matrix}
      conflict_rules: []
    out:
      sod_results: sod_status
      sod_evidence: evidence_files

  # 5. リスクベースサンプリング
  - id: risk_sampling
    description: リスクベースサンプリングの実行
    block: control.sampling
    in:
      population_data:
        data_source: "取引データ"
        total_items: ${transactions.count}
        items: ${transactions.items}
      sampling_parameters:
        method: "risk_based"
        confidence_level: 0.95
        sample_size: 50
        risk_criteria:
          high_risk_threshold: 0.7
          high_risk_percentage: 0.8
    out:
      sample_results: selected_items
      sampling_evidence: evidence_files

  # 6. 統制テスト結果の統合
  - id: integrate_control_results
    description: 統制テスト結果の統合
    block: transforms.group_evidence
    in:
      evidence_groups:
        - name: "承認統制"
          evidence: ${approval_control_check.approval_evidence}
          results: ${approval_control_check.approval_results}
        - name: "職務分掌"
          evidence: ${sod_control_check.sod_evidence}
          results: ${sod_control_check.sod_results}
        - name: "サンプリング"
          evidence: ${risk_sampling.sampling_evidence}
          results: ${risk_sampling.sample_results}
    out:
      integrated_evidence: evidence
      summary_results: results

  # 7. 監査レポート生成
  - id: generate_audit_report
    description: 監査レポートの生成
    block: ai.process_llm
    in:
      evidence_data: ${integrate_control_results.integrated_evidence}
      instruction: |
        以下の内部統制テスト結果を分析し、監査レポートを作成してください：
        
        1. 承認統制の有効性評価
        2. 職務分掌の適切性評価
        3. サンプリング結果の分析
        4. 発見事項と推奨事項
        5. 統制環境の総合評価
        
        監査基準に従い、客観的で具体的なレポートを作成してください。
      system_prompt: |
        あなたは経験豊富な内部監査人です。
        内部統制の評価において、以下の観点を重視してください：
        - 統制の設計の適切性
        - 統制の運用の有効性
        - リスクと統制のバランス
        - 改善提案の実現可能性
      output_schema:
        type: object
        properties:
          executive_summary:
            type: string
            description: エグゼクティブサマリー
          control_effectiveness:
            type: object
            properties:
              approval_control:
                type: object
                properties:
                  rating:
                    type: string
                    enum: [effective, partially_effective, ineffective]
                  findings:
                    type: array
                    items:
                      type: string
              sod_control:
                type: object
                properties:
                  rating:
                    type: string
                    enum: [effective, partially_effective, ineffective]
                  findings:
                    type: array
                    items:
                      type: string
          recommendations:
            type: array
            items:
              type: object
              properties:
                priority:
                  type: string
                  enum: [high, medium, low]
                description:
                  type: string
                timeline:
                  type: string
          overall_assessment:
            type: string
            enum: [satisfactory, needs_improvement, unsatisfactory]
    out:
      audit_report: output_schema

  # 8. 結果確認
  - id: ui_review_results
    description: 監査結果の確認
    block: ui.interactive_input
    in:
      mode: confirm
      message: |
        内部統制監査が完了しました。
        
        承認統制: ${approval_control_check.approval_results.approval_status}
        職務分掌: ${sod_control_check.sod_results.sod_status}
        サンプリング: ${risk_sampling.sample_results.length}件選択
        
        監査レポートを確認し、承認しますか？
      display_data:
        - label: "監査レポート"
          value: ${generate_audit_report.audit_report}
        - label: "証跡ファイル"
          value: ${integrate_control_results.integrated_evidence}
    out:
      approval: approved

  # 9. 最終出力
  - id: finalize_audit
    description: 監査結果の最終化
    block: excel.write
    in:
      data:
        audit_summary: ${generate_audit_report.audit_report}
        approval_results: ${approval_control_check.approval_results}
        sod_results: ${sod_control_check.sod_results}
        sampling_results: ${risk_sampling.sample_results}
        evidence_index: ${integrate_control_results.integrated_evidence}
      template: "internal_control_audit_report.xlsx"
      output_path: "audit_results_${audit_period}.xlsx"
    when:
      condition: ${ui_review_results.approval}
```

### 実装ディレクトリ構造

```
keiri_agent_v0/
├── block_specs/
│   └── processing/
│       └── control/
│           ├── approval.yaml
│           ├── sod_check.yaml
│           ├── sampling.yaml
│           ├── reconciliation.yaml
│           ├── validation.yaml
│           ├── documentation.yaml
│           ├── risk_assessment.yaml
│           ├── compliance_check.yaml
│           └── audit_trail.yaml
├── core/
│   └── blocks/
│       └── processing/
│           └── control/
│               ├── __init__.py
│               ├── approval.py
│               ├── sod_check.py
│               ├── sampling.py
│               ├── reconciliation.py
│               ├── validation.py
│               ├── documentation.py
│               ├── risk_assessment.py
│               ├── compliance_check.py
│               └── audit_trail.py
├── designs/
│   ├── internal_control_audit.yaml
│   ├── approval_workflow.yaml
│   ├── sod_compliance_check.yaml
│   └── risk_based_testing.yaml
└── templates/
    ├── internal_control_audit_report.xlsx
    ├── approval_matrix.xlsx
    └── sod_matrix.xlsx
```

### 統合テストシナリオ

#### シナリオ1: 承認統制テスト
1. 取引データのアップロード
2. 承認ポリシーの適用
3. 承認フローの検証
4. 違反事項の検出
5. 証跡の生成

#### シナリオ2: 職務分掌テスト
1. ユーザーロール情報の読み込み
2. 取引における役割分担の分析
3. 利益相反の検知
4. コンプライアンススコアの算出
5. 改善提案の生成

#### シナリオ3: 統合監査プロセス
1. 複数統制の同時テスト
2. リスクベースサンプリング
3. 結果の統合分析
4. 監査レポートの自動生成
5. 証跡の一元管理

### 期待効果

#### 効率化効果
- 監査工数削減: 50-70%
- 統制テスト時間短縮: 60-80%
- 証跡作成自動化: 90%以上

#### 品質向上効果
- 人的エラー削減: 80%以上
- 統制テストの標準化: 100%
- 証跡の完全性確保: 100%

#### コンプライアンス強化
- 監査証跡の完全性
- 統制実施の透明性
- リスクベース監査の実現

## P1 基本ブロック I/O（最新）

### control.approval
- inputs: `route_definition`, `decisions`, `context`
- outputs: `approved`, `route_log`, `violations`

### control.sod_check
- inputs: `assignments`, `sod_matrix`, `scope`
- outputs: `violations`, `summary`

### control.sampling
- inputs: `population`, `method`, `size`, `attribute_rules`, `risk_weights`, `seed`
- outputs: `samples`, `excluded`, `summary`

## P5 拡張ブロック（雛形）

### control.reconciliation
- inputs: `left`, `right`, `keys`, `options(compare_fields)`
- outputs: `matched`, `diffs`, `left_only`, `right_only`, `summary`

### control.validation
- inputs: `dataset`, `rules`, `options`
- outputs: `violations`, `summary`

