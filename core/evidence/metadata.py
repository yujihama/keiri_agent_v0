"""証跡メタデータ管理

Evidence Vaultで使用する各種メタデータモデルを定義します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class EvidenceType(str, Enum):
    """証跡タイプ"""
    INPUT = "input"
    OUTPUT = "output" 
    INTERMEDIATE = "intermediate"
    CONTROL_RESULT = "control_result"
    AUDIT_FINDING = "audit_finding"
    DOCUMENT = "document"
    CALCULATION = "calculation"
    APPROVAL_RECORD = "approval_record"


class EventType(str, Enum):
    """監査証跡イベントタイプ"""
    BLOCK_START = "block_start"
    BLOCK_END = "block_end"
    DATA_TRANSFORM = "data_transform"
    CONTROL_CHECK = "control_check"
    POLICY_VALIDATION = "policy_validation"
    EVIDENCE_STORE = "evidence_store"
    EVIDENCE_RETRIEVE = "evidence_retrieve"


class ExecutionStatus(str, Enum):
    """実行ステータス"""
    STARTED = "started"
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    CANCELLED = "cancelled"


class EvidenceMetadata(BaseModel):
    """証跡メタデータ"""
    
    evidence_id: str = Field(..., description="証跡ID")
    evidence_type: EvidenceType = Field(..., description="証跡タイプ")
    block_id: str = Field(..., description="ブロックID")
    run_id: str = Field(..., description="実行ID")
    timestamp: datetime = Field(..., description="作成日時")
    file_path: str = Field(..., description="ファイルパス")
    file_hash: str = Field("", description="ファイルハッシュ（SHA256）")
    file_size: int = Field(0, description="ファイルサイズ（バイト）")
    encryption_key_id: Optional[str] = Field(None, description="暗号化キーID")
    retention_until: datetime = Field(..., description="保存期限")
    tags: List[str] = Field(default_factory=list, description="検索用タグ")
    related_evidence: List[str] = Field(default_factory=list, description="関連証跡ID")
    
    # 追加メタデータ
    creator_user_id: Optional[str] = Field(None, description="作成者ユーザーID")
    department: Optional[str] = Field(None, description="部門")
    risk_level: Optional[str] = Field(None, description="リスクレベル")
    compliance_flags: List[str] = Field(default_factory=list, description="コンプライアンスフラグ")
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """ファイルパスの検証"""
        if not v or not isinstance(v, str):
            raise ValueError("ファイルパスは必須です")
        return v
    
    @validator('tags', pre=True)
    def validate_tags(cls, v):
        """タグの検証・正規化"""
        if v is None:
            return []
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(',') if tag.strip()]
        return v


class AuditTrailEntry(BaseModel):
    """監査証跡エントリ"""
    
    entry_id: str = Field(..., description="エントリID")
    timestamp: datetime = Field(..., description="発生日時")
    event_type: EventType = Field(..., description="イベントタイプ")
    block_id: str = Field(..., description="ブロックID")
    run_id: str = Field(..., description="実行ID")
    user_id: Optional[str] = Field(None, description="ユーザーID")
    
    # 実行情報
    inputs: Dict[str, Any] = Field(default_factory=dict, description="入力データ")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="出力データ")
    execution_time_ms: int = Field(0, description="実行時間（ミリ秒）")
    status: ExecutionStatus = Field(..., description="実行ステータス")
    error_details: Optional[str] = Field(None, description="エラー詳細")
    
    # セキュリティ情報
    signature: Optional[str] = Field(None, description="デジタル署名")
    previous_entry_hash: Optional[str] = Field(None, description="前エントリのハッシュ")
    
    # 監査情報
    session_id: Optional[str] = Field(None, description="セッションID")
    ip_address: Optional[str] = Field(None, description="IPアドレス")
    user_agent: Optional[str] = Field(None, description="ユーザーエージェント")
    
    @validator('execution_time_ms')
    def validate_execution_time(cls, v):
        """実行時間の検証"""
        if v < 0:
            raise ValueError("実行時間は0以上である必要があります")
        return v


class DataLineageNode(BaseModel):
    """データ系譜ノード"""
    
    node_id: str = Field(..., description="ノードID")
    node_type: str = Field(..., description="ノードタイプ（source/transform/sink）")
    block_id: str = Field(..., description="ブロックID")
    data_hash: str = Field(..., description="データハッシュ")
    parent_nodes: List[str] = Field(default_factory=list, description="親ノードID")
    child_nodes: List[str] = Field(default_factory=list, description="子ノードID")
    transformation_details: Dict[str, Any] = Field(default_factory=dict, description="変換詳細")
    
    # 系譜追跡情報
    created_at: datetime = Field(default_factory=datetime.now, description="作成日時")
    data_size: Optional[int] = Field(None, description="データサイズ")
    data_format: Optional[str] = Field(None, description="データ形式")
    quality_score: Optional[float] = Field(None, description="データ品質スコア")
    
    @validator('quality_score')
    def validate_quality_score(cls, v):
        """品質スコアの検証"""
        if v is not None and (v < 0 or v > 100):
            raise ValueError("品質スコアは0-100の範囲である必要があります")
        return v


class VaultStatistics(BaseModel):
    """Vault統計情報"""
    
    total_evidence_count: int = Field(0, description="総証跡数")
    total_storage_size: int = Field(0, description="総ストレージサイズ（バイト）")
    evidence_by_type: Dict[str, int] = Field(default_factory=dict, description="タイプ別証跡数")
    oldest_evidence_date: Optional[datetime] = Field(None, description="最古証跡日時")
    newest_evidence_date: Optional[datetime] = Field(None, description="最新証跡日時")
    
    # 統計期間
    statistics_date: datetime = Field(default_factory=datetime.now, description="統計作成日時")
    period_start: Optional[datetime] = Field(None, description="統計期間開始")
    period_end: Optional[datetime] = Field(None, description="統計期間終了")
    
    # 品質指標
    integrity_check_pass_rate: float = Field(100.0, description="整合性チェック合格率")
    encryption_coverage_rate: float = Field(100.0, description="暗号化カバー率")
    backup_coverage_rate: float = Field(0.0, description="バックアップカバー率")


class RetentionPolicy(BaseModel):
    """保存ポリシー"""
    
    policy_id: str = Field(..., description="ポリシーID")
    policy_name: str = Field(..., description="ポリシー名")
    default_retention_days: int = Field(2555, description="デフォルト保存期間（日）")
    
    # タイプ別保存期間
    retention_by_type: Dict[EvidenceType, int] = Field(default_factory=dict, description="タイプ別保存期間")
    
    # 特別保存ルール
    permanent_retention_tags: List[str] = Field(default_factory=list, description="永久保存タグ")
    extended_retention_rules: List[Dict[str, Any]] = Field(default_factory=list, description="延長保存ルール")
    
    # 削除設定
    auto_deletion_enabled: bool = Field(True, description="自動削除有効化")
    deletion_grace_period_days: int = Field(30, description="削除猶予期間（日）")
    
    @validator('default_retention_days')
    def validate_retention_days(cls, v):
        """保存期間の検証"""
        if v < 1:
            raise ValueError("保存期間は1日以上である必要があります")
        return v