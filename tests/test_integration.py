"""統合テスト

監査・内部統制機能の統合テスト、E2Eシナリオ、セキュリティテストを実施します。
"""

import pytest
import json
import os
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from core.evidence.vault import EvidenceVault
from core.policy.engine import PolicyEngine
from core.policy.models import Policy, PolicyRule, PolicyType, PolicyStatus, RuleSeverity
from core.blocks.processing.control.approval import ApprovalBlock
from core.blocks.processing.control.sod_check import SodCheckBlock
from core.blocks.processing.control.sampling import SamplingBlock
from core.blocks.processing.control.policy_enforce import PolicyEnforceBlock
from core.ui.auth import AuthManager
from core.reviewer.dashboard import ReviewerDashboard


class TestAuditControlsIntegration:
    """監査・内部統制機能統合テスト"""
    
    @pytest.mark.integration
    def test_complete_audit_workflow(self, temp_workspace, block_context):
        """完全な監査ワークフロー統合テスト"""
        # 1. システム初期化
        evidence_vault = EvidenceVault(
            os.path.join(temp_workspace, "evidence_vault"),
            encryption_password="integration_test_password"
        )
        
        policy_engine = PolicyEngine(
            policy_dir=os.path.join(temp_workspace, "policies"),
            evidence_vault=evidence_vault
        )
        
        # サンプルポリシー作成
        policy_engine.create_sample_policies()
        
        # 2. 承認プロセス
        approval_block = ApprovalBlock()
        approval_inputs = {
            "approval_request": {
                "request_id": "REQ-INTEGRATION-001",
                "requester": "user_a",
                "amount": 1500000,
                "description": "統合テスト購買申請",
                "attachments": []
            },
            "approval_policy": {
                "levels": [
                    {
                        "level": 1,
                        "min_amount": 0,
                        "max_amount": 1000000,
                        "required_approvers": 1,
                        "approver_roles": ["manager"],
                        "timeout_hours": 24
                    },
                    {
                        "level": 2,
                        "min_amount": 1000000,
                        "max_amount": 10000000,
                        "required_approvers": 2,
                        "approver_roles": ["director", "manager"],
                        "timeout_hours": 48
                    }
                ]
            }
        }
        
        setattr(block_context, 'evidence_vault', evidence_vault)
        approval_result = approval_block.execute(approval_inputs, block_context)
        
        # 3. 職務分掌チェック
        sod_block = SodCheckBlock()
        sod_inputs = {
            "transaction_data": {
                "transaction_id": "TXN-INTEGRATION-001",
                "transaction_type": "purchase",
                "amount": 1500000,
                "initiator": "user_a",
                "approver": "user_b",
                "processor": "user_c",
                "timestamp": datetime.now().isoformat()
            },
            "sod_matrix": {
                "incompatible_roles": [
                    ["initiator", "approver"],
                    ["approver", "processor"]
                ],
                "required_separation": True,
                "exception_roles": ["admin"]
            }
        }
        
        sod_result = sod_block.execute(sod_inputs, block_context)
        
        # 4. ポリシー検証
        policy_block = PolicyEnforceBlock()
        policy_inputs = {
            "data": {
                "transaction_data": {
                    "amount": 1500000,
                    "initiator": "user_a",
                    "approver": "user_b",
                    "approval_status": "approved",
                    "daily_payment_total": 5000000
                },
                "metadata": {
                    "department": "購買部",
                    "request_id": "REQ-INTEGRATION-001"
                }
            },
            "policy_config": {
                "policy_type": "compliance"
            }
        }
        
        policy_result = policy_block.execute(policy_inputs, block_context)
        
        # 5. サンプリング実行
        sampling_block = SamplingBlock()
        sampling_inputs = {
            "population_data": {
                "data_source": "integration_test_transactions",
                "total_items": 50,
                "total_value": 75000000,
                "items": [
                    {
                        "item_id": f"ITEM-{i:03d}",
                        "value": 1500000 + (i * 50000),
                        "risk_score": 0.2 + (i % 5) * 0.2,
                        "attributes": {
                            "department": "購買部" if i % 2 == 0 else "財務部",
                            "category": "A" if i < 20 else "B"
                        }
                    }
                    for i in range(50)
                ]
            },
            "sampling_parameters": {
                "method": "risk_based",
                "sample_size": 15,
                "risk_criteria": {
                    "high_risk_threshold": 0.7,
                    "medium_risk_threshold": 0.3,
                    "high_risk_percentage": 0.8
                }
            }
        }
        
        sampling_result = sampling_block.execute(sampling_inputs, block_context)
        
        # 結果検証
        assert approval_result["approval_result"]["success"] is True
        assert approval_result["approval_result"]["level_required"] == 2
        
        assert sod_result["sod_result"]["compliant"] is True
        assert len(sod_result["sod_result"]["violations"]) == 0
        
        assert policy_result["policy_result"]["success"] is True
        
        assert sampling_result["sampling_result"]["method_used"] == "risk_based"
        assert len(sampling_result["selected_items"]) == 15
        
        # 6. Evidence Vaultに全証跡が保存されていることを確認
        all_evidence = evidence_vault.search_evidence({})
        assert len(all_evidence) >= 4  # 各ブロックから最低1つずつ
        
        # 証跡タイプの確認
        evidence_types = [e.evidence_type.value for e in all_evidence]
        assert "control_result" in evidence_types
    
    @pytest.mark.e2e
    def test_end_to_end_compliance_scenario(self, temp_workspace, block_context):
        """エンドツーエンド コンプライアンスシナリオ"""
        # シナリオ: 高額購買申請の完全な処理フロー
        
        # システム初期化
        evidence_vault = EvidenceVault(
            os.path.join(temp_workspace, "evidence_vault"),
            encryption_password="e2e_test_password"
        )
        policy_engine = PolicyEngine(
            policy_dir=os.path.join(temp_workspace, "policies"),
            evidence_vault=evidence_vault
        )
        
        # カスタムポリシー作成
        compliance_policy = Policy(
            name="高額購買コンプライアンス",
            description="高額購買申請の完全なコンプライアンスチェック",
            policy_type=PolicyType.COMPLIANCE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="高額閾値チェック",
                    description="500万円以上は特別承認必要",
                    rule_type="threshold",
                    expression="amount > 5000000",
                    parameters={
                        "field": "amount",
                        "threshold": 5000000,
                        "operator": ">"
                    },
                    severity=RuleSeverity.CRITICAL
                ),
                PolicyRule(
                    name="職務分掌確認",
                    description="申請者と承認者の分離",
                    rule_type="segregation_duty",
                    expression="initiator != approver",
                    severity=RuleSeverity.HIGH
                ),
                PolicyRule(
                    name="承認ステータス確認",
                    description="適切な承認が必要",
                    rule_type="approval_required",
                    expression="approval_status == approved",
                    parameters={"required_approvers": 2},
                    severity=RuleSeverity.HIGH
                )
            ]
        )
        
        policy_engine.save_policy(compliance_policy, "system")
        
        setattr(block_context, 'evidence_vault', evidence_vault)
        
        # テストケース: 複数の購買申請パターン
        test_scenarios = [
            {
                "name": "正常な高額申請",
                "data": {
                    "amount": 6000000,
                    "initiator": "buyer_001",
                    "approver": "manager_001",
                    "approval_status": "approved",
                    "special_approval": True
                },
                "expected_violations": 0,
                "expected_critical": 0
            },
            {
                "name": "職務分掌違反",
                "data": {
                    "amount": 6000000,
                    "initiator": "buyer_001",
                    "approver": "buyer_001",  # 同一人物（違反）
                    "approval_status": "approved",
                    "special_approval": True
                },
                "expected_violations": 1,
                "expected_critical": 0  # 職務分掌はHIGH
            },
            {
                "name": "複数違反ケース",
                "data": {
                    "amount": 8000000,
                    "initiator": "buyer_002",
                    "approver": "buyer_002",  # 職務分掌違反
                    "approval_status": "pending",  # 承認不足
                    "special_approval": False  # 特別承認なし
                },
                "expected_violations": 3,
                "expected_critical": 1
            }
        ]
        
        # 各シナリオの実行
        scenario_results = []
        for scenario in test_scenarios:
            policy_block = PolicyEnforceBlock()
            
            inputs = {
                "data": {
                    "transaction_data": scenario["data"],
                    "metadata": {
                        "scenario_name": scenario["name"],
                        "test_run": "e2e_compliance"
                    }
                },
                "policy_config": {
                    "policy_ids": [compliance_policy.policy_id]
                }
            }
            
            result = policy_block.execute(inputs, block_context)
            scenario_results.append({
                "scenario": scenario["name"],
                "result": result,
                "data": scenario["data"]
            })
            
            # 結果検証
            assert result["policy_result"]["success"] is True
            assert result["policy_result"]["total_violations"] >= scenario["expected_violations"]
            assert result["policy_result"]["critical_violations"] >= scenario["expected_critical"]
        
        # 全体的な監査証跡の確認
        audit_evidence = evidence_vault.search_evidence({
            "tags": ["policy_enforcement"],
            "run_id": block_context.run_id
        })
        
        assert len(audit_evidence) >= len(test_scenarios)
        
        # 違反サマリの確認
        total_violations = sum(r["result"]["policy_result"]["total_violations"] 
                             for r in scenario_results)
        assert total_violations >= 4  # 最低期待違反数
        
        return scenario_results
    
    @pytest.mark.security
    def test_security_controls(self, temp_workspace):
        """セキュリティ統制テスト"""
        # 暗号化テスト
        evidence_vault = EvidenceVault(
            os.path.join(temp_workspace, "security_vault"),
            encryption_password="security_test_password_123"
        )
        
        # 機密データの保存
        sensitive_data = {
            "personal_id": "123-45-6789",
            "credit_card": "4111-1111-1111-1111",
            "bank_account": "1234567890",
            "salary": 5000000,
            "performance_review": "confidential content"
        }
        
        from core.evidence.metadata import EvidenceMetadata, EvidenceType
        metadata = EvidenceMetadata(
            evidence_id="security_test_001",
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id="security_test",
            run_id="security_run",
            timestamp=datetime.now(),
            file_path="security/test_001.json",
            file_hash="security_hash",
            file_size=len(json.dumps(sensitive_data)),
            retention_until=datetime.now() + timedelta(days=2555),
            tags=["security_test", "confidential"]
        )
        
        # 保存
        evidence_id = evidence_vault.store_evidence(sensitive_data, metadata)
        
        # ファイルが暗号化されていることを確認
        vault_file = evidence_vault.vault_path / metadata.file_path
        with open(vault_file, 'rb') as f:
            encrypted_content = f.read()
        
        # 機密情報が平文で含まれていないことを確認
        for sensitive_value in sensitive_data.values():
            if isinstance(sensitive_value, str):
                assert sensitive_value.encode() not in encrypted_content
        
        # 正常に復号化できることを確認
        retrieved_data = evidence_vault.retrieve_evidence(evidence_id)
        assert retrieved_data == sensitive_data
        
        # 不正なパスワードでのアクセス試行
        malicious_vault = EvidenceVault(
            os.path.join(temp_workspace, "security_vault"),
            encryption_password="wrong_password"
        )
        
        with pytest.raises(Exception):
            malicious_vault.retrieve_evidence(evidence_id)
    
    @pytest.mark.integration
    def test_reviewer_workspace_integration(self, temp_workspace):
        """Reviewer Workspace統合テスト"""
        # システム初期化
        evidence_vault = EvidenceVault(
            os.path.join(temp_workspace, "reviewer_vault"),
            encryption_password="reviewer_test_password"
        )
        
        policy_engine = PolicyEngine(
            policy_dir=os.path.join(temp_workspace, "policies"),
            evidence_vault=evidence_vault
        )
        
        # テストデータ生成
        policy_engine.create_sample_policies()
        
        # 複数の証跡を生成
        from .conftest import create_test_evidence
        from core.evidence.metadata import EvidenceType
        
        for i in range(10):
            test_data = {
                "test_transaction": f"TXN-{i:03d}",
                "amount": 1000000 + (i * 100000),
                "status": "completed" if i % 2 == 0 else "pending",
                "risk_level": "high" if i < 3 else "medium" if i < 7 else "low"
            }
            
            create_test_evidence(
                evidence_vault,
                EvidenceType.CONTROL_RESULT if i % 2 == 0 else EvidenceType.AUDIT_FINDING,
                test_data
            )
        
        # Reviewer Dashboard初期化とテスト
        dashboard = ReviewerDashboard(evidence_vault, policy_engine)
        
        # 統計データ取得テスト
        from datetime import date
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()
        
        stats = dashboard._get_dashboard_stats(start_date, end_date)
        
        # 統計データの妥当性確認
        assert stats['evidence']['total_count'] >= 10
        assert stats['policies']['total_policies'] >= 2
        assert stats['policies']['active_policies'] >= 2
        
        # 違反サマリテスト（サンプルデータ）
        assert 'by_severity' in stats['violations']
        assert 'by_type' in stats['violations']
    
    @pytest.mark.slow
    def test_performance_stress(self, temp_workspace):
        """パフォーマンス・ストレステスト"""
        import time
        
        evidence_vault = EvidenceVault(
            os.path.join(temp_workspace, "performance_vault"),
            encryption_password="performance_test_password"
        )
        
        # 大量データ処理テスト
        start_time = time.time()
        
        # 1000件の証跡を高速保存
        evidence_ids = []
        for i in range(1000):
            data = {
                "batch_id": "PERF-BATCH-001",
                "item_id": f"ITEM-{i:04d}",
                "value": 1000 + i,
                "timestamp": datetime.now().isoformat()
            }
            
            from core.evidence.metadata import EvidenceMetadata, EvidenceType
            metadata = EvidenceMetadata(
                evidence_id=f"perf_test_{i:04d}",
                evidence_type=EvidenceType.INPUT,
                block_id="performance_test",
                run_id="perf_run_001",
                timestamp=datetime.now(),
                file_path=f"performance/batch_001/item_{i:04d}.json",
                file_hash=f"hash_{i:04d}",
                file_size=len(json.dumps(data)),
                retention_until=datetime.now() + timedelta(days=2555),
                tags=["performance_test", "batch_001"]
            )
            
            evidence_id = evidence_vault.store_evidence(data, metadata)
            evidence_ids.append(evidence_id)
        
        store_time = time.time() - start_time
        
        # 検索性能テスト
        search_start = time.time()
        search_results = evidence_vault.search_evidence({
            "tags": ["performance_test"]
        })
        search_time = time.time() - search_start
        
        # 取得性能テスト
        retrieve_start = time.time()
        sample_ids = evidence_ids[::100]  # 10件をサンプル取得
        for eid in sample_ids:
            evidence_vault.retrieve_evidence(eid)
        retrieve_time = time.time() - retrieve_start
        
        # パフォーマンス要件確認
        assert store_time < 60.0  # 1000件保存が60秒以内
        assert search_time < 5.0   # 検索が5秒以内
        assert retrieve_time < 2.0 # 10件取得が2秒以内
        
        assert len(search_results) == 1000
        assert len(evidence_ids) == 1000
        
        print(f"Performance Results:")
        print(f"  Store 1000 items: {store_time:.2f}s")
        print(f"  Search 1000 items: {search_time:.2f}s")
        print(f"  Retrieve 10 items: {retrieve_time:.2f}s")


class TestErrorHandling:
    """エラーハンドリングテスト"""
    
    @pytest.mark.unit
    def test_corrupted_evidence_handling(self, evidence_vault, sample_evidence_metadata):
        """破損証跡処理テスト"""
        # 正常データを保存
        test_data = {"test": "corrupted data test"}
        evidence_vault.store_evidence(test_data, sample_evidence_metadata)
        
        # ファイルを故意に破損
        file_path = evidence_vault.vault_path / sample_evidence_metadata.file_path
        with open(file_path, 'wb') as f:
            f.write(b"corrupted_content")
        
        # 破損データの取得試行
        with pytest.raises(Exception):
            evidence_vault.retrieve_evidence(sample_evidence_metadata.evidence_id)
    
    @pytest.mark.unit
    def test_invalid_policy_handling(self, policy_engine):
        """不正ポリシー処理テスト"""
        # 不正なルールを含むポリシー
        invalid_policy = Policy(
            name="不正ポリシー",
            description="不正なルールを含むテスト",
            policy_type=PolicyType.COMPLIANCE,
            status=PolicyStatus.ACTIVE,
            rules=[
                PolicyRule(
                    name="不正ルール",
                    description="不正な式",
                    rule_type="expression",
                    expression="invalid_expression_syntax",
                    severity=RuleSeverity.MEDIUM
                )
            ]
        )
        
        policy_engine.save_policy(invalid_policy, "test_user")
        
        # 不正ポリシーの評価（エラーハンドリング確認）
        result = policy_engine.evaluate_policy(
            invalid_policy.policy_id,
            {"test": "data"},
            {"run_id": "error_test"}
        )
        
        # エラーが適切に処理されることを確認
        assert result.success is True  # 評価自体は成功
        assert len(result.violations) > 0  # エラーが違反として記録
    
    @pytest.mark.unit
    def test_network_failure_simulation(self, evidence_vault):
        """ネットワーク障害シミュレーション"""
        # Evidence Vaultのファイルシステムアクセスをモック
        with patch('builtins.open', side_effect=IOError("Network error")):
            with pytest.raises(Exception):
                from core.evidence.metadata import EvidenceMetadata, EvidenceType
                metadata = EvidenceMetadata(
                    evidence_id="network_test",
                    evidence_type=EvidenceType.CONTROL_RESULT,
                    block_id="network_test",
                    run_id="network_run",
                    timestamp=datetime.now(),
                    file_path="network/test.json",
                    file_hash="network_hash",
                    file_size=100,
                    retention_until=datetime.now() + timedelta(days=2555),
                    tags=["network_test"]
                )
                
                evidence_vault.store_evidence({"test": "network failure"}, metadata)