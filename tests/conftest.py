"""pytest共通設定とフィクスチャ

監査・内部統制機能のテストで使用する共通のフィクスチャとセットアップを定義します。
"""

import pytest
import tempfile
import shutil
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType
from core.policy.engine import PolicyEngine
from core.policy.models import Policy, PolicyRule, PolicyType, RuleSeverity
from core.blocks.base import BlockContext


@pytest.fixture(scope="session")
def temp_workspace():
    """テスト用の一時ワークスペース"""
    temp_dir = tempfile.mkdtemp(prefix="keiri_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def evidence_vault(temp_workspace):
    """テスト用Evidence Vault"""
    vault_path = os.path.join(temp_workspace, "evidence_vault")
    return EvidenceVault(vault_path, encryption_password="test_password_123")


@pytest.fixture
def policy_engine(temp_workspace, evidence_vault):
    """テスト用Policy Engine"""
    policy_dir = os.path.join(temp_workspace, "policies")
    return PolicyEngine(policy_dir, evidence_vault)


@pytest.fixture
def sample_policy():
    """サンプルポリシー"""
    return Policy(
        name="テスト購買ポリシー",
        description="テスト用の購買承認ポリシー",
        policy_type=PolicyType.COMPLIANCE,
        rules=[
            PolicyRule(
                name="高額承認必須",
                description="100万円以上は部長承認必要",
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
                name="職務分掌チェック",
                description="申請者と承認者は別人",
                rule_type="segregation_duty",
                expression="initiator != approver",
                severity=RuleSeverity.CRITICAL
            )
        ]
    )


@pytest.fixture
def sample_evidence_metadata():
    """サンプル証跡メタデータ"""
    return EvidenceMetadata(
        evidence_id="test_evidence_001",
        evidence_type=EvidenceType.CONTROL_RESULT,
        block_id="test_block",
        run_id="test_run_001",
        timestamp=datetime.now(),
        file_path="test/evidence/test_evidence_001.json",
        file_hash="test_hash",
        file_size=1024,
        retention_until=datetime.now() + timedelta(days=2555),
        tags=["test", "control", "audit"],
        department="テスト部署"
    )


@pytest.fixture
def sample_transaction_data():
    """サンプル取引データ"""
    return {
        "transaction_id": "TXN-001",
        "amount": 1500000,
        "initiator": "user_a",
        "approver": "user_b",
        "approval_status": "pending",
        "department": "購買部",
        "description": "テスト購買申請"
    }


@pytest.fixture
def block_context(temp_workspace):
    """テスト用ブロックコンテキスト"""
    return BlockContext(
        run_id="test_run_001",
        workspace=temp_workspace,
        user="test_user",
        department="テスト部署"
    )


@pytest.fixture
def approval_request_data():
    """承認要求データ"""
    return {
        "request_id": "REQ-001",
        "requester": "test_user",
        "amount": 1500000,
        "description": "テスト購買申請",
        "attachments": []
    }


@pytest.fixture
def approval_policy():
    """承認ポリシー"""
    return {
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


@pytest.fixture
def sod_matrix():
    """職務分掌マトリクス"""
    return {
        "incompatible_roles": [
            ["requester", "approver"],
            ["creator", "authorizer"],
            ["initiator", "reviewer"]
        ],
        "required_separation": True,
        "exception_roles": ["admin"]
    }


@pytest.fixture
def population_data():
    """サンプリング用母集団データ"""
    return {
        "data_source": "test_transactions",
        "total_items": 100,
        "total_value": 50000000,
        "items": [
            {
                "item_id": f"ITEM-{i:03d}",
                "value": 500000 + (i * 10000),
                "risk_score": 0.1 + (i % 10) * 0.1,
                "attributes": {
                    "department": "購買部" if i % 2 == 0 else "財務部",
                    "category": "A" if i < 30 else "B" if i < 70 else "C"
                }
            }
            for i in range(100)
        ]
    }


@pytest.fixture
def sampling_parameters():
    """サンプリングパラメータ"""
    return {
        "method": "statistical",
        "confidence_level": 0.95,
        "tolerable_error_rate": 0.05,
        "expected_error_rate": 0.02,
        "sample_size": None,
        "stratification": {
            "enabled": False
        },
        "risk_criteria": {
            "high_risk_threshold": 0.7,
            "medium_risk_threshold": 0.3,
            "high_risk_percentage": 0.8
        }
    }


# テスト用ヘルパー関数
def create_test_evidence(evidence_vault: EvidenceVault, 
                        evidence_type: EvidenceType = EvidenceType.CONTROL_RESULT,
                        data: Dict[str, Any] = None) -> str:
    """テスト用証跡を作成"""
    if data is None:
        data = {"test": "data", "timestamp": datetime.now().isoformat()}
    
    metadata = EvidenceMetadata(
        evidence_id=f"test_{datetime.now().timestamp()}",
        evidence_type=evidence_type,
        block_id="test_block",
        run_id="test_run",
        timestamp=datetime.now(),
        file_path=f"test/evidence_{evidence_type.value}.json",
        file_hash="test_hash",
        file_size=len(str(data)),
        retention_until=datetime.now() + timedelta(days=2555),
        tags=["test"]
    )
    
    return evidence_vault.store_evidence(data, metadata)


# マーカー設定
pytest_plugins = []