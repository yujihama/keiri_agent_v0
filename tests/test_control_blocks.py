"""Control Blocksテスト

承認統制、職務分掌、サンプリングブロックの機能テストを実施します。
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from core.blocks.processing.control.approval import ApprovalBlock
from core.blocks.processing.control.sod_check import SodCheckBlock
from core.blocks.processing.control.sampling import SamplingBlock
from core.errors import BlockExecutionError


class TestApprovalBlock:
    """承認統制ブロックのテスト"""
    
    @pytest.mark.unit
    def test_approval_block_initialization(self):
        """承認ブロック初期化テスト"""
        block = ApprovalBlock()
        assert block is not None
    
    @pytest.mark.unit
    def test_single_level_approval_success(self, block_context, approval_request_data, approval_policy):
        """単一レベル承認成功テスト"""
        block = ApprovalBlock()
        
        # 100万円以下のリクエスト（レベル1承認）
        approval_request_data["amount"] = 500000
        
        inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["approval_result"]["success"] is True
        assert result["approval_result"]["level_required"] == 1
        assert result["approval_result"]["required_approvers"] == 1
        assert len(result["evidence_files"]) > 0
    
    @pytest.mark.unit
    def test_multi_level_approval_required(self, block_context, approval_request_data, approval_policy):
        """多段承認必要テスト"""
        block = ApprovalBlock()
        
        # 100万円超のリクエスト（レベル2承認）
        approval_request_data["amount"] = 2000000
        
        inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["approval_result"]["success"] is True
        assert result["approval_result"]["level_required"] == 2
        assert result["approval_result"]["required_approvers"] == 2
        assert "director" in result["approval_result"]["required_roles"]
        assert "manager" in result["approval_result"]["required_roles"]
    
    @pytest.mark.unit
    def test_approval_escalation(self, block_context, approval_request_data, approval_policy):
        """承認エスカレーションテスト"""
        block = ApprovalBlock()
        
        # タイムアウト設定を短くして即座にエスカレーション
        approval_policy["levels"][0]["timeout_hours"] = 0.001
        
        inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy,
            "current_approvals": []  # 承認なし
        }
        
        result = block.execute(inputs, block_context)
        
        # エスカレーション発生を確認
        assert result["approval_result"]["escalation_required"] is True
        assert "escalation_reason" in result["approval_result"]
    
    @pytest.mark.unit
    def test_approval_timeout_handling(self, block_context, approval_request_data, approval_policy):
        """承認タイムアウト処理テスト"""
        block = ApprovalBlock()
        
        inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy,
            "timeout_action": "escalate"
        }
        
        # タイムアウト発生のシミュレーション
        with patch('core.blocks.processing.control.approval.datetime') as mock_datetime:
            # 48時間後の時刻を設定
            mock_datetime.now.return_value = datetime.now() + timedelta(hours=49)
            
            result = block.execute(inputs, block_context)
            
            assert result["approval_result"]["timeout_occurred"] is True
    
    @pytest.mark.unit
    def test_invalid_approval_request(self, block_context, approval_policy):
        """不正な承認要求の処理テスト"""
        block = ApprovalBlock()
        
        # 必須フィールドが不足している要求
        invalid_request = {
            "request_id": "REQ-001",
            # "requester": "test_user",  # 必須フィールド不足
            "amount": 1000000,
            "description": "テスト申請"
        }
        
        inputs = {
            "approval_request": invalid_request,
            "approval_policy": approval_policy
        }
        
        with pytest.raises(BlockExecutionError):
            block.execute(inputs, block_context)


class TestSodCheckBlock:
    """職務分掌チェックブロックのテスト"""
    
    @pytest.mark.unit
    def test_sod_check_initialization(self):
        """職務分掌ブロック初期化テスト"""
        block = SodCheckBlock()
        assert block is not None
    
    @pytest.mark.unit
    def test_valid_segregation(self, block_context, sample_transaction_data, sod_matrix):
        """適切な職務分掌テスト"""
        block = SodCheckBlock()
        
        # 異なる人物での処理
        sample_transaction_data.update({
            "initiator": "user_a",
            "approver": "user_b",
            "processor": "user_c"
        })
        
        inputs = {
            "transaction_data": sample_transaction_data,
            "sod_matrix": sod_matrix
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sod_result"]["compliant"] is True
        assert len(result["sod_result"]["violations"]) == 0
    
    @pytest.mark.unit
    def test_sod_violation_detection(self, block_context, sample_transaction_data, sod_matrix):
        """職務分掌違反検知テスト"""
        block = SodCheckBlock()
        
        # 同一人物による申請と承認（違反）
        sample_transaction_data.update({
            "initiator": "user_a",
            "approver": "user_a",  # 同一人物
            "processor": "user_b"
        })
        
        inputs = {
            "transaction_data": sample_transaction_data,
            "sod_matrix": sod_matrix
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sod_result"]["compliant"] is False
        assert len(result["sod_result"]["violations"]) > 0
        assert "initiator" in result["sod_result"]["violations"][0]["conflicting_roles"]
        assert "approver" in result["sod_result"]["violations"][0]["conflicting_roles"]
    
    @pytest.mark.unit
    def test_admin_exception_handling(self, block_context, sample_transaction_data, sod_matrix):
        """管理者例外処理テスト"""
        block = SodCheckBlock()
        
        # 管理者による処理（例外適用）
        sample_transaction_data.update({
            "initiator": "admin_user",
            "approver": "admin_user",  # 通常は違反だが管理者例外
            "processor": "admin_user"
        })
        
        inputs = {
            "transaction_data": sample_transaction_data,
            "sod_matrix": sod_matrix,
            "user_roles": {"admin_user": ["admin"]}
        }
        
        result = block.execute(inputs, block_context)
        
        # 管理者例外により違反なしとして処理
        assert result["sod_result"]["compliant"] is True
        assert result["sod_result"]["exception_applied"] is True
    
    @pytest.mark.unit
    def test_complex_role_conflicts(self, block_context, sample_transaction_data):
        """複雑なロール競合テスト"""
        block = SodCheckBlock()
        
        complex_sod_matrix = {
            "incompatible_roles": [
                ["creator", "authorizer"],
                ["requester", "approver"],
                ["maker", "checker"],
                ["buyer", "receiver"]
            ],
            "required_separation": True,
            "exception_roles": []
        }
        
        # 複数の競合を含むデータ
        sample_transaction_data.update({
            "creator": "user_a",
            "authorizer": "user_a",  # 違反1
            "maker": "user_b", 
            "checker": "user_c",    # 適切
            "buyer": "user_a",
            "receiver": "user_a"    # 違反2
        })
        
        inputs = {
            "transaction_data": sample_transaction_data,
            "sod_matrix": complex_sod_matrix
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sod_result"]["compliant"] is False
        assert len(result["sod_result"]["violations"]) == 2  # 2つの違反


class TestSamplingBlock:
    """サンプリングブロックのテスト"""
    
    @pytest.mark.unit
    def test_sampling_block_initialization(self):
        """サンプリングブロック初期化テスト"""
        block = SamplingBlock()
        assert block is not None
    
    @pytest.mark.unit
    def test_statistical_sampling(self, block_context, population_data, sampling_parameters):
        """統計的サンプリングテスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "statistical"
        sampling_parameters["sample_size"] = 25
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sampling_result"]["method_used"] == "statistical"
        assert result["sampling_result"]["sample_size"] == 25
        assert result["sampling_result"]["population_size"] == 100
        assert len(result["selected_items"]) == 25
        assert result["sampling_statistics"]["total_sample_value"] > 0
    
    @pytest.mark.unit
    def test_risk_based_sampling(self, block_context, population_data, sampling_parameters):
        """リスクベースサンプリングテスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "risk_based"
        sampling_parameters["sample_size"] = 30
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sampling_result"]["method_used"] == "risk_based"
        assert len(result["selected_items"]) <= 30
        
        # 高リスクアイテムが多く選択されることを確認
        high_risk_count = sum(1 for item in result["selected_items"] 
                             if item["risk_score"] >= 0.7)
        
        # 高リスクアイテムの選択割合を確認
        total_high_risk = sum(1 for item in population_data["items"] 
                             if item["risk_score"] >= 0.7)
        
        if total_high_risk > 0:
            assert high_risk_count > 0  # 高リスクアイテムが選択されている
    
    @pytest.mark.unit
    def test_systematic_sampling(self, block_context, population_data, sampling_parameters):
        """系統的サンプリングテスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "systematic"
        sampling_parameters["sample_size"] = 20
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sampling_result"]["method_used"] == "systematic"
        assert len(result["selected_items"]) == 20
        
        # 系統的サンプリングの選択理由確認
        selection_reasons = [item["selection_reason"] for item in result["selected_items"]]
        assert all("系統的サンプリング" in reason for reason in selection_reasons)
    
    @pytest.mark.unit
    def test_random_sampling(self, block_context, population_data, sampling_parameters):
        """ランダムサンプリングテスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "random"
        sampling_parameters["sample_size"] = 15
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sampling_result"]["method_used"] == "random"
        assert len(result["selected_items"]) == 15
        assert result["sampling_statistics"]["value_coverage_ratio"] > 0
    
    @pytest.mark.unit
    def test_sample_size_calculation(self, block_context, population_data, sampling_parameters):
        """サンプルサイズ自動計算テスト"""
        block = SamplingBlock()
        
        # サンプルサイズを指定せず、統計的に計算
        sampling_parameters["method"] = "statistical"
        sampling_parameters["sample_size"] = None
        sampling_parameters["confidence_level"] = 0.95
        sampling_parameters["tolerable_error_rate"] = 0.05
        sampling_parameters["expected_error_rate"] = 0.02
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        # 自動計算されたサンプルサイズが適切な範囲にあることを確認
        sample_size = result["sampling_result"]["sample_size"]
        assert 10 <= sample_size <= 100  # 現実的な範囲
        assert result["sampling_result"]["confidence_level"] == 0.95
    
    @pytest.mark.unit
    def test_sampling_statistics_calculation(self, block_context, population_data, sampling_parameters):
        """サンプリング統計計算テスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "random"
        sampling_parameters["sample_size"] = 10
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        stats = result["sampling_statistics"]
        
        # 統計値の妥当性確認
        assert stats["total_sample_value"] > 0
        assert stats["average_item_value"] > 0
        assert 0 <= stats["value_coverage_ratio"] <= 1
        
        # リスク分布確認
        risk_dist = stats["risk_distribution"]
        total_risk_count = (risk_dist["high_risk_count"] + 
                           risk_dist["medium_risk_count"] + 
                           risk_dist["low_risk_count"])
        assert total_risk_count == 10  # サンプルサイズと一致
    
    @pytest.mark.unit
    def test_empty_population_handling(self, block_context, sampling_parameters):
        """空の母集団処理テスト"""
        block = SamplingBlock()
        
        empty_population = {
            "data_source": "empty_test",
            "total_items": 0,
            "total_value": 0,
            "items": []
        }
        
        inputs = {
            "population_data": empty_population,
            "sampling_parameters": sampling_parameters
        }
        
        result = block.execute(inputs, block_context)
        
        assert result["sampling_result"]["sample_size"] == 0
        assert len(result["selected_items"]) == 0
        assert result["sampling_statistics"]["total_sample_value"] == 0
    
    @pytest.mark.unit
    def test_invalid_sampling_method(self, block_context, population_data, sampling_parameters):
        """不正なサンプリング手法処理テスト"""
        block = SamplingBlock()
        
        sampling_parameters["method"] = "invalid_method"
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        with pytest.raises(BlockExecutionError):
            block.execute(inputs, block_context)


class TestControlBlocksIntegration:
    """Control Blocks統合テスト"""
    
    @pytest.mark.integration
    def test_approval_to_sod_workflow(self, block_context, approval_request_data, 
                                    approval_policy, sod_matrix):
        """承認から職務分掌チェックのワークフローテスト"""
        approval_block = ApprovalBlock()
        sod_block = SodCheckBlock()
        
        # 1. 承認処理
        approval_inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy
        }
        
        approval_result = approval_block.execute(approval_inputs, block_context)
        
        # 2. 承認結果を職務分掌チェックに連携
        transaction_data = {
            "transaction_id": approval_request_data["request_id"],
            "amount": approval_request_data["amount"],
            "initiator": approval_request_data["requester"],
            "approver": "different_user",  # 適切な分掌
            "approval_level": approval_result["approval_result"]["level_required"]
        }
        
        sod_inputs = {
            "transaction_data": transaction_data,
            "sod_matrix": sod_matrix
        }
        
        sod_result = sod_block.execute(sod_inputs, block_context)
        
        # 統合結果の検証
        assert approval_result["approval_result"]["success"] is True
        assert sod_result["sod_result"]["compliant"] is True
    
    @pytest.mark.integration
    def test_control_blocks_with_evidence_vault(self, block_context, evidence_vault, 
                                               population_data, sampling_parameters):
        """Evidence Vault連携統合テスト"""
        sampling_block = SamplingBlock()
        
        # Evidence Vaultをコンテキストに設定
        block_context.evidence_vault = evidence_vault
        
        inputs = {
            "population_data": population_data,
            "sampling_parameters": sampling_parameters
        }
        
        result = sampling_block.execute(inputs, block_context)
        
        # 証跡ファイルが生成されていることを確認
        assert len(result["evidence_files"]) > 0
        
        # Evidence Vaultに証跡が保存されていることを確認
        evidence_files = result["evidence_files"]
        for evidence_file in evidence_files:
            if evidence_file.startswith("vault:"):
                evidence_id = evidence_file.replace("vault:", "")
                # 証跡が取得できることを確認
                stored_data = evidence_vault.retrieve_evidence(evidence_id)
                assert stored_data is not None
    
    @pytest.mark.audit
    def test_complete_audit_trail(self, block_context, evidence_vault, 
                                 approval_request_data, approval_policy):
        """完全な監査証跡テスト"""
        approval_block = ApprovalBlock()
        block_context.evidence_vault = evidence_vault
        
        inputs = {
            "approval_request": approval_request_data,
            "approval_policy": approval_policy
        }
        
        result = approval_block.execute(inputs, block_context)
        
        # 監査証跡の確認
        evidence_files = result["evidence_files"]
        assert len(evidence_files) > 0
        
        # 各証跡ファイルの内容検証
        for evidence_file in evidence_files:
            if evidence_file.startswith("vault:"):
                evidence_id = evidence_file.replace("vault:", "")
                stored_data = evidence_vault.retrieve_evidence(evidence_id)
                
                # 必要な監査情報が含まれていることを確認
                assert "approval_result" in stored_data or "approval_request" in stored_data
                
                # 監査証跡の確認
                audit_trail = evidence_vault.get_audit_trail(evidence_id)
                assert len(audit_trail) >= 1
                assert audit_trail[0].action == "stored"