"""ポリシーエンジン

Policy-as-Codeの中核となるポリシー実行エンジン。
ポリシーの読み込み、評価、違反検知、結果記録を統合的に管理します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import json
import os
import time
import logging
from pathlib import Path

from .models import (
    Policy, PolicyRule, PolicyViolation, PolicyExecutionResult, 
    PolicyAuditLog, RuleSeverity, ViolationType, PolicyStatus
)
from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType

# ロガー設定
logger = logging.getLogger(__name__)


class PolicyEngine:
    """ポリシーエンジン"""
    
    def __init__(self, policy_dir: str = "designs/policies", evidence_vault: EvidenceVault = None):
        """
        ポリシーエンジンの初期化
        
        Args:
            policy_dir: ポリシー定義ファイルディレクトリ
            evidence_vault: Evidence Vault（証跡保存用）
        """
        self.policy_dir = Path(policy_dir)
        self.evidence_vault = evidence_vault
        self.policies: Dict[str, Policy] = {}
        self.audit_logs: List[PolicyAuditLog] = []
        
        # ポリシーディレクトリ作成
        self.policy_dir.mkdir(parents=True, exist_ok=True)
        
        # ポリシー読み込み
        self._load_policies()
    
    def _load_policies(self) -> None:
        """ポリシー定義ファイルの読み込み"""
        try:
            for policy_file in self.policy_dir.glob("*.json"):
                try:
                    with open(policy_file, 'r', encoding='utf-8') as f:
                        policy_data = json.load(f)
                        policy = Policy(**policy_data)
                        self.policies[policy.policy_id] = policy
                        logger.info(f"ポリシー読み込み完了: {policy.name} ({policy.policy_id})")
                except Exception as e:
                    logger.error(f"ポリシーファイル読み込みエラー {policy_file}: {str(e)}")
        except Exception as e:
            logger.error(f"ポリシーディレクトリアクセスエラー: {str(e)}")
    
    def save_policy(self, policy: Policy, actor: str = "system") -> bool:
        """
        ポリシーの保存
        
        Args:
            policy: 保存するポリシー
            actor: 実行者
            
        Returns:
            保存成功フラグ
        """
        try:
            # ポリシーファイル保存
            policy_file = self.policy_dir / f"{policy.policy_id}.json"
            with open(policy_file, 'w', encoding='utf-8') as f:
                json.dump(policy.dict(), f, ensure_ascii=False, indent=2, default=str)
            
            # メモリ上のポリシー更新
            self.policies[policy.policy_id] = policy
            
            # 監査ログ記録
            audit_log = PolicyAuditLog(
                policy_id=policy.policy_id,
                action="saved",
                actor=actor
            )
            audit_log.add_detail("policy_name", policy.name)
            audit_log.add_detail("policy_version", policy.version)
            self.audit_logs.append(audit_log)
            
            logger.info(f"ポリシー保存完了: {policy.name} ({policy.policy_id})")
            return True
            
        except Exception as e:
            logger.error(f"ポリシー保存エラー: {str(e)}")
            return False
    
    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """ポリシー取得"""
        return self.policies.get(policy_id)
    
    def get_active_policies(self) -> List[Policy]:
        """有効なポリシー一覧を取得"""
        return [policy for policy in self.policies.values() if policy.is_effective()]
    
    def evaluate_policy(self, policy_id: str, data: Dict[str, Any], 
                       context: Dict[str, Any] = None) -> PolicyExecutionResult:
        """
        ポリシーの評価実行
        
        Args:
            policy_id: ポリシーID
            data: 評価対象データ
            context: 実行コンテキスト
            
        Returns:
            ポリシー実行結果
        """
        start_time = time.time()
        context = context or {}
        
        # 実行結果初期化
        result = PolicyExecutionResult(
            policy_id=policy_id,
            success=False,
            context=context
        )
        
        try:
            policy = self.get_policy(policy_id)
            if not policy:
                result.error_message = f"ポリシーが見つかりません: {policy_id}"
                return result
            
            if not policy.is_effective():
                result.error_message = f"ポリシーが無効です: {policy.name}"
                return result
            
            # ルール評価
            active_rules = policy.get_active_rules()
            result.rules_evaluated = len(active_rules)
            
            for rule in active_rules:
                try:
                    violation = self._evaluate_rule(policy, rule, data, context)
                    if violation:
                        result.add_violation(violation)
                    else:
                        result.rules_passed += 1
                        
                except Exception as e:
                    logger.error(f"ルール評価エラー {rule.rule_id}: {str(e)}")
                    # ルール評価エラーも違反として扱う
                    error_violation = PolicyViolation(
                        policy_id=policy_id,
                        rule_id=rule.rule_id,
                        violation_type=ViolationType.RULE_VIOLATION,
                        severity=RuleSeverity.HIGH,
                        title=f"ルール評価エラー: {rule.name}",
                        description=f"ルール評価中にエラーが発生しました: {str(e)}",
                        violated_data=data,
                        context=context
                    )
                    result.add_violation(error_violation)
            
            # 実行成功判定
            result.success = True
            result.execution_time_ms = (time.time() - start_time) * 1000
            
            # 監査ログ記録
            audit_log = PolicyAuditLog(
                policy_id=policy_id,
                action="executed",
                actor=context.get("actor", "system")
            )
            audit_log.add_detail("rules_evaluated", result.rules_evaluated)
            audit_log.add_detail("violations_found", len(result.violations))
            self.audit_logs.append(audit_log)
            
            # Evidence Vaultに結果保存
            if self.evidence_vault:
                self._store_execution_result(result)
            
            logger.info(f"ポリシー評価完了: {policy.name}, 違反数: {len(result.violations)}")
            
        except Exception as e:
            result.error_message = str(e)
            result.execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"ポリシー評価エラー {policy_id}: {str(e)}")
        
        return result
    
    def _evaluate_rule(self, policy: Policy, rule: PolicyRule, data: Dict[str, Any], 
                      context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """
        個別ルールの評価
        
        Args:
            policy: ポリシー
            rule: 評価ルール
            data: 評価対象データ
            context: 実行コンテキスト
            
        Returns:
            違反情報（違反がない場合はNone）
        """
        try:
            # ルール式の評価
            violation = None
            
            if rule.rule_type == "expression":
                violation = self._evaluate_expression_rule(policy, rule, data, context)
            elif rule.rule_type == "threshold":
                violation = self._evaluate_threshold_rule(policy, rule, data, context)
            elif rule.rule_type == "approval_required":
                violation = self._evaluate_approval_rule(policy, rule, data, context)
            elif rule.rule_type == "segregation_duty":
                violation = self._evaluate_segregation_rule(policy, rule, data, context)
            else:
                # 未対応ルールタイプ
                violation = PolicyViolation(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    violation_type=ViolationType.RULE_VIOLATION,
                    severity=rule.severity,
                    title=f"未対応ルールタイプ: {rule.rule_type}",
                    description=f"ルールタイプ '{rule.rule_type}' は実装されていません",
                    violated_data=data,
                    context=context
                )
            
            return violation
            
        except Exception as e:
            # ルール評価エラー
            return PolicyViolation(
                policy_id=policy.policy_id,
                rule_id=rule.rule_id,
                violation_type=ViolationType.RULE_VIOLATION,
                severity=RuleSeverity.HIGH,
                title=f"ルール評価エラー: {rule.name}",
                description=f"ルール評価中にエラーが発生しました: {str(e)}",
                violated_data=data,
                context=context
            )
    
    def _evaluate_expression_rule(self, policy: Policy, rule: PolicyRule, 
                                data: Dict[str, Any], context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """式ルールの評価"""
        try:
            # 簡易式評価（実際の実装では安全な式評価器を使用）
            expression = rule.expression
            
            # データからの値置換
            for key, value in data.items():
                expression = expression.replace(f"${key}", str(value))
            
            # 安全な評価（実際にはより厳密な式評価器を使用すべき）
            if "==" in expression:
                left, right = expression.split("==", 1)
                result = left.strip() == right.strip()
            elif ">" in expression:
                left, right = expression.split(">", 1)
                result = float(left.strip()) > float(right.strip())
            elif "<" in expression:
                left, right = expression.split("<", 1)
                result = float(left.strip()) < float(right.strip())
            else:
                # デフォルトは文字列として評価
                result = bool(expression)
            
            # ルール違反チェック
            if not result:
                return PolicyViolation(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    violation_type=ViolationType.RULE_VIOLATION,
                    severity=rule.severity,
                    title=f"式ルール違反: {rule.name}",
                    description=f"式 '{rule.expression}' の評価が失敗しました",
                    violated_data=data,
                    context=context
                )
            
            return None
            
        except Exception as e:
            return PolicyViolation(
                policy_id=policy.policy_id,
                rule_id=rule.rule_id,
                violation_type=ViolationType.RULE_VIOLATION,
                severity=RuleSeverity.HIGH,
                title=f"式評価エラー: {rule.name}",
                description=f"式評価中にエラーが発生しました: {str(e)}",
                violated_data=data,
                context=context
            )
    
    def _evaluate_threshold_rule(self, policy: Policy, rule: PolicyRule,
                               data: Dict[str, Any], context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """閾値ルールの評価"""
        try:
            field = rule.parameters.get("field")
            threshold = rule.parameters.get("threshold")
            operator = rule.parameters.get("operator", ">")
            
            if not field or threshold is None:
                return PolicyViolation(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    violation_type=ViolationType.RULE_VIOLATION,
                    severity=RuleSeverity.HIGH,
                    title=f"閾値ルール設定エラー: {rule.name}",
                    description="field または threshold パラメータが設定されていません",
                    violated_data=data,
                    context=context
                )
            
            value = data.get(field)
            if value is None:
                return PolicyViolation(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    violation_type=ViolationType.RULE_VIOLATION,
                    severity=rule.severity,
                    title=f"データ不足: {rule.name}",
                    description=f"フィールド '{field}' がデータに含まれていません",
                    violated_data=data,
                    context=context
                )
            
            # 閾値チェック
            violation_detected = False
            if operator == ">" and float(value) > float(threshold):
                violation_detected = True
            elif operator == "<" and float(value) < float(threshold):
                violation_detected = True
            elif operator == ">=" and float(value) >= float(threshold):
                violation_detected = True
            elif operator == "<=" and float(value) <= float(threshold):
                violation_detected = True
            elif operator == "==" and float(value) == float(threshold):
                violation_detected = True
            
            if violation_detected:
                return PolicyViolation(
                    policy_id=policy.policy_id,
                    rule_id=rule.rule_id,
                    violation_type=ViolationType.THRESHOLD_EXCEEDED,
                    severity=rule.severity,
                    title=f"閾値超過: {rule.name}",
                    description=f"フィールド '{field}' の値 {value} が閾値 {threshold} を超過しました（{operator}）",
                    violated_data=data,
                    context=context
                )
            
            return None
            
        except Exception as e:
            return PolicyViolation(
                policy_id=policy.policy_id,
                rule_id=rule.rule_id,
                violation_type=ViolationType.RULE_VIOLATION,
                severity=RuleSeverity.HIGH,
                title=f"閾値評価エラー: {rule.name}",
                description=f"閾値評価中にエラーが発生しました: {str(e)}",
                violated_data=data,
                context=context
            )
    
    def _evaluate_approval_rule(self, policy: Policy, rule: PolicyRule,
                              data: Dict[str, Any], context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """承認必須ルールの評価"""
        approval_status = data.get("approval_status")
        required_approvers = rule.parameters.get("required_approvers", 1)
        
        if approval_status != "approved":
            return PolicyViolation(
                policy_id=policy.policy_id,
                rule_id=rule.rule_id,
                violation_type=ViolationType.MISSING_APPROVAL,
                severity=rule.severity,
                title=f"承認不足: {rule.name}",
                description=f"必要な承認が取得されていません（必要承認者数: {required_approvers}）",
                violated_data=data,
                context=context
            )
        
        return None
    
    def _evaluate_segregation_rule(self, policy: Policy, rule: PolicyRule,
                                 data: Dict[str, Any], context: Dict[str, Any]) -> Optional[PolicyViolation]:
        """職務分掌ルールの評価"""
        initiator = data.get("initiator")
        approver = data.get("approver")
        
        if initiator and approver and initiator == approver:
            return PolicyViolation(
                policy_id=policy.policy_id,
                rule_id=rule.rule_id,
                violation_type=ViolationType.SEGREGATION_DUTY,
                severity=rule.severity,
                title=f"職務分掌違反: {rule.name}",
                description=f"申請者と承認者が同一人物です: {initiator}",
                violated_data=data,
                context=context
            )
        
        return None
    
    def _store_execution_result(self, result: PolicyExecutionResult) -> None:
        """実行結果をEvidence Vaultに保存"""
        try:
            evidence_id = f"policy_execution_{result.execution_id}"
            metadata = EvidenceMetadata(
                evidence_id=evidence_id,
                evidence_type=EvidenceType.CONTROL_RESULT,
                block_id="PolicyEngine",
                run_id=result.context.get("run_id", ""),
                timestamp=result.executed_at,
                file_path=f"evidence/policy/{result.executed_at.strftime('%Y-%m-%d')}/{evidence_id}.json",
                file_hash="",
                file_size=0,
                retention_until=datetime.now() + timedelta(days=2555),
                tags=["policy_execution", "compliance"],
                risk_level="medium"
            )
            
            evidence_data = {
                "execution_result": result.dict(),
                "violations": [v.dict() for v in result.violations],
                "execution_summary": {
                    "policy_id": result.policy_id,
                    "success": result.success,
                    "rules_evaluated": result.rules_evaluated,
                    "rules_passed": result.rules_passed,
                    "rules_failed": result.rules_failed,
                    "violation_count": len(result.violations),
                    "execution_time_ms": result.execution_time_ms
                }
            }
            
            self.evidence_vault.store_evidence(evidence_data, metadata)
            logger.info(f"ポリシー実行結果をEvidence Vaultに保存: {evidence_id}")
            
        except Exception as e:
            logger.error(f"Evidence Vault保存エラー: {str(e)}")
    
    def get_violations(self, policy_id: str = None, severity: RuleSeverity = None) -> List[PolicyViolation]:
        """違反一覧を取得"""
        # 実際の実装ではデータベースから取得
        violations = []
        # 簡易実装（メモリ上のデータから検索）
        return violations
    
    def create_sample_policies(self) -> None:
        """サンプルポリシーの作成"""
        # 購買承認ポリシー
        purchase_policy = Policy(
            name="購買承認ポリシー",
            description="購買申請に対する承認要件を定義",
            policy_type="compliance",
            rules=[
                PolicyRule(
                    name="高額承認必須",
                    description="100万円以上の購買には部長承認が必要",
                    rule_type="threshold",
                    expression="amount > 1000000",
                    parameters={
                        "field": "amount",
                        "threshold": 1000000,
                        "operator": ">"
                    },
                    severity=RuleSeverity.HIGH
                ),
                PolicyRule(
                    name="申請者承認者分離",
                    description="申請者と承認者は異なる人物である必要がある",
                    rule_type="segregation_duty",
                    expression="initiator != approver",
                    severity=RuleSeverity.CRITICAL
                )
            ],
            tags=["購買", "承認", "職務分掌"],
            department="購買部",
            status=PolicyStatus.ACTIVE
        )
        
        # 支払いポリシー
        payment_policy = Policy(
            name="支払いポリシー",
            description="支払い処理に関するコンプライアンス要件",
            policy_type="financial",
            rules=[
                PolicyRule(
                    name="請求書承認確認",
                    description="支払い前に請求書の承認が必要",
                    rule_type="approval_required",
                    expression="invoice_approved == true",
                    parameters={
                        "required_approvers": 1
                    },
                    severity=RuleSeverity.HIGH
                ),
                PolicyRule(
                    name="支払い限度額チェック",
                    description="日次支払い限度額の確認",
                    rule_type="threshold",
                    expression="daily_payment_total <= 10000000",
                    parameters={
                        "field": "daily_payment_total",
                        "threshold": 10000000,
                        "operator": "<="
                    },
                    severity=RuleSeverity.MEDIUM
                )
            ],
            tags=["支払い", "財務", "承認"],
            department="財務部",
            status=PolicyStatus.ACTIVE
        )
        
        # ポリシー保存
        self.save_policy(purchase_policy, "system")
        self.save_policy(payment_policy, "system")
        
        logger.info("サンプルポリシーを作成しました")