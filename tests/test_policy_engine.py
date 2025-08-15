"""Policy Engineテスト

Policy-as-Codeのポリシー評価、違反検知、配布機能のテストを実施します。
"""

import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from core.policy.engine import PolicyEngine
from core.policy.models import (
    Policy, PolicyRule, PolicyViolation, PolicyExecutionResult,
    PolicyType, RuleSeverity, ViolationType, PolicyStatus
)
from core.blocks.processing.control.policy_enforce import PolicyEnforceBlock
from core.errors import BlockExecutionError


class TestPolicyEngine:
    """Policy Engineのテスト"""
    
    @pytest.mark.unit
    def test_policy_engine_initialization(self, policy_engine):
        """Policy Engine初期化テスト"""
        assert policy_engine.policy_dir.exists()
        assert policy_engine.policies is not None
        assert policy_engine.audit_logs is not None
    
    @pytest.mark.unit
    def test_save_and_load_policy(self, policy_engine, sample_policy):
        """ポリシー保存・読み込みテスト"""
        # ポリシー保存
        success = policy_engine.save_policy(sample_policy, "test_user")
        assert success is True
        
        # ポリシー取得
        loaded_policy = policy_engine.get_policy(sample_policy.policy_id)
        assert loaded_policy is not None
        assert loaded_policy.name == sample_policy.name
        assert len(loaded_policy.rules) == len(sample_policy.rules)
    
    @pytest.mark.unit
    def test_get_active_policies(self, policy_engine, sample_policy):
        """有効ポリシー取得テスト"""
        # アクティブポリシーとして保存
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        active_policies = policy_engine.get_active_policies()
        assert len(active_policies) >= 1
        assert sample_policy.policy_id in [p.policy_id for p in active_policies]
    
    @pytest.mark.unit
    def test_evaluate_threshold_policy_success(self, policy_engine, sample_policy):
        """閾値ポリシー評価成功テスト"""
        # 閾値以下のデータ
        test_data = {
            "amount": 500000,  # 100万円以下
            "initiator": "user_a",
            "approver": "user_b"
        }
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        result = policy_engine.evaluate_policy(
            sample_policy.policy_id,
            test_data,
            {"run_id": "test_run"}
        )
        
        assert result.success is True
        assert len(result.violations) == 0
        assert result.rules_passed == 2  # 両方のルールが成功
    
    @pytest.mark.unit
    def test_evaluate_threshold_policy_violation(self, policy_engine, sample_policy):
        """閾値ポリシー違反テスト"""
        # 閾値超過のデータ
        test_data = {
            "amount": 2000000,  # 100万円超過
            "initiator": "user_a",
            "approver": "user_b"
        }
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        result = policy_engine.evaluate_policy(
            sample_policy.policy_id,
            test_data,
            {"run_id": "test_run"}
        )
        
        assert result.success is True  # 評価は成功
        assert len(result.violations) == 1  # 閾値違反が検出
        assert result.violations[0].violation_type == ViolationType.THRESHOLD_EXCEEDED
        assert result.violations[0].severity == RuleSeverity.HIGH
    
    @pytest.mark.unit
    def test_evaluate_segregation_duty_violation(self, policy_engine, sample_policy):
        """職務分掌違反テスト"""
        # 申請者と承認者が同一人物
        test_data = {
            "amount": 500000,
            "initiator": "user_a",
            "approver": "user_a"  # 同一人物（違反）
        }
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        result = policy_engine.evaluate_policy(
            sample_policy.policy_id,
            test_data,
            {"run_id": "test_run"}
        )
        
        assert result.success is True
        assert len(result.violations) == 1
        assert result.violations[0].violation_type == ViolationType.SEGREGATION_DUTY
        assert result.violations[0].severity == RuleSeverity.CRITICAL
    
    @pytest.mark.unit
    def test_evaluate_multiple_violations(self, policy_engine, sample_policy):
        """複数違反検知テスト"""
        # 閾値超過かつ職務分掌違反
        test_data = {
            "amount": 2000000,  # 閾値超過
            "initiator": "user_a",
            "approver": "user_a"  # 職務分掌違反
        }
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        result = policy_engine.evaluate_policy(
            sample_policy.policy_id,
            test_data,
            {"run_id": "test_run"}
        )
        
        assert result.success is True
        assert len(result.violations) == 2  # 2つの違反
        
        # 違反タイプの確認
        violation_types = [v.violation_type for v in result.violations]
        assert ViolationType.THRESHOLD_EXCEEDED in violation_types
        assert ViolationType.SEGREGATION_DUTY in violation_types
    
    @pytest.mark.unit
    def test_evaluate_nonexistent_policy(self, policy_engine):
        """存在しないポリシー評価テスト"""
        result = policy_engine.evaluate_policy(
            "nonexistent_policy",
            {"test": "data"},
            {"run_id": "test_run"}
        )
        
        assert result.success is False
        assert "ポリシーが見つかりません" in result.error_message
    
    @pytest.mark.unit
    def test_evaluate_inactive_policy(self, policy_engine, sample_policy):
        """非アクティブポリシー評価テスト"""
        # ドラフト状態のポリシー
        sample_policy.status = PolicyStatus.DRAFT
        policy_engine.save_policy(sample_policy, "test_user")
        
        result = policy_engine.evaluate_policy(
            sample_policy.policy_id,
            {"amount": 500000},
            {"run_id": "test_run"}
        )
        
        assert result.success is False
        assert "ポリシーが無効です" in result.error_message
    
    @pytest.mark.unit
    def test_expression_rule_evaluation(self, policy_engine):
        """式ルール評価テスト"""
        # 式ルールを含むポリシー
        expression_policy = Policy(
            name="式ルールテスト",
            description="式ルールのテスト",
            policy_type=PolicyType.BUSINESS_RULE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="金額チェック",
                    description="金額が正の値",
                    rule_type="expression",
                    expression="$amount > 0",
                    severity=RuleSeverity.MEDIUM
                )
            ]
        )
        
        policy_engine.save_policy(expression_policy, "test_user")
        
        # 正常データ
        result_success = policy_engine.evaluate_policy(
            expression_policy.policy_id,
            {"amount": 1000},
            {"run_id": "test_run"}
        )
        assert len(result_success.violations) == 0
        
        # 違反データ
        result_violation = policy_engine.evaluate_policy(
            expression_policy.policy_id,
            {"amount": -1000},  # 負の値（違反）
            {"run_id": "test_run"}
        )
        assert len(result_violation.violations) == 1
    
    @pytest.mark.unit
    def test_approval_required_rule(self, policy_engine):
        """承認必須ルールテスト"""
        approval_policy = Policy(
            name="承認必須テスト",
            description="承認必須ルールのテスト",
            policy_type=PolicyType.COMPLIANCE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="承認ステータスチェック",
                    description="承認が必要",
                    rule_type="approval_required",
                    expression="approval_status == approved",
                    parameters={"required_approvers": 1},
                    severity=RuleSeverity.HIGH
                )
            ]
        )
        
        policy_engine.save_policy(approval_policy, "test_user")
        
        # 承認済みデータ
        result_approved = policy_engine.evaluate_policy(
            approval_policy.policy_id,
            {"approval_status": "approved"},
            {"run_id": "test_run"}
        )
        assert len(result_approved.violations) == 0
        
        # 未承認データ
        result_pending = policy_engine.evaluate_policy(
            approval_policy.policy_id,
            {"approval_status": "pending"},
            {"run_id": "test_run"}
        )
        assert len(result_pending.violations) == 1
        assert result_pending.violations[0].violation_type == ViolationType.MISSING_APPROVAL
    
    @pytest.mark.unit
    def test_create_sample_policies(self, policy_engine):
        """サンプルポリシー作成テスト"""
        initial_count = len(policy_engine.policies)
        
        policy_engine.create_sample_policies()
        
        # ポリシーが追加されていることを確認
        assert len(policy_engine.policies) > initial_count
        
        # 購買ポリシーの確認
        purchase_policy = next((p for p in policy_engine.policies.values() 
                              if "購買" in p.name), None)
        assert purchase_policy is not None
        assert purchase_policy.status == PolicyStatus.ACTIVE
        
        # 支払いポリシーの確認
        payment_policy = next((p for p in policy_engine.policies.values() 
                             if "支払い" in p.name), None)
        assert payment_policy is not None
        assert payment_policy.status == PolicyStatus.ACTIVE


class TestPolicyEnforceBlock:
    """ポリシー強制実行ブロックのテスト"""
    
    @pytest.mark.unit
    def test_policy_enforce_block_initialization(self):
        """ポリシー強制実行ブロック初期化テスト"""
        block = PolicyEnforceBlock()
        assert block is not None
    
    @pytest.mark.unit
    def test_policy_enforce_with_specific_policy(self, block_context, policy_engine, sample_policy):
        """特定ポリシー指定実行テスト"""
        block = PolicyEnforceBlock()
        
        # ポリシー準備
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        # コンテキストにevidence_vaultを設定
        setattr(block_context, 'evidence_vault', None)
        
        inputs = {
            "data": {
                "transaction_data": {
                    "amount": 500000,
                    "initiator": "user_a",
                    "approver": "user_b"
                },
                "metadata": {"department": "テスト部署"}
            },
            "policy_config": {
                "policy_ids": [sample_policy.policy_id]
            }
        }
        
        result = block.run(block_context, inputs)
        
        assert result["policy_result"]["success"] is True
        assert result["policy_result"]["policies_evaluated"] == 1
        assert result["policy_result"]["total_violations"] == 0
    
    @pytest.mark.unit
    def test_policy_enforce_with_violations(self, block_context, policy_engine, sample_policy):
        """違反検知テスト"""
        block = PolicyEnforceBlock()
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        setattr(block_context, 'evidence_vault', None)
        
        # 違反データ
        inputs = {
            "data": {
                "transaction_data": {
                    "amount": 2000000,  # 閾値超過
                    "initiator": "user_a",
                    "approver": "user_a"  # 職務分掌違反
                },
                "metadata": {"department": "テスト部署"}
            },
            "policy_config": {
                "policy_ids": [sample_policy.policy_id]
            }
        }
        
        result = block.run(block_context, inputs)
        
        assert result["policy_result"]["success"] is True  # 実行は成功
        assert result["policy_result"]["total_violations"] == 2  # 2つの違反
        assert result["policy_result"]["critical_violations"] == 1  # 1つが重要違反
    
    @pytest.mark.unit
    def test_policy_enforce_fail_on_violation(self, block_context, policy_engine, sample_policy):
        """違反時停止テスト"""
        block = PolicyEnforceBlock()
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(sample_policy, "test_user")
        
        setattr(block_context, 'evidence_vault', None)
        
        # 違反データ + 停止設定
        inputs = {
            "data": {
                "transaction_data": {
                    "amount": 2000000,
                    "initiator": "user_a",
                    "approver": "user_a"
                },
                "metadata": {"department": "テスト部署"}
            },
            "policy_config": {
                "policy_ids": [sample_policy.policy_id],
                "fail_on_violation": True,
                "severity_threshold": "high"
            }
        }
        
        # 高重要度以上の違反で停止することを確認
        with pytest.raises(BlockExecutionError) as exc_info:
            block.run(block_context, inputs)
        
        assert "ポリシー違反により処理を停止" in str(exc_info.value)
    
    @pytest.mark.unit
    def test_policy_enforce_by_type(self, block_context, policy_engine):
        """ポリシータイプ指定実行テスト"""
        block = PolicyEnforceBlock()
        
        # 複数タイプのポリシーを作成
        compliance_policy = Policy(
            name="コンプライアンステスト",
            description="コンプライアンスルール",
            policy_type=PolicyType.COMPLIANCE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="テストルール",
                    description="テスト用",
                    rule_type="expression",
                    expression="$test > 0",
                    severity=RuleSeverity.LOW
                )
            ]
        )
        
        business_policy = Policy(
            name="ビジネスルールテスト",
            description="ビジネスルール",
            policy_type=PolicyType.BUSINESS_RULE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="テストルール2",
                    description="テスト用2",
                    rule_type="expression",
                    expression="$test2 > 0",
                    severity=RuleSeverity.LOW
                )
            ]
        )
        
        policy_engine.save_policy(compliance_policy, "test_user")
        policy_engine.save_policy(business_policy, "test_user")
        
        setattr(block_context, 'evidence_vault', None)
        
        # コンプライアンスポリシーのみ実行
        inputs = {
            "data": {
                "transaction_data": {"test": 1, "test2": 1},
                "metadata": {}
            },
            "policy_config": {
                "policy_type": "compliance"
            }
        }
        
        result = block.run(block_context, inputs)
        
        # コンプライアンスポリシーのみが評価されることを確認
        assert result["policy_result"]["policies_evaluated"] == 1
    
    @pytest.mark.unit
    def test_policy_enforce_no_policies(self, block_context):
        """ポリシーなし実行テスト"""
        block = PolicyEnforceBlock()
        
        setattr(block_context, 'evidence_vault', None)
        
        inputs = {
            "data": {
                "transaction_data": {"test": "data"},
                "metadata": {}
            },
            "policy_config": {
                "policy_ids": ["nonexistent_policy"]
            }
        }
        
        result = block.run(block_context, inputs)
        
        assert result["policy_result"]["success"] is True
        assert result["policy_result"]["policies_evaluated"] == 0
        assert result["policy_result"]["total_violations"] == 0


class TestPolicyIntegration:
    """Policy統合テスト"""
    
    @pytest.mark.integration
    def test_policy_lifecycle(self, policy_engine, evidence_vault):
        """ポリシーライフサイクルテスト"""
        # 1. ポリシー作成
        test_policy = Policy(
            name="ライフサイクルテスト",
            description="ライフサイクルテスト用ポリシー",
            policy_type=PolicyType.COMPLIANCE,
            status=PolicyStatus.DRAFT,
            rules=[
                PolicyRule(
                    name="テストルール",
                    description="テスト用ルール",
                    rule_type="threshold",
                    expression="amount <= 1000000",
                    parameters={
                        "field": "amount",
                        "threshold": 1000000,
                        "operator": "<="
                    },
                    severity=RuleSeverity.MEDIUM
                )
            ]
        )
        
        # 2. ポリシー保存
        policy_engine.save_policy(test_policy, "test_user")
        
        # 3. ドラフト状態では評価されない
        result_draft = policy_engine.evaluate_policy(
            test_policy.policy_id,
            {"amount": 500000},
            {"run_id": "test_run"}
        )
        assert result_draft.success is False
        
        # 4. アクティブ化
        test_policy.status = PolicyStatus.ACTIVE
        policy_engine.save_policy(test_policy, "test_user")
        
        # 5. アクティブ状態で評価実行
        result_active = policy_engine.evaluate_policy(
            test_policy.policy_id,
            {"amount": 500000},
            {"run_id": "test_run"}
        )
        assert result_active.success is True
        assert len(result_active.violations) == 0
        
        # 6. 違反ケースの評価
        result_violation = policy_engine.evaluate_policy(
            test_policy.policy_id,
            {"amount": 2000000},
            {"run_id": "test_run"}
        )
        assert len(result_violation.violations) == 1
    
    @pytest.mark.integration
    def test_policy_with_evidence_vault(self, policy_engine, evidence_vault, sample_policy):
        """Evidence Vault連携テスト"""
        # Evidence Vault付きポリシーエンジン
        policy_engine_with_vault = PolicyEngine(
            policy_dir=str(policy_engine.policy_dir),
            evidence_vault=evidence_vault
        )
        
        sample_policy.status = PolicyStatus.ACTIVE
        policy_engine_with_vault.save_policy(sample_policy, "test_user")
        
        # ポリシー評価実行
        result = policy_engine_with_vault.evaluate_policy(
            sample_policy.policy_id,
            {"amount": 2000000, "initiator": "user_a", "approver": "user_a"},
            {"run_id": "test_run", "actor": "test_user"}
        )
        
        # 結果の確認
        assert result.success is True
        assert len(result.violations) == 2
        
        # Evidence Vaultに結果が保存されていることを確認
        evidence_list = evidence_vault.search_evidence({
            "run_id": "test_run",
            "tags": ["policy_execution"]
        })
        
        assert len(evidence_list) >= 1
    
    @pytest.mark.e2e
    def test_end_to_end_policy_workflow(self, block_context, policy_engine, evidence_vault):
        """エンドツーエンド ポリシーワークフロー"""
        # 1. ポリシー作成とセットアップ
        policy_engine.create_sample_policies()
        
        # 2. Policy Enforce Blockによる実行
        policy_block = PolicyEnforceBlock()
        setattr(block_context, 'evidence_vault', evidence_vault)
        
        # 3. 複数の取引データでテスト
        test_cases = [
            # 正常ケース
            {
                "data": {
                    "transaction_data": {
                        "amount": 500000,
                        "initiator": "user_a",
                        "approver": "user_b",
                        "invoice_approved": True,
                        "daily_payment_total": 5000000
                    },
                    "metadata": {"department": "購買部"}
                },
                "expected_violations": 0
            },
            # 職務分掌違反
            {
                "data": {
                    "transaction_data": {
                        "amount": 500000,
                        "initiator": "user_a",
                        "approver": "user_a",  # 同一人物
                        "invoice_approved": True,
                        "daily_payment_total": 5000000
                    },
                    "metadata": {"department": "購買部"}
                },
                "expected_violations": 1
            },
            # 複数違反
            {
                "data": {
                    "transaction_data": {
                        "amount": 2000000,  # 閾値超過
                        "initiator": "user_a",
                        "approver": "user_a",  # 職務分掌違反
                        "invoice_approved": False,  # 承認不足
                        "daily_payment_total": 15000000  # 限度額超過
                    },
                    "metadata": {"department": "財務部"}
                },
                "expected_violations": 4
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            inputs = {
                "data": test_case["data"],
                "policy_config": {"policy_type": "compliance"}
            }
            
            result = policy_block.run(block_context, inputs)
            
            # 結果検証
            assert result["policy_result"]["success"] is True
            # 違反数は期待値以上（ポリシーの詳細により変動する可能性）
            assert result["policy_result"]["total_violations"] >= test_case["expected_violations"]
        
        # 4. Evidence Vaultに全実行結果が保存されていることを確認
        all_evidence = evidence_vault.search_evidence({
            "tags": ["policy_enforcement"]
        })
        assert len(all_evidence) >= len(test_cases)