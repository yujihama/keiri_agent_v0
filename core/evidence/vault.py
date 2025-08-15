"""Evidence Vault メインクラス

完全な監査証跡管理を提供するEvidenceVaultの核となる実装。
暗号化・改ざん検知機能付きで証跡を永続保存し、監査人や規制当局への透明性を確保します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json
import uuid
import os
import logging
from contextlib import contextmanager

from .metadata import (
    EvidenceMetadata, AuditTrailEntry, DataLineageNode, VaultStatistics,
    EvidenceType, EventType, ExecutionStatus
)
from .encryption import EncryptionManager
from core.errors import BlockExecutionError

# ロガー設定
logger = logging.getLogger(__name__)


class EvidenceVault:
    """Evidence Vault メインクラス"""
    
    def __init__(self, vault_path: str, encryption_password: str = None):
        """
        Evidence Vaultの初期化
        
        Args:
            vault_path: Vaultのルートパス
            encryption_password: 暗号化パスワード（指定しない場合は自動生成）
        """
        self.vault_path = Path(vault_path)
        self.encryption_manager = EncryptionManager(encryption_password)
        self._ensure_vault_structure()
        self._initialize_index()
        
        logger.info(f"Evidence Vault initialized at {self.vault_path}")
    
    def _ensure_vault_structure(self):
        """Vault ディレクトリ構造の確保"""
        directories = [
            'evidence/raw',
            'evidence/processed', 
            'evidence/outputs',
            'evidence/metadata',
            'audit_trail',
            'signatures',
            'lineage',
            'statistics',
            'backups',
            'temp'
        ]
        
        for directory in directories:
            dir_path = self.vault_path / directory
            dir_path.mkdir(parents=True, exist_ok=True)
            
            # .gitkeepファイルを作成（空ディレクトリの保持用）
            gitkeep_file = dir_path / '.gitkeep'
            if not gitkeep_file.exists():
                gitkeep_file.touch()
    
    def _initialize_index(self):
        """Vaultインデックスの初期化"""
        index_file = self.vault_path / 'vault_index.json'
        
        if not index_file.exists():
            initial_index = {
                'created_at': datetime.now().isoformat(),
                'version': '1.0.0',
                'evidence_count': 0,
                'last_evidence_id': None,
                'last_updated': datetime.now().isoformat(),
                'encryption_enabled': True,
                'statistics': {
                    'total_size_bytes': 0,
                    'evidence_by_type': {}
                }
            }
            
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(initial_index, f, ensure_ascii=False, indent=2)
    
    def store_evidence(self, evidence_data: Union[str, bytes, Dict[str, Any]], 
                      metadata: EvidenceMetadata) -> str:
        """
        証跡データの保存
        
        Args:
            evidence_data: 保存する証跡データ
            metadata: 証跡メタデータ
            
        Returns:
            保存された証跡のID
            
        Raises:
            BlockExecutionError: 保存処理でエラーが発生した場合
        """
        try:
            # ファイルパス生成
            evidence_file = self.vault_path / metadata.file_path
            evidence_file.parent.mkdir(parents=True, exist_ok=True)
            
            # データの前処理
            if isinstance(evidence_data, dict):
                data_bytes = json.dumps(evidence_data, ensure_ascii=False, indent=2).encode('utf-8')
            elif isinstance(evidence_data, str):
                data_bytes = evidence_data.encode('utf-8')
            else:
                data_bytes = evidence_data
            
            # ハッシュ計算（暗号化前）
            metadata.file_hash = self.encryption_manager.calculate_hash(data_bytes)
            metadata.file_size = len(data_bytes)
            
            # データの暗号化と保存
            encrypted_data = self.encryption_manager.encrypt(data_bytes)
            
            with open(evidence_file, 'wb') as f:
                f.write(encrypted_data)
            
            # メタデータ保存
            self._save_metadata(metadata)
            
            # インデックス更新
            self._update_vault_index(metadata)
            
            # 監査証跡記録
            self._log_evidence_operation('store', metadata.evidence_id, metadata.block_id)
            
            logger.info(f"Evidence stored successfully: {metadata.evidence_id}")
            return metadata.evidence_id
            
        except Exception as e:
            logger.error(f"Failed to store evidence {metadata.evidence_id}: {str(e)}")
            raise BlockExecutionError(f"証跡保存エラー: {str(e)}")
    
    def retrieve_evidence(self, evidence_id: str, verify_integrity: bool = True) -> Tuple[Any, EvidenceMetadata]:
        """
        証跡データの取得
        
        Args:
            evidence_id: 取得する証跡ID
            verify_integrity: 整合性検証の実行フラグ
            
        Returns:
            (証跡データ, メタデータ)のタプル
            
        Raises:
            BlockExecutionError: 取得処理でエラーが発生した場合
        """
        try:
            # メタデータ読み込み
            metadata = self._load_metadata(evidence_id)
            
            # データ読み込みと復号化
            evidence_file = self.vault_path / metadata.file_path
            
            if not evidence_file.exists():
                raise FileNotFoundError(f"証跡ファイルが見つかりません: {evidence_file}")
            
            with open(evidence_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.encryption_manager.decrypt(encrypted_data)
            
            # 整合性検証
            if verify_integrity:
                current_hash = self.encryption_manager.calculate_hash(decrypted_data)
                if current_hash != metadata.file_hash:
                    raise BlockExecutionError(f"データ改ざんを検出: {evidence_id}")
            
            # データ形式の復元
            try:
                data = json.loads(decrypted_data.decode('utf-8'))
            except json.JSONDecodeError:
                data = decrypted_data.decode('utf-8')
            except UnicodeDecodeError:
                # バイナリデータの場合はそのまま返す
                data = decrypted_data
            
            # 監査証跡記録
            self._log_evidence_operation('retrieve', evidence_id, metadata.block_id)
            
            logger.info(f"Evidence retrieved successfully: {evidence_id}")
            return data, metadata
            
        except Exception as e:
            logger.error(f"Failed to retrieve evidence {evidence_id}: {str(e)}")
            raise BlockExecutionError(f"証跡取得エラー: {str(e)}")
    
    def search_evidence(self, criteria: Dict[str, Any], limit: int = 100) -> List[Dict[str, Any]]:
        """
        証跡の検索
        
        Args:
            criteria: 検索条件
            limit: 取得件数上限
            
        Returns:
            検索結果のリスト
        """
        try:
            results = []
            metadata_dir = self.vault_path / 'evidence/metadata'
            
            if not metadata_dir.exists():
                return results
            
            # メタデータファイルを走査
            for metadata_file in metadata_dir.glob('*.json'):
                if len(results) >= limit:
                    break
                
                try:
                    metadata = self._load_metadata_from_file(metadata_file)
                    
                    # 検索条件のマッチング
                    if self._matches_criteria(metadata, criteria):
                        relevance_score = self._calculate_relevance(metadata, criteria)
                        
                        results.append({
                            'evidence_id': metadata.evidence_id,
                            'evidence_type': metadata.evidence_type.value,
                            'block_id': metadata.block_id,
                            'timestamp': metadata.timestamp.isoformat(),
                            'file_path': metadata.file_path,
                            'tags': metadata.tags,
                            'relevance_score': relevance_score
                        })
                        
                except Exception as e:
                    logger.warning(f"Failed to process metadata file {metadata_file}: {e}")
                    continue
            
            # 関連度順でソート
            results.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            logger.info(f"Evidence search completed: {len(results)} results found")
            return results
            
        except Exception as e:
            logger.error(f"Evidence search failed: {str(e)}")
            raise BlockExecutionError(f"証跡検索エラー: {str(e)}")
    
    def log_audit_trail(self, entry: AuditTrailEntry):
        """
        監査証跡の記録
        
        Args:
            entry: 監査証跡エントリ
        """
        try:
            # デジタル署名生成
            entry_data = entry.dict(exclude={'signature'})
            entry_json = json.dumps(entry_data, sort_keys=True, default=str)
            entry.signature = self.encryption_manager.calculate_hmac(entry_json)
            
            # 監査証跡ファイルに追記
            audit_file = self.vault_path / 'audit_trail' / f"{entry.run_id}_audit.jsonl"
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.dict(), default=str) + '\n')
                
            logger.debug(f"Audit trail logged: {entry.entry_id}")
                
        except Exception as e:
            logger.error(f"Failed to log audit trail: {str(e)}")
            # 監査証跡の記録失敗は通常の処理を停止させない
    
    def build_data_lineage(self, run_id: str) -> Dict[str, Any]:
        """
        データ系譜の構築
        
        Args:
            run_id: 実行ID
            
        Returns:
            データ系譜情報
        """
        try:
            lineage_nodes = []
            lineage_edges = []
            
            # 監査証跡から系譜情報を抽出
            audit_file = self.vault_path / 'audit_trail' / f"{run_id}_audit.jsonl"
            
            if audit_file.exists():
                with open(audit_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line)
                            if entry['event_type'] == EventType.DATA_TRANSFORM.value:
                                # ノードとエッジの生成
                                node = DataLineageNode(
                                    node_id=f"{entry['block_id']}_{entry['timestamp']}",
                                    node_type='transform',
                                    block_id=entry['block_id'],
                                    data_hash=self.encryption_manager.calculate_hash(
                                        json.dumps(entry['outputs'], sort_keys=True)
                                    )
                                )
                                lineage_nodes.append(node)
                        except Exception as e:
                            logger.warning(f"Failed to process lineage entry: {e}")
                            continue
            
            # 系譜グラフの保存
            lineage_data = {
                'run_id': run_id,
                'nodes': [node.dict() for node in lineage_nodes],
                'edges': lineage_edges,
                'generated_at': datetime.now().isoformat()
            }
            
            lineage_file = self.vault_path / 'lineage' / f"{run_id}_lineage.json"
            lineage_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(lineage_file, 'w', encoding='utf-8') as f:
                json.dump(lineage_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Data lineage built for run {run_id}")
            return lineage_data
            
        except Exception as e:
            logger.error(f"Failed to build data lineage: {str(e)}")
            raise BlockExecutionError(f"データ系譜構築エラー: {str(e)}")
    
    def get_statistics(self, period_start: Optional[datetime] = None, 
                      period_end: Optional[datetime] = None) -> VaultStatistics:
        """
        Vault統計情報の取得
        
        Args:
            period_start: 統計期間開始
            period_end: 統計期間終了
            
        Returns:
            Vault統計情報
        """
        try:
            stats = VaultStatistics(
                period_start=period_start,
                period_end=period_end
            )
            
            metadata_dir = self.vault_path / 'evidence/metadata'
            
            if metadata_dir.exists():
                for metadata_file in metadata_dir.glob('*.json'):
                    try:
                        metadata = self._load_metadata_from_file(metadata_file)
                        
                        # 期間フィルタリング
                        if period_start and metadata.timestamp < period_start:
                            continue
                        if period_end and metadata.timestamp > period_end:
                            continue
                        
                        # 統計更新
                        stats.total_evidence_count += 1
                        stats.total_storage_size += metadata.file_size
                        
                        evidence_type = metadata.evidence_type.value
                        stats.evidence_by_type[evidence_type] = stats.evidence_by_type.get(evidence_type, 0) + 1
                        
                        # 日時更新
                        if not stats.oldest_evidence_date or metadata.timestamp < stats.oldest_evidence_date:
                            stats.oldest_evidence_date = metadata.timestamp
                        if not stats.newest_evidence_date or metadata.timestamp > stats.newest_evidence_date:
                            stats.newest_evidence_date = metadata.timestamp
                            
                    except Exception as e:
                        logger.warning(f"Failed to process statistics for {metadata_file}: {e}")
                        continue
            
            logger.info(f"Statistics generated: {stats.total_evidence_count} evidence items")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {str(e)}")
            raise BlockExecutionError(f"統計取得エラー: {str(e)}")
    
    def verify_integrity(self, evidence_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        証跡の整合性検証
        
        Args:
            evidence_ids: 検証対象の証跡ID（指定しない場合は全証跡）
            
        Returns:
            検証結果
        """
        try:
            verification_results = {
                'total_checked': 0,
                'passed': 0,
                'failed': 0,
                'errors': [],
                'check_timestamp': datetime.now().isoformat()
            }
            
            metadata_dir = self.vault_path / 'evidence/metadata'
            
            if not metadata_dir.exists():
                return verification_results
            
            metadata_files = []
            if evidence_ids:
                metadata_files = [metadata_dir / f"{eid}.json" for eid in evidence_ids if (metadata_dir / f"{eid}.json").exists()]
            else:
                metadata_files = list(metadata_dir.glob('*.json'))
            
            for metadata_file in metadata_files:
                try:
                    metadata = self._load_metadata_from_file(metadata_file)
                    verification_results['total_checked'] += 1
                    
                    # 整合性チェック
                    _, _ = self.retrieve_evidence(metadata.evidence_id, verify_integrity=True)
                    verification_results['passed'] += 1
                    
                except Exception as e:
                    verification_results['failed'] += 1
                    verification_results['errors'].append({
                        'evidence_id': metadata_file.stem,
                        'error': str(e)
                    })
            
            logger.info(f"Integrity verification completed: {verification_results['passed']}/{verification_results['total_checked']} passed")
            return verification_results
            
        except Exception as e:
            logger.error(f"Integrity verification failed: {str(e)}")
            raise BlockExecutionError(f"整合性検証エラー: {str(e)}")
    
    @contextmanager
    def transaction(self):
        """
        トランザクション管理
        
        Usage:
            with vault.transaction():
                vault.store_evidence(...)
                vault.store_evidence(...)
        """
        transaction_id = str(uuid.uuid4())
        temp_dir = self.vault_path / 'temp' / transaction_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            logger.debug(f"Transaction started: {transaction_id}")
            yield transaction_id
            logger.debug(f"Transaction committed: {transaction_id}")
        except Exception as e:
            logger.error(f"Transaction failed: {transaction_id}, error: {e}")
            # ロールバック処理（実装省略）
            raise
        finally:
            # 一時ディレクトリクリーンアップ
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    # プライベートメソッド
    
    def _save_metadata(self, metadata: EvidenceMetadata):
        """メタデータの保存"""
        metadata_file = self.vault_path / 'evidence/metadata' / f"{metadata.evidence_id}.json"
        metadata_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata.dict(), f, ensure_ascii=False, indent=2, default=str)
    
    def _load_metadata(self, evidence_id: str) -> EvidenceMetadata:
        """メタデータの読み込み"""
        metadata_file = self.vault_path / 'evidence/metadata' / f"{evidence_id}.json"
        
        if not metadata_file.exists():
            raise FileNotFoundError(f"メタデータファイルが見つかりません: {evidence_id}")
        
        return self._load_metadata_from_file(metadata_file)
    
    def _load_metadata_from_file(self, metadata_file: Path) -> EvidenceMetadata:
        """ファイルからメタデータを読み込み"""
        with open(metadata_file, 'r', encoding='utf-8') as f:
            metadata_dict = json.load(f)
        
        # datetimeフィールドの変換
        for field in ['timestamp', 'retention_until']:
            if field in metadata_dict and isinstance(metadata_dict[field], str):
                metadata_dict[field] = datetime.fromisoformat(metadata_dict[field].replace('Z', '+00:00'))
        
        return EvidenceMetadata(**metadata_dict)
    
    def _update_vault_index(self, metadata: EvidenceMetadata):
        """Vaultインデックスの更新"""
        index_file = self.vault_path / 'vault_index.json'
        
        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                index = json.load(f)
            
            index['evidence_count'] += 1
            index['last_evidence_id'] = metadata.evidence_id
            index['last_updated'] = datetime.now().isoformat()
            index['statistics']['total_size_bytes'] += metadata.file_size
            
            evidence_type = metadata.evidence_type.value
            index['statistics']['evidence_by_type'][evidence_type] = \
                index['statistics']['evidence_by_type'].get(evidence_type, 0) + 1
            
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            logger.warning(f"Failed to update vault index: {e}")
    
    def _log_evidence_operation(self, operation: str, evidence_id: str, block_id: str):
        """証跡操作の監査ログ記録"""
        entry = AuditTrailEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            event_type=EventType.EVIDENCE_STORE if operation == 'store' else EventType.EVIDENCE_RETRIEVE,
            block_id=block_id,
            run_id=evidence_id,  # 簡易実装
            status=ExecutionStatus.SUCCESS,
            inputs={'operation': operation, 'evidence_id': evidence_id},
            outputs={'success': True}
        )
        
        self.log_audit_trail(entry)
    
    def _matches_criteria(self, metadata: EvidenceMetadata, criteria: Dict[str, Any]) -> bool:
        """検索条件のマッチング"""
        # run_id条件
        if 'run_id' in criteria and criteria['run_id'] and criteria['run_id'] != metadata.run_id:
            return False
        
        # block_id条件
        if 'block_id' in criteria and criteria['block_id'] and criteria['block_id'] != metadata.block_id:
            return False
        
        # evidence_type条件
        if 'evidence_type' in criteria and criteria['evidence_type'] and criteria['evidence_type'] != metadata.evidence_type.value:
            return False
        
        # 日時範囲条件
        if 'date_from' in criteria and criteria['date_from']:
            date_from = datetime.fromisoformat(criteria['date_from']) if isinstance(criteria['date_from'], str) else criteria['date_from']
            if metadata.timestamp < date_from:
                return False
        
        if 'date_to' in criteria and criteria['date_to']:
            date_to = datetime.fromisoformat(criteria['date_to']) if isinstance(criteria['date_to'], str) else criteria['date_to']
            if metadata.timestamp > date_to:
                return False
        
        # タグ条件
        if 'tags' in criteria and criteria['tags']:
            search_tags = set(criteria['tags'])
            metadata_tags = set(metadata.tags)
            if not search_tags.intersection(metadata_tags):
                return False
        
        return True
    
    def _calculate_relevance(self, metadata: EvidenceMetadata, criteria: Dict[str, Any]) -> float:
        """関連度スコア計算"""
        score = 0.0
        
        # 完全一致ボーナス
        if 'run_id' in criteria and criteria['run_id'] == metadata.run_id:
            score += 10.0
        
        if 'block_id' in criteria and criteria['block_id'] == metadata.block_id:
            score += 5.0
        
        # タグマッチボーナス
        if 'tags' in criteria and criteria['tags']:
            search_tags = set(criteria['tags'])
            metadata_tags = set(metadata.tags)
            if search_tags and metadata_tags:
                match_ratio = len(search_tags.intersection(metadata_tags)) / len(search_tags)
                score += match_ratio * 3.0
        
        # 新しさボーナス
        days_old = (datetime.now() - metadata.timestamp).days
        freshness_score = max(0, 1.0 - (days_old / 365))  # 1年で0になる
        score += freshness_score
        
        return score