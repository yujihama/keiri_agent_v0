"""Evidence Vaultテスト

Evidence Vaultの暗号化、メタデータ管理、証跡保存・取得機能のテストを実施します。
"""

import pytest
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType, AuditTrailEntry
from core.evidence.encryption import EncryptionManager
from core.errors import BlockExecutionError


class TestEncryptionManager:
    """暗号化マネージャーのテスト"""
    
    @pytest.mark.unit
    def test_encryption_manager_initialization(self):
        """暗号化マネージャーの初期化テスト"""
        # パスワード指定あり
        em = EncryptionManager("test_password")
        assert em.encryption_key is not None
        assert em.cipher is not None
        
        # パスワード指定なし（自動生成）
        em_auto = EncryptionManager()
        assert em_auto.encryption_key is not None
        assert em_auto.cipher is not None
    
    @pytest.mark.unit
    def test_encrypt_decrypt_roundtrip(self):
        """暗号化・復号化の往復テスト"""
        em = EncryptionManager("test_password")
        test_data = {"message": "テスト暗号化データ", "number": 12345}
        
        # 暗号化
        encrypted_data = em.encrypt(test_data)
        assert encrypted_data != test_data
        assert isinstance(encrypted_data, bytes)
        
        # 復号化
        decrypted_data = em.decrypt(encrypted_data)
        assert decrypted_data == test_data
    
    @pytest.mark.unit
    def test_verify_integrity(self):
        """データ整合性検証テスト"""
        em = EncryptionManager("test_password")
        test_data = {"test": "integrity check"}
        
        encrypted_data = em.encrypt(test_data)
        
        # 正常データの検証
        assert em.verify_integrity(test_data, encrypted_data) is True
        
        # 改ざんデータの検証
        tampered_data = {"test": "tampered data"}
        assert em.verify_integrity(tampered_data, encrypted_data) is False
    
    @pytest.mark.unit
    def test_invalid_data_handling(self):
        """不正データの処理テスト"""
        em = EncryptionManager("test_password")
        
        # 不正な暗号化データ
        with pytest.raises(Exception):
            em.decrypt(b"invalid_encrypted_data")
        
        # 空データ
        with pytest.raises(ValueError):
            em.encrypt("")


class TestEvidenceVault:
    """Evidence Vaultのテスト"""
    
    @pytest.mark.unit
    def test_vault_initialization(self, evidence_vault):
        """Evidence Vault初期化テスト"""
        assert evidence_vault.vault_path.exists()
        assert evidence_vault.encryption_manager is not None
        assert os.path.exists(evidence_vault.metadata_db)
    
    @pytest.mark.unit
    def test_store_evidence(self, evidence_vault, sample_evidence_metadata):
        """証跡保存テスト"""
        test_data = {
            "transaction_id": "TXN-001",
            "amount": 1000000,
            "timestamp": datetime.now().isoformat()
        }
        
        evidence_id = evidence_vault.store_evidence(test_data, sample_evidence_metadata)
        
        assert evidence_id == sample_evidence_metadata.evidence_id
        assert evidence_vault.vault_path.joinpath(sample_evidence_metadata.file_path).exists()
    
    @pytest.mark.unit
    def test_retrieve_evidence(self, evidence_vault, sample_evidence_metadata):
        """証跡取得テスト"""
        test_data = {
            "test": "retrieve data",
            "value": 999
        }
        
        # 保存
        evidence_vault.store_evidence(test_data, sample_evidence_metadata)
        
        # 取得
        retrieved_data = evidence_vault.retrieve_evidence(sample_evidence_metadata.evidence_id)
        
        assert retrieved_data == test_data
    
    @pytest.mark.unit
    def test_search_evidence(self, evidence_vault):
        """証跡検索テスト"""
        # テストデータの作成
        for i in range(5):
            metadata = EvidenceMetadata(
                evidence_id=f"test_evidence_{i}",
                evidence_type=EvidenceType.CONTROL_RESULT,
                block_id="test_block",
                run_id=f"run_{i}",
                timestamp=datetime.now() - timedelta(days=i),
                file_path=f"test/evidence_{i}.json",
                file_hash=f"hash_{i}",
                file_size=1024,
                retention_until=datetime.now() + timedelta(days=2555),
                tags=["test", f"tag_{i}"],
                department="テスト部署" if i % 2 == 0 else "別部署"
            )
            evidence_vault.store_evidence({"data": f"test_{i}"}, metadata)
        
        # 全件検索
        all_evidence = evidence_vault.search_evidence({})
        assert len(all_evidence) == 5
        
        # 証跡タイプ検索
        control_evidence = evidence_vault.search_evidence({
            "evidence_type": EvidenceType.CONTROL_RESULT
        })
        assert len(control_evidence) == 5
        
        # 部署検索
        dept_evidence = evidence_vault.search_evidence({
            "department": "テスト部署"
        })
        assert len(dept_evidence) == 3  # 偶数インデックス
        
        # 日付範囲検索
        recent_evidence = evidence_vault.search_evidence({
            "date_from": datetime.now() - timedelta(days=2)
        })
        assert len(recent_evidence) >= 2
    
    @pytest.mark.unit
    def test_delete_evidence(self, evidence_vault, sample_evidence_metadata):
        """証跡削除テスト"""
        test_data = {"test": "delete me"}
        
        # 保存
        evidence_vault.store_evidence(test_data, sample_evidence_metadata)
        
        # 削除
        success = evidence_vault.delete_evidence(sample_evidence_metadata.evidence_id)
        assert success is True
        
        # 削除確認
        with pytest.raises(FileNotFoundError):
            evidence_vault.retrieve_evidence(sample_evidence_metadata.evidence_id)
    
    @pytest.mark.unit
    def test_get_statistics(self, evidence_vault):
        """統計取得テスト"""
        # テストデータ作成
        for i in range(3):
            metadata = EvidenceMetadata(
                evidence_id=f"stats_test_{i}",
                evidence_type=EvidenceType.CONTROL_RESULT,
                block_id="test_block",
                run_id=f"run_{i}",
                timestamp=datetime.now(),
                file_path=f"test/stats_{i}.json",
                file_hash=f"hash_{i}",
                file_size=1024 * (i + 1),
                retention_until=datetime.now() + timedelta(days=2555),
                tags=["stats_test"]
            )
            evidence_vault.store_evidence({"data": f"stats_{i}"}, metadata)
        
        stats = evidence_vault.get_statistics()
        
        assert stats.total_evidence_count >= 3
        assert stats.total_data_size_mb > 0
        assert stats.today_evidence_count >= 3
        assert stats.retention_days_remaining > 0
    
    @pytest.mark.unit
    def test_audit_trail_creation(self, evidence_vault, sample_evidence_metadata):
        """監査証跡作成テスト"""
        test_data = {"test": "audit trail"}
        
        # 保存（監査証跡が自動作成される）
        evidence_vault.store_evidence(test_data, sample_evidence_metadata)
        
        # 監査証跡確認
        audit_trail = evidence_vault.get_audit_trail(sample_evidence_metadata.evidence_id)
        
        assert len(audit_trail) >= 1
        assert audit_trail[0].action == "stored"
        assert audit_trail[0].evidence_id == sample_evidence_metadata.evidence_id
    
    @pytest.mark.security
    def test_encryption_in_storage(self, evidence_vault, sample_evidence_metadata):
        """保存時暗号化テスト"""
        sensitive_data = {
            "personal_info": "機密情報",
            "amount": 5000000,
            "account": "1234-567-890"
        }
        
        evidence_vault.store_evidence(sensitive_data, sample_evidence_metadata)
        
        # ファイルが暗号化されていることを確認
        file_path = evidence_vault.vault_path / sample_evidence_metadata.file_path
        with open(file_path, 'rb') as f:
            raw_content = f.read()
        
        # 生データには機密情報が含まれていないことを確認
        assert b"機密情報" not in raw_content
        assert b"1234-567-890" not in raw_content
        
        # 正常に復号化できることを確認
        retrieved_data = evidence_vault.retrieve_evidence(sample_evidence_metadata.evidence_id)
        assert retrieved_data == sensitive_data
    
    @pytest.mark.unit
    def test_evidence_with_context(self, evidence_vault):
        """コンテキスト付き証跡保存テスト"""
        with evidence_vault.evidence_context(
            block_id="test_block",
            run_id="test_run",
            department="テスト部署"
        ):
            evidence_id = evidence_vault.store_evidence_simple(
                {"context_test": "data"},
                EvidenceType.CONTROL_RESULT,
                tags=["context_test"]
            )
        
        # コンテキスト情報が正しく保存されていることを確認
        evidence_list = evidence_vault.search_evidence({
            "run_id": "test_run",
            "department": "テスト部署"
        })
        
        assert len(evidence_list) == 1
        assert evidence_list[0].evidence_id == evidence_id
        assert evidence_list[0].block_id == "test_block"
    
    @pytest.mark.slow
    def test_large_data_handling(self, evidence_vault):
        """大容量データ処理テスト"""
        # 大きなデータセットを作成
        large_data = {
            "records": [{"id": i, "data": f"record_{i}" * 100} for i in range(1000)]
        }
        
        metadata = EvidenceMetadata(
            evidence_id="large_data_test",
            evidence_type=EvidenceType.INPUT,
            block_id="test_block",
            run_id="large_test",
            timestamp=datetime.now(),
            file_path="test/large_data.json",
            file_hash="large_hash",
            file_size=len(json.dumps(large_data)),
            retention_until=datetime.now() + timedelta(days=2555),
            tags=["large_data"]
        )
        
        # 保存
        evidence_vault.store_evidence(large_data, metadata)
        
        # 取得
        retrieved_data = evidence_vault.retrieve_evidence("large_data_test")
        
        assert retrieved_data == large_data
        assert len(retrieved_data["records"]) == 1000
    
    @pytest.mark.unit
    def test_concurrent_access(self, evidence_vault):
        """並行アクセステスト"""
        import threading
        import time
        
        results = []
        errors = []
        
        def store_evidence(thread_id):
            try:
                data = {"thread_id": thread_id, "timestamp": time.time()}
                metadata = EvidenceMetadata(
                    evidence_id=f"concurrent_test_{thread_id}",
                    evidence_type=EvidenceType.CONTROL_RESULT,
                    block_id="concurrent_test",
                    run_id=f"concurrent_run_{thread_id}",
                    timestamp=datetime.now(),
                    file_path=f"test/concurrent_{thread_id}.json",
                    file_hash=f"hash_{thread_id}",
                    file_size=100,
                    retention_until=datetime.now() + timedelta(days=2555),
                    tags=["concurrent"]
                )
                
                evidence_vault.store_evidence(data, metadata)
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, str(e)))
        
        # 複数スレッドで同時実行
        threads = []
        for i in range(5):
            thread = threading.Thread(target=store_evidence, args=(i,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # エラーがないことを確認
        assert len(errors) == 0, f"並行アクセスエラー: {errors}"
        assert len(results) == 5
        
        # 保存されたデータを確認
        concurrent_evidence = evidence_vault.search_evidence({"tags": ["concurrent"]})
        assert len(concurrent_evidence) == 5


class TestEvidenceIntegration:
    """Evidence Vault統合テスト"""
    
    @pytest.mark.integration
    def test_end_to_end_workflow(self, evidence_vault):
        """エンドツーエンド ワークフローテスト"""
        # 1. 入力データ保存
        input_data = {"input": "original data", "step": 1}
        input_metadata = EvidenceMetadata(
            evidence_id="e2e_input",
            evidence_type=EvidenceType.INPUT,
            block_id="e2e_test",
            run_id="e2e_run",
            timestamp=datetime.now(),
            file_path="e2e/input.json",
            file_hash="input_hash",
            file_size=100,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=["e2e", "input"]
        )
        evidence_vault.store_evidence(input_data, input_metadata)
        
        # 2. 中間処理結果保存
        intermediate_data = {"processed": "intermediate result", "step": 2}
        intermediate_metadata = EvidenceMetadata(
            evidence_id="e2e_intermediate",
            evidence_type=EvidenceType.INTERMEDIATE,
            block_id="e2e_test",
            run_id="e2e_run",
            timestamp=datetime.now(),
            file_path="e2e/intermediate.json",
            file_hash="intermediate_hash",
            file_size=150,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=["e2e", "intermediate"]
        )
        evidence_vault.store_evidence(intermediate_data, intermediate_metadata)
        
        # 3. 最終結果保存
        output_data = {"output": "final result", "step": 3}
        output_metadata = EvidenceMetadata(
            evidence_id="e2e_output",
            evidence_type=EvidenceType.OUTPUT,
            block_id="e2e_test",
            run_id="e2e_run",
            timestamp=datetime.now(),
            file_path="e2e/output.json",
            file_hash="output_hash",
            file_size=120,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=["e2e", "output"]
        )
        evidence_vault.store_evidence(output_data, output_metadata)
        
        # 4. 全体検索・検証
        e2e_evidence = evidence_vault.search_evidence({"run_id": "e2e_run"})
        assert len(e2e_evidence) == 3
        
        # 5. 各段階のデータ検証
        retrieved_input = evidence_vault.retrieve_evidence("e2e_input")
        retrieved_intermediate = evidence_vault.retrieve_evidence("e2e_intermediate")
        retrieved_output = evidence_vault.retrieve_evidence("e2e_output")
        
        assert retrieved_input == input_data
        assert retrieved_intermediate == intermediate_data
        assert retrieved_output == output_data
        
        # 6. 監査証跡確認
        for evidence_id in ["e2e_input", "e2e_intermediate", "e2e_output"]:
            audit_trail = evidence_vault.get_audit_trail(evidence_id)
            assert len(audit_trail) >= 1
            assert audit_trail[0].action == "stored"