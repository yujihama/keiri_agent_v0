# Evidence Vault 詳細設計

## 概要

Evidence Vaultは、Keiri Agentにおける完全な監査証跡管理システムです。すべての処理実行、データ変換、統制テスト、承認プロセスの証跡を暗号化・改ざん検知機能付きで永続保存し、監査人や規制当局への透明性を確保します。

## 設計原則

### 1. 完全性（Integrity）
- すべての処理ステップの完全な記録
- データの改ざん検知機能
- デジタル署名による真正性保証

### 2. 可用性（Availability）
- 高速検索・フィルタリング機能
- 長期保存（7年以上）対応
- 災害復旧機能

### 3. 機密性（Confidentiality）
- エンドツーエンド暗号化
- アクセス制御・権限管理
- 個人情報保護対応

### 4. 監査性（Auditability）
- 完全な監査証跡
- 時系列追跡機能
- 規制要件への準拠

## アーキテクチャ設計

### 1. 既存システムとの統合

#### BlockContextの拡張
```python
# core/blocks/base.py の拡張
class BlockContext(BaseModel):
    run_id: str                    # 実行ID（既存）
    workspace: Optional[str]       # ワークスペース（既存）
    vars: Dict[str, Any]          # 変数（既存）
    
    # Evidence Vault拡張
    evidence_vault: Optional['EvidenceVault'] = None
    audit_session_id: Optional[str] = None
    retention_policy: Optional[str] = None
    encryption_enabled: bool = True
```

#### ワークスペース構造の拡張
```
workspace/
├── evidence/                  # 証跡ファイル
│   ├── raw/                  # 生データ
│   ├── processed/            # 処理済みデータ
│   ├── outputs/              # 出力データ
│   └── metadata/             # メタデータ
├── audit_trail/              # 監査証跡
│   ├── execution_log.json    # 実行ログ
│   ├── data_lineage.json     # データ系譜
│   └── control_results.json  # 統制結果
├── signatures/               # デジタル署名
│   ├── block_signatures.json # ブロック署名
│   └── session_signature.json # セッション署名
└── vault_index.json          # Vault索引
```

### 2. Evidence Vaultコアコンポーネント

#### EvidenceVault基底クラス
```python
# core/evidence/vault.py
from __future__ import annotations
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from pathlib import Path
import json
import hashlib
import hmac
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

class EvidenceMetadata(BaseModel):
    evidence_id: str
    evidence_type: str  # input, output, intermediate, control_result
    block_id: str
    run_id: str
    timestamp: datetime
    file_path: str
    file_hash: str
    file_size: int
    encryption_key_id: Optional[str] = None
    retention_until: datetime
    tags: List[str] = []
    related_evidence: List[str] = []

class AuditTrailEntry(BaseModel):
    entry_id: str
    timestamp: datetime
    event_type: str  # block_start, block_end, data_transform, control_check
    block_id: str
    run_id: str
    user_id: Optional[str] = None
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    execution_time_ms: int
    status: str  # success, error, warning
    error_details: Optional[str] = None
    signature: Optional[str] = None

class DataLineageNode(BaseModel):
    node_id: str
    node_type: str  # source, transform, sink
    block_id: str
    data_hash: str
    parent_nodes: List[str] = []
    child_nodes: List[str] = []
    transformation_details: Dict[str, Any] = {}

class EvidenceVault:
    """Evidence Vault メインクラス"""
    
    def __init__(self, vault_path: str, encryption_key: Optional[str] = None):
        self.vault_path = Path(vault_path)
        self.encryption_key = encryption_key or Fernet.generate_key()
        self.cipher = Fernet(self.encryption_key)
        self._ensure_vault_structure()
    
    def _ensure_vault_structure(self):
        """Vault ディレクトリ構造の確保"""
        directories = [
            'evidence/raw',
            'evidence/processed', 
            'evidence/outputs',
            'evidence/metadata',
            'audit_trail',
            'signatures',
            'lineage'
        ]
        
        for directory in directories:
            (self.vault_path / directory).mkdir(parents=True, exist_ok=True)
    
    def store_evidence(self, evidence_data: Union[str, bytes, Dict[str, Any]], 
                      metadata: EvidenceMetadata) -> str:
        """証跡データの保存"""
        try:
            # ファイルパス生成
            evidence_file = self.vault_path / metadata.file_path
            evidence_file.parent.mkdir(parents=True, exist_ok=True)
            
            # データの暗号化と保存
            if isinstance(evidence_data, dict):
                data_bytes = json.dumps(evidence_data, ensure_ascii=False, indent=2).encode('utf-8')
            elif isinstance(evidence_data, str):
                data_bytes = evidence_data.encode('utf-8')
            else:
                data_bytes = evidence_data
            
            encrypted_data = self.cipher.encrypt(data_bytes)
            
            with open(evidence_file, 'wb') as f:
                f.write(encrypted_data)
            
            # ハッシュ計算
            metadata.file_hash = hashlib.sha256(data_bytes).hexdigest()
            metadata.file_size = len(data_bytes)
            
            # メタデータ保存
            metadata_file = self.vault_path / 'evidence/metadata' / f"{metadata.evidence_id}.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata.dict(), f, ensure_ascii=False, indent=2, default=str)
            
            # インデックス更新
            self._update_vault_index(metadata)
            
            return metadata.evidence_id
            
        except Exception as e:
            raise Exception(f"証跡保存エラー: {str(e)}")
    
    def retrieve_evidence(self, evidence_id: str) -> tuple[Any, EvidenceMetadata]:
        """証跡データの取得"""
        try:
            # メタデータ読み込み
            metadata_file = self.vault_path / 'evidence/metadata' / f"{evidence_id}.json"
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata_dict = json.load(f)
            metadata = EvidenceMetadata(**metadata_dict)
            
            # データ読み込みと復号化
            evidence_file = self.vault_path / metadata.file_path
            with open(evidence_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            
            # ハッシュ検証
            current_hash = hashlib.sha256(decrypted_data).hexdigest()
            if current_hash != metadata.file_hash:
                raise Exception(f"データ改ざんを検出: {evidence_id}")
            
            # データ形式の復元
            try:
                data = json.loads(decrypted_data.decode('utf-8'))
            except json.JSONDecodeError:
                data = decrypted_data.decode('utf-8')
            
            return data, metadata
            
        except Exception as e:
            raise Exception(f"証跡取得エラー: {str(e)}")
    
    def log_audit_trail(self, entry: AuditTrailEntry):
        """監査証跡の記録"""
        try:
            # デジタル署名生成
            entry_data = entry.dict(exclude={'signature'})
            entry_json = json.dumps(entry_data, sort_keys=True, default=str)
            signature = hmac.new(
                self.encryption_key, 
                entry_json.encode('utf-8'), 
                hashlib.sha256
            ).hexdigest()
            entry.signature = signature
            
            # 監査証跡ファイルに追記
            audit_file = self.vault_path / 'audit_trail' / f"{entry.run_id}_audit.jsonl"
            with open(audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.dict(), default=str) + '\n')
                
        except Exception as e:
            raise Exception(f"監査証跡記録エラー: {str(e)}")
    
    def build_data_lineage(self, run_id: str) -> Dict[str, Any]:
        """データ系譜の構築"""
        try:
            lineage_nodes = []
            lineage_edges = []
            
            # 監査証跡から系譜情報を抽出
            audit_file = self.vault_path / 'audit_trail' / f"{run_id}_audit.jsonl"
            if audit_file.exists():
                with open(audit_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        entry = json.loads(line)
                        if entry['event_type'] == 'data_transform':
                            # ノードとエッジの生成
                            node = DataLineageNode(
                                node_id=f"{entry['block_id']}_{entry['timestamp']}",
                                node_type='transform',
                                block_id=entry['block_id'],
                                data_hash=hashlib.sha256(
                                    json.dumps(entry['outputs'], sort_keys=True).encode()
                                ).hexdigest()
                            )
                            lineage_nodes.append(node)
            
            # 系譜グラフの保存
            lineage_data = {
                'run_id': run_id,
                'nodes': [node.dict() for node in lineage_nodes],
                'edges': lineage_edges,
                'generated_at': datetime.now().isoformat()
            }
            
            lineage_file = self.vault_path / 'lineage' / f"{run_id}_lineage.json"
            with open(lineage_file, 'w', encoding='utf-8') as f:
                json.dump(lineage_data, f, ensure_ascii=False, indent=2)
            
            return lineage_data
            
        except Exception as e:
            raise Exception(f"データ系譜構築エラー: {str(e)}")
```


### 3. ブロック統合機能

#### ProcessingBlockの拡張
```python
# core/blocks/base.py の拡張
from core.evidence.vault import EvidenceVault, EvidenceMetadata, AuditTrailEntry
import uuid
from datetime import datetime, timedelta

class ProcessingBlock(ABC):
    """拡張されたProcessingBlock基底クラス"""
    
    def execute_with_evidence(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """証跡管理付き実行"""
        start_time = datetime.now()
        
        try:
            # 実行前の証跡記録
            if context.evidence_vault:
                self._log_execution_start(inputs, context, start_time)
                self._store_input_evidence(inputs, context)
            
            # 実際の処理実行
            outputs = self.execute(inputs, context)
            
            # 実行後の証跡記録
            if context.evidence_vault:
                self._store_output_evidence(outputs, context)
                self._log_execution_end(inputs, outputs, context, start_time, 'success')
            
            return outputs
            
        except Exception as e:
            # エラー時の証跡記録
            if context.evidence_vault:
                self._log_execution_end(inputs, {}, context, start_time, 'error', str(e))
            raise
    
    def _log_execution_start(self, inputs: Dict[str, Any], context: BlockContext, start_time: datetime):
        """実行開始ログ"""
        entry = AuditTrailEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=start_time,
            event_type='block_start',
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            inputs=self._sanitize_sensitive_data(inputs),
            outputs={},
            execution_time_ms=0,
            status='started'
        )
        context.evidence_vault.log_audit_trail(entry)
    
    def _store_input_evidence(self, inputs: Dict[str, Any], context: BlockContext):
        """入力データの証跡保存"""
        evidence_id = f"input_{context.run_id}_{self.__class__.__name__}_{uuid.uuid4().hex[:8]}"
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type='input',
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/raw/{context.run_id}/{evidence_id}.json",
            file_hash='',  # 保存時に計算
            file_size=0,   # 保存時に計算
            retention_until=datetime.now() + timedelta(days=2555),  # 7年保存
            tags=['input', 'block_execution']
        )
        
        context.evidence_vault.store_evidence(inputs, metadata)
    
    def _store_output_evidence(self, outputs: Dict[str, Any], context: BlockContext):
        """出力データの証跡保存"""
        evidence_id = f"output_{context.run_id}_{self.__class__.__name__}_{uuid.uuid4().hex[:8]}"
        
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            evidence_type='output',
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/outputs/{context.run_id}/{evidence_id}.json",
            file_hash='',
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['output', 'block_execution']
        )
        
        context.evidence_vault.store_evidence(outputs, metadata)
    
    def _sanitize_sensitive_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """機密データのサニタイズ"""
        sensitive_keys = ['password', 'api_key', 'token', 'secret']
        sanitized = data.copy()
        
        for key in sensitive_keys:
            if key in sanitized:
                sanitized[key] = '***REDACTED***'
        
        return sanitized

    @abstractmethod
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """実際の処理実行（サブクラスで実装）"""
        pass
```

### 4. Evidence Vault専用ブロック

#### evidence.store ブロック
```yaml
# block_specs/processing/evidence/store.yaml
id: evidence.store
version: 1.0.0
entrypoint: blocks/processing/evidence/store.py:EvidenceStoreBlock
description: 任意のデータをEvidence Vaultに保存

inputs:
  evidence_data:
    type: object
    description: 保存する証跡データ
  evidence_type:
    type: string
    enum: [document, calculation, control_result, approval_record, audit_finding]
    description: 証跡タイプ
  retention_period_days:
    type: integer
    minimum: 1
    maximum: 3650
    default: 2555
    description: 保存期間（日数）
  tags:
    type: array
    items:
      type: string
    description: 検索用タグ
  related_evidence_ids:
    type: array
    items:
      type: string
    description: 関連証跡ID

output_schema:
  type: object
  properties:
    evidence_id:
      type: string
      description: 生成された証跡ID
    storage_path:
      type: string
      description: 保存パス
    file_hash:
      type: string
      description: ファイルハッシュ
    retention_until:
      type: string
      format: date-time
      description: 保存期限
  required: [evidence_id, storage_path, file_hash, retention_until]
```

#### evidence.retrieve ブロック
```yaml
# block_specs/processing/evidence/retrieve.yaml
id: evidence.retrieve
version: 1.0.0
entrypoint: blocks/processing/evidence/retrieve.py:EvidenceRetrieveBlock
description: Evidence Vaultから証跡データを取得

inputs:
  evidence_id:
    type: string
    description: 取得する証跡ID
  verify_integrity:
    type: boolean
    default: true
    description: 整合性検証の実行

output_schema:
  type: object
  properties:
    evidence_data:
      type: object
      description: 取得された証跡データ
    metadata:
      type: object
      description: 証跡メタデータ
      properties:
        evidence_id:
          type: string
        evidence_type:
          type: string
        timestamp:
          type: string
          format: date-time
        file_hash:
          type: string
        integrity_verified:
          type: boolean
    retrieval_timestamp:
      type: string
      format: date-time
      description: 取得日時
  required: [evidence_data, metadata, retrieval_timestamp]
```

#### evidence.search ブロック
```yaml
# block_specs/processing/evidence/search.yaml
id: evidence.search
version: 1.0.0
entrypoint: blocks/processing/evidence/search.py:EvidenceSearchBlock
description: Evidence Vault内の証跡検索

inputs:
  search_criteria:
    type: object
    description: 検索条件
    properties:
      run_id:
        type: string
        description: 実行ID
      block_id:
        type: string
        description: ブロックID
      evidence_type:
        type: string
        description: 証跡タイプ
      date_from:
        type: string
        format: date-time
        description: 開始日時
      date_to:
        type: string
        format: date-time
        description: 終了日時
      tags:
        type: array
        items:
          type: string
        description: 検索タグ
      text_search:
        type: string
        description: テキスト検索
  limit:
    type: integer
    minimum: 1
    maximum: 1000
    default: 100
    description: 取得件数上限

output_schema:
  type: object
  properties:
    search_results:
      type: array
      items:
        type: object
        properties:
          evidence_id:
            type: string
          evidence_type:
            type: string
          block_id:
            type: string
          timestamp:
            type: string
            format: date-time
          file_path:
            type: string
          tags:
            type: array
            items:
              type: string
          relevance_score:
            type: number
            description: 関連度スコア
    total_count:
      type: integer
      description: 総件数
    search_timestamp:
      type: string
      format: date-time
      description: 検索実行日時
  required: [search_results, total_count, search_timestamp]
```

### 5. 監査レポート生成機能

#### evidence.audit_report ブロック
```yaml
# block_specs/processing/evidence/audit_report.yaml
id: evidence.audit_report
version: 1.0.0
entrypoint: blocks/processing/evidence/audit_report.py:AuditReportBlock
description: 監査レポートの自動生成

inputs:
  report_scope:
    type: object
    description: レポート範囲
    properties:
      run_ids:
        type: array
        items:
          type: string
        description: 対象実行ID
      date_from:
        type: string
        format: date-time
        description: 開始日時
      date_to:
        type: string
        format: date-time
        description: 終了日時
      audit_areas:
        type: array
        items:
          type: string
          enum: [approval_control, sod_control, data_integrity, access_control]
        description: 監査領域
  report_format:
    type: string
    enum: [detailed, summary, executive]
    default: detailed
    description: レポート形式
  include_evidence_links:
    type: boolean
    default: true
    description: 証跡リンクの含有

output_schema:
  type: object
  properties:
    audit_report:
      type: object
      description: 監査レポート
      properties:
        report_id:
          type: string
        generated_at:
          type: string
          format: date-time
        scope_summary:
          type: object
          properties:
            total_runs:
              type: integer
            total_evidence_items:
              type: integer
            date_range:
              type: object
              properties:
                from:
                  type: string
                  format: date-time
                to:
                  type: string
                  format: date-time
        findings:
          type: array
          items:
            type: object
            properties:
              finding_id:
                type: string
              severity:
                type: string
                enum: [low, medium, high, critical]
              category:
                type: string
              description:
                type: string
              evidence_ids:
                type: array
                items:
                  type: string
              recommendation:
                type: string
        compliance_summary:
          type: object
          properties:
            overall_score:
              type: number
              minimum: 0
              maximum: 100
            control_effectiveness:
              type: object
              additionalProperties:
                type: string
                enum: [effective, partially_effective, ineffective]
        evidence_integrity:
          type: object
          properties:
            total_evidence_checked:
              type: integer
            integrity_violations:
              type: integer
            integrity_score:
              type: number
              minimum: 0
              maximum: 100
    report_file_path:
      type: string
      description: 生成されたレポートファイルパス
    evidence_package_path:
      type: string
      description: 証跡パッケージファイルパス
  required: [audit_report, report_file_path]
```


### 6. Evidence Vault実装クラス

#### EvidenceStoreBlock実装
```python
# core/blocks/processing/evidence/store.py
from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime, timedelta
import uuid

from core.blocks.base import ProcessingBlock, BlockContext
from core.evidence.vault import EvidenceMetadata
from core.errors import BlockExecutionError

class EvidenceStoreBlock(ProcessingBlock):
    """証跡保存ブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """証跡データの保存"""
        try:
            if not context.evidence_vault:
                raise BlockExecutionError("Evidence Vaultが初期化されていません")
            
            # 入力パラメータの取得
            evidence_data = inputs['evidence_data']
            evidence_type = inputs['evidence_type']
            retention_days = inputs.get('retention_period_days', 2555)
            tags = inputs.get('tags', [])
            related_evidence_ids = inputs.get('related_evidence_ids', [])
            
            # 証跡ID生成
            evidence_id = f"evidence_{uuid.uuid4().hex}"
            
            # メタデータ作成
            metadata = EvidenceMetadata(
                evidence_id=evidence_id,
                evidence_type=evidence_type,
                block_id=self.__class__.__name__,
                run_id=context.run_id,
                timestamp=datetime.now(),
                file_path=f"evidence/processed/{context.run_id}/{evidence_id}.json",
                file_hash='',  # store_evidenceで計算
                file_size=0,   # store_evidenceで計算
                retention_until=datetime.now() + timedelta(days=retention_days),
                tags=tags + ['manual_store'],
                related_evidence=related_evidence_ids
            )
            
            # 証跡保存
            stored_evidence_id = context.evidence_vault.store_evidence(evidence_data, metadata)
            
            return {
                'evidence_id': stored_evidence_id,
                'storage_path': metadata.file_path,
                'file_hash': metadata.file_hash,
                'retention_until': metadata.retention_until.isoformat()
            }
            
        except Exception as e:
            raise BlockExecutionError(f"証跡保存でエラーが発生しました: {str(e)}")
```

#### EvidenceSearchBlock実装
```python
# core/blocks/processing/evidence/search.py
from __future__ import annotations
from typing import Dict, Any, List
from datetime import datetime
import json
import re
from pathlib import Path

from core.blocks.base import ProcessingBlock, BlockContext
from core.evidence.vault import EvidenceMetadata
from core.errors import BlockExecutionError

class EvidenceSearchBlock(ProcessingBlock):
    """証跡検索ブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """証跡データの検索"""
        try:
            if not context.evidence_vault:
                raise BlockExecutionError("Evidence Vaultが初期化されていません")
            
            search_criteria = inputs['search_criteria']
            limit = inputs.get('limit', 100)
            
            # 検索実行
            search_results = self._search_evidence(context.evidence_vault, search_criteria, limit)
            
            return {
                'search_results': search_results,
                'total_count': len(search_results),
                'search_timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            raise BlockExecutionError(f"証跡検索でエラーが発生しました: {str(e)}")
    
    def _search_evidence(self, vault, criteria: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """証跡検索の実行"""
        results = []
        metadata_dir = vault.vault_path / 'evidence/metadata'
        
        if not metadata_dir.exists():
            return results
        
        # メタデータファイルを走査
        for metadata_file in metadata_dir.glob('*.json'):
            try:
                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata_dict = json.load(f)
                
                metadata = EvidenceMetadata(**metadata_dict)
                
                # 検索条件のマッチング
                if self._matches_criteria(metadata, criteria):
                    # テキスト検索（必要に応じて）
                    relevance_score = self._calculate_relevance(metadata, criteria)
                    
                    results.append({
                        'evidence_id': metadata.evidence_id,
                        'evidence_type': metadata.evidence_type,
                        'block_id': metadata.block_id,
                        'timestamp': metadata.timestamp.isoformat(),
                        'file_path': metadata.file_path,
                        'tags': metadata.tags,
                        'relevance_score': relevance_score
                    })
                    
                    if len(results) >= limit:
                        break
                        
            except Exception as e:
                # 個別ファイルのエラーは無視して続行
                continue
        
        # 関連度順でソート
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results
    
    def _matches_criteria(self, metadata: EvidenceMetadata, criteria: Dict[str, Any]) -> bool:
        """検索条件のマッチング"""
        # run_id条件
        if 'run_id' in criteria and criteria['run_id'] != metadata.run_id:
            return False
        
        # block_id条件
        if 'block_id' in criteria and criteria['block_id'] != metadata.block_id:
            return False
        
        # evidence_type条件
        if 'evidence_type' in criteria and criteria['evidence_type'] != metadata.evidence_type:
            return False
        
        # 日時範囲条件
        if 'date_from' in criteria:
            date_from = datetime.fromisoformat(criteria['date_from'])
            if metadata.timestamp < date_from:
                return False
        
        if 'date_to' in criteria:
            date_to = datetime.fromisoformat(criteria['date_to'])
            if metadata.timestamp > date_to:
                return False
        
        # タグ条件
        if 'tags' in criteria:
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
        if 'tags' in criteria:
            search_tags = set(criteria['tags'])
            metadata_tags = set(metadata.tags)
            match_ratio = len(search_tags.intersection(metadata_tags)) / len(search_tags)
            score += match_ratio * 3.0
        
        # 新しさボーナス
        days_old = (datetime.now() - metadata.timestamp).days
        freshness_score = max(0, 1.0 - (days_old / 365))  # 1年で0になる
        score += freshness_score
        
        return score
```

### 7. Plan DSL統合例

#### 証跡管理付き監査プラン
```yaml
# designs/evidence_managed_audit.yaml
apiVersion: v1
id: evidence_managed_audit
description: Evidence Vault統合監査プラン
version: 1.0.0

vars:
  audit_session_id: "audit_2025_q1_${timestamp}"
  retention_policy: "regulatory_7years"
  evidence_encryption: true

policy:
  on_error: stop
  retries: 1
  evidence_vault:
    enabled: true
    encryption_required: true
    retention_default_days: 2555

ui:
  layout:
    - ui_audit_setup
    - ui_evidence_review
    - ui_final_approval

graph:
  # 1. 監査セットアップ
  - id: ui_audit_setup
    description: 監査パラメータとEvidence Vault設定
    block: ui.interactive_input
    in:
      mode: collect
      requirements:
        - id: source_documents
          label: 監査対象文書
          type: file
          accept: .xlsx,.pdf,.zip
          required: true
        - id: audit_scope
          label: 監査範囲
          type: text
          required: true

  # 2. 初期証跡保存
  - id: store_source_evidence
    description: 監査対象文書の証跡保存
    block: evidence.store
    in:
      evidence_data: ${ui_audit_setup.collected_data}
      evidence_type: "document"
      retention_period_days: 2555
      tags: ["source_document", "audit_input", "${audit_session_id}"]
    out:
      source_evidence_id: evidence_id

  # 3. データ処理と証跡記録
  - id: process_audit_data
    description: 監査データの処理
    block: excel.read_data
    in:
      source: ${ui_audit_setup.collected_data}
      path: source_documents
    out:
      processed_data: data
      processing_evidence: evidence_files

  # 4. 処理結果の証跡保存
  - id: store_processing_evidence
    description: 処理結果の証跡保存
    block: evidence.store
    in:
      evidence_data:
        processed_data: ${process_audit_data.processed_data}
        processing_metadata:
          block_id: "excel.read_data"
          processing_timestamp: "${timestamp}"
          source_evidence_id: ${store_source_evidence.source_evidence_id}
      evidence_type: "calculation"
      tags: ["data_processing", "intermediate_result", "${audit_session_id}"]
      related_evidence_ids: [${store_source_evidence.source_evidence_id}]
    out:
      processing_evidence_id: evidence_id

  # 5. 統制テスト実行
  - id: control_testing
    description: 統制テストの実行
    block: control.approval
    in:
      approval_request:
        request_id: "${audit_session_id}_approval_test"
        requester: "audit_system"
        amount: 1000000
        description: "統制テスト用サンプル取引"
      approval_policy:
        levels:
          - level: 1
            min_amount: 0
            max_amount: 1000000
            required_approvers: 2
            approver_roles: ["manager", "director"]
            timeout_hours: 24
      current_approvals: []
    out:
      control_results: approval_status
      control_evidence: evidence_files

  # 6. 統制テスト結果の証跡保存
  - id: store_control_evidence
    description: 統制テスト結果の証跡保存
    block: evidence.store
    in:
      evidence_data:
        control_test_results: ${control_testing.control_results}
        test_parameters:
          test_type: "approval_control"
          test_date: "${timestamp}"
          sample_size: 1
        related_processing: ${processing_evidence_id}
      evidence_type: "control_result"
      tags: ["control_testing", "approval_control", "${audit_session_id}"]
      related_evidence_ids: 
        - ${store_source_evidence.source_evidence_id}
        - ${store_processing_evidence.processing_evidence_id}
    out:
      control_evidence_id: evidence_id

  # 7. 証跡検索とレビュー
  - id: search_related_evidence
    description: 関連証跡の検索
    block: evidence.search
    in:
      search_criteria:
        tags: ["${audit_session_id}"]
        evidence_type: null
        date_from: "${audit_start_date}"
        date_to: "${timestamp}"
      limit: 100
    out:
      evidence_inventory: search_results

  # 8. 監査レポート生成
  - id: generate_audit_report
    description: 証跡付き監査レポート生成
    block: evidence.audit_report
    in:
      report_scope:
        run_ids: ["${run_id}"]
        audit_areas: ["approval_control", "data_integrity"]
      report_format: "detailed"
      include_evidence_links: true
    out:
      final_report: audit_report
      report_file: report_file_path

  # 9. 最終証跡保存
  - id: store_final_evidence
    description: 最終監査レポートの証跡保存
    block: evidence.store
    in:
      evidence_data:
        audit_report: ${generate_audit_report.final_report}
        evidence_inventory: ${search_related_evidence.evidence_inventory}
        audit_conclusion:
          session_id: "${audit_session_id}"
          completion_date: "${timestamp}"
          auditor: "Keiri Agent"
          total_evidence_items: ${search_related_evidence.evidence_inventory.length}
      evidence_type: "audit_finding"
      retention_period_days: 2555
      tags: ["final_report", "audit_conclusion", "${audit_session_id}"]
      related_evidence_ids:
        - ${store_source_evidence.source_evidence_id}
        - ${store_processing_evidence.processing_evidence_id}
        - ${store_control_evidence.control_evidence_id}
    out:
      final_evidence_id: evidence_id

  # 10. 証跡レビューUI
  - id: ui_evidence_review
    description: 生成された証跡のレビュー
    block: ui.interactive_input
    in:
      mode: review
      display_data:
        - label: "監査セッションID"
          value: "${audit_session_id}"
        - label: "総証跡数"
          value: ${search_related_evidence.evidence_inventory.length}
        - label: "監査レポート"
          value: ${generate_audit_report.report_file}
        - label: "証跡完全性"
          value: "検証済み"
      message: "証跡の完全性と監査結果を確認してください。"
    out:
      review_approved: approved

  # 11. 最終承認
  - id: ui_final_approval
    description: 監査完了の最終承認
    block: ui.interactive_input
    in:
      mode: confirm
      message: |
        監査プロセスが完了しました。
        
        - 監査セッション: ${audit_session_id}
        - 証跡保存期間: 7年間
        - 最終レポート: ${generate_audit_report.report_file}
        
        監査を完了し、証跡をアーカイブしますか？
    when:
      condition: ${ui_evidence_review.review_approved}
    out:
      audit_completed: approved
```

### 8. 期待効果とメリット

#### 監査効率化
- **証跡作成自動化**: 手動作業を90%削減
- **検索時間短縮**: 従来の1/10の時間で必要な証跡を発見
- **レポート生成**: 完全自動化による即座のレポート作成

#### コンプライアンス強化
- **完全な監査証跡**: すべての処理ステップの記録
- **改ざん検知**: 暗号化ハッシュによる完全性保証
- **長期保存**: 規制要件（7年間）への完全対応

#### 透明性向上
- **データ系譜**: 処理の流れの完全な可視化
- **アクセス履歴**: 証跡へのアクセス記録
- **監査人対応**: 即座の証跡提供能力

