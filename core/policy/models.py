"""ポリシーモデル

Policy-as-Codeで使用するポリシー定義、ルール、違反情報などのデータモデルを定義します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum
import uuid


class PolicyType(str, Enum):
    """ポリシータイプ"""
    COMPLIANCE = "compliance"
    BUSINESS_RULE = "business_rule"
    SECURITY = "security"
    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    AUDIT = "audit"


class RuleSeverity(str, Enum):
    """ルール重要度"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class PolicyStatus(str, Enum):
    """ポリシーステータス"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    SUSPENDED = "suspended"


class ViolationType(str, Enum):
    """違反タイプ"""
    RULE_VIOLATION = "rule_violation"
    THRESHOLD_EXCEEDED = "threshold_exceeded"
    MISSING_APPROVAL = "missing_approval"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    DATA_QUALITY = "data_quality"
    SEGREGATION_DUTY = "segregation_duty"


class PolicyRule(BaseModel):
    """ポリシールール"""
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    rule_type: str  # expression, threshold, approval_required, etc.
    expression: str  # ルール式（JSON Logic、Python式等）
    parameters: Dict[str, Any] = {}
    severity: RuleSeverity = RuleSeverity.MEDIUM
    enabled: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('expression')
    def validate_expression(cls, v):
        """ルール式の妥当性検証"""
        if not v or not v.strip():
            raise ValueError("ルール式は必須です")
        return v.strip()


class Policy(BaseModel):
    """ポリシー定義"""
    policy_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    policy_type: PolicyType
    version: str = "1.0.0"
    rules: List[PolicyRule] = []
    metadata: Dict[str, Any] = {}
    tags: List[str] = []
    department: Optional[str] = None
    owner: Optional[str] = None
    status: PolicyStatus = PolicyStatus.DRAFT
    effective_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    @validator('rules')
    def validate_rules(cls, v):
        """ルール一覧の妥当性検証"""
        if not v:
            raise ValueError("ポリシーには最低1つのルールが必要です")
        return v
    
    def get_active_rules(self) -> List[PolicyRule]:
        """有効なルール一覧を取得"""
        return [rule for rule in self.rules if rule.enabled]
    
    def is_effective(self) -> bool:
        """ポリシーが有効期間内かチェック"""
        now = datetime.now()
        if self.effective_date and now < self.effective_date:
            return False
        if self.expiry_date and now > self.expiry_date:
            return False
        return self.status == PolicyStatus.ACTIVE


class PolicyViolation(BaseModel):
    """ポリシー違反"""
    violation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str
    rule_id: str
    violation_type: ViolationType
    severity: RuleSeverity
    title: str
    description: str
    violated_data: Dict[str, Any] = {}
    context: Dict[str, Any] = {}
    detected_at: datetime = Field(default_factory=datetime.now)
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    assignee: Optional[str] = None
    department: Optional[str] = None
    run_id: Optional[str] = None
    block_id: Optional[str] = None
    
    def is_resolved(self) -> bool:
        """解決済みかチェック"""
        return self.resolved_at is not None
    
    def resolve(self, notes: str = None) -> None:
        """違反を解決済みにマーク"""
        self.resolved_at = datetime.now()
        if notes:
            self.resolution_notes = notes


class PolicyExecutionResult(BaseModel):
    """ポリシー実行結果"""
    policy_id: str
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    executed_at: datetime = Field(default_factory=datetime.now)
    success: bool
    rules_evaluated: int = 0
    rules_passed: int = 0
    rules_failed: int = 0
    violations: List[PolicyViolation] = []
    execution_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    context: Dict[str, Any] = {}
    
    def add_violation(self, violation: PolicyViolation) -> None:
        """違反を追加"""
        self.violations.append(violation)
        self.rules_failed += 1
    
    def get_violations_by_severity(self, severity: RuleSeverity) -> List[PolicyViolation]:
        """重要度別違反一覧を取得"""
        return [v for v in self.violations if v.severity == severity]


class PolicyDistribution(BaseModel):
    """ポリシー配布情報"""
    distribution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str
    target_systems: List[str] = []
    target_departments: List[str] = []
    target_users: List[str] = []
    distributed_at: datetime = Field(default_factory=datetime.now)
    distribution_method: str = "automatic"  # automatic, manual, scheduled
    status: str = "pending"  # pending, distributed, failed
    error_message: Optional[str] = None
    
    def mark_distributed(self) -> None:
        """配布完了にマーク"""
        self.status = "distributed"
        self.distributed_at = datetime.now()
    
    def mark_failed(self, error: str) -> None:
        """配布失敗にマーク"""
        self.status = "failed"
        self.error_message = error


class PolicyAuditLog(BaseModel):
    """ポリシー監査ログ"""
    log_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    policy_id: str
    action: str  # created, updated, deleted, executed, distributed
    actor: str  # ユーザーID
    timestamp: datetime = Field(default_factory=datetime.now)
    details: Dict[str, Any] = {}
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def add_detail(self, key: str, value: Any) -> None:
        """詳細情報を追加"""
        self.details[key] = value