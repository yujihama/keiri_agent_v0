"""承認統制ブロック

多段承認フローの実行と承認履歴の管理を行います。
金額に基づく承認レベルの決定、承認状況の評価、エスカレーション処理などを提供します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import json
import os
import uuid

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError
from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType


class ApprovalRequest(BaseModel):
    """承認要求データ"""
    request_id: str
    requester: str
    amount: float
    description: str
    attachments: List[str] = []


class ApprovalLevel(BaseModel):
    """承認レベル定義"""
    level: int
    min_amount: float
    max_amount: float
    required_approvers: int
    approver_roles: List[str]
    timeout_hours: int


class EscalationPolicy(BaseModel):
    """エスカレーションポリシー"""
    enabled: bool = False
    escalation_hours: int = 24
    escalation_roles: List[str] = []


class ApprovalPolicy(BaseModel):
    """承認ポリシー"""
    levels: List[ApprovalLevel]
    escalation_policy: EscalationPolicy


class CurrentApproval(BaseModel):
    """現在の承認状況"""
    approver: str
    status: str  # pending, approved, rejected
    timestamp: datetime
    comment: Optional[str] = None


class ApprovalBlock(ProcessingBlock):
    """承認統制ブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """承認フローの実行"""
        try:
            # 入力データの検証と変換
            approval_request = ApprovalRequest(**inputs['approval_request'])
            approval_policy = ApprovalPolicy(**inputs['approval_policy'])
            current_approvals = self._parse_current_approvals(inputs.get('current_approvals', []))
            
            # 承認レベルの決定
            required_level = self._determine_approval_level(approval_request.amount, approval_policy.levels)
            
            # 承認状況の評価
            approval_status = self._evaluate_approval_status(required_level, current_approvals, approval_policy)
            
            # 承認履歴の生成
            approval_history = self._generate_approval_history(current_approvals)
            
            # 必要な承認の生成
            required_approvals = self._format_required_approvals(required_level, current_approvals)
            
            # 次のアクションの決定
            next_actions = self._determine_next_actions(approval_status, required_level, current_approvals, approval_policy)
            
            # 証跡ファイルの生成
            evidence_files = self._generate_evidence_files(
                approval_request, approval_policy, current_approvals, 
                approval_status, context
            )
            
            return {
                'approval_status': approval_status,
                'required_approvals': required_approvals,
                'approval_history': approval_history,
                'next_actions': next_actions,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"承認統制処理でエラーが発生しました: {str(e)}")
    
    def _parse_current_approvals(self, approvals_data: List[Dict[str, Any]]) -> List[CurrentApproval]:
        """現在の承認状況をパース"""
        current_approvals = []
        for approval_data in approvals_data:
            # timestampの変換
            if isinstance(approval_data.get('timestamp'), str):
                approval_data['timestamp'] = datetime.fromisoformat(approval_data['timestamp'].replace('Z', '+00:00'))
            elif approval_data.get('timestamp') is None:
                approval_data['timestamp'] = datetime.now()
            
            current_approvals.append(CurrentApproval(**approval_data))
        
        return current_approvals
    
    def _determine_approval_level(self, amount: float, levels: List[ApprovalLevel]) -> ApprovalLevel:
        """金額に基づく承認レベルの決定"""
        # 金額に合致するレベルを検索
        matching_levels = [
            level for level in levels 
            if level.min_amount <= amount <= level.max_amount
        ]
        
        if matching_levels:
            # 複数合致する場合は最も高いレベルを選択
            return max(matching_levels, key=lambda x: x.level)
        else:
            # 合致しない場合は最高レベルを返す
            return max(levels, key=lambda x: x.level)
    
    def _evaluate_approval_status(self, required_level: ApprovalLevel, 
                                current_approvals: List[CurrentApproval],
                                policy: ApprovalPolicy) -> str:
        """承認状況の評価"""
        approved_count = sum(1 for approval in current_approvals if approval.status == 'approved')
        rejected_count = sum(1 for approval in current_approvals if approval.status == 'rejected')
        
        # 拒否がある場合
        if rejected_count > 0:
            return 'rejected'
        
        # 必要承認数に達している場合
        if approved_count >= required_level.required_approvers:
            return 'approved'
        
        # エスカレーション判定
        if policy.escalation_policy.enabled:
            oldest_pending = self._get_oldest_pending_timestamp(current_approvals)
            if oldest_pending:
                time_elapsed = datetime.now() - oldest_pending
                if time_elapsed > timedelta(hours=policy.escalation_policy.escalation_hours):
                    return 'escalated'
        
        return 'pending'
    
    def _get_oldest_pending_timestamp(self, current_approvals: List[CurrentApproval]) -> Optional[datetime]:
        """最も古い保留中の承認のタイムスタンプを取得"""
        pending_timestamps = [
            approval.timestamp for approval in current_approvals 
            if approval.status == 'pending'
        ]
        return min(pending_timestamps) if pending_timestamps else None
    
    def _generate_approval_history(self, current_approvals: List[CurrentApproval]) -> List[Dict[str, Any]]:
        """承認履歴の生成"""
        history = []
        for approval in current_approvals:
            if approval.status != 'pending':  # 完了した承認のみ履歴に含める
                history.append({
                    'approver': approval.approver,
                    'action': approval.status,  # approved, rejected
                    'timestamp': approval.timestamp.isoformat(),
                    'comment': approval.comment or ''
                })
        
        # 時系列順でソート
        history.sort(key=lambda x: x['timestamp'])
        return history
    
    def _format_required_approvals(self, required_level: ApprovalLevel, 
                                 current_approvals: List[CurrentApproval]) -> List[Dict[str, Any]]:
        """必要な承認の整形"""
        approved_count = sum(1 for approval in current_approvals if approval.status == 'approved')
        remaining_approvals = max(0, required_level.required_approvers - approved_count)
        
        required_approvals = []
        
        # 既に取得した承認
        for approval in current_approvals:
            if approval.status == 'approved':
                required_approvals.append({
                    'level': required_level.level,
                    'approver_role': 'completed',
                    'status': 'approved',
                    'deadline': (approval.timestamp + timedelta(hours=required_level.timeout_hours)).isoformat()
                })
        
        # 残りの必要な承認
        for i in range(remaining_approvals):
            deadline = datetime.now() + timedelta(hours=required_level.timeout_hours)
            required_approvals.append({
                'level': required_level.level,
                'approver_role': required_level.approver_roles[0] if required_level.approver_roles else 'unknown',
                'status': 'pending',
                'deadline': deadline.isoformat()
            })
        
        return required_approvals
    
    def _determine_next_actions(self, approval_status: str, required_level: ApprovalLevel,
                              current_approvals: List[CurrentApproval], 
                              policy: ApprovalPolicy) -> List[Dict[str, Any]]:
        """次のアクションの決定"""
        next_actions = []
        
        if approval_status == 'pending':
            # 承認待ち
            deadline = datetime.now() + timedelta(hours=required_level.timeout_hours)
            next_actions.append({
                'action_type': 'wait_approval',
                'target_role': required_level.approver_roles[0] if required_level.approver_roles else 'unknown',
                'deadline': deadline.isoformat()
            })
        
        elif approval_status == 'escalated':
            # エスカレーション
            if policy.escalation_policy.escalation_roles:
                deadline = datetime.now() + timedelta(hours=policy.escalation_policy.escalation_hours)
                next_actions.append({
                    'action_type': 'escalate',
                    'target_role': policy.escalation_policy.escalation_roles[0],
                    'deadline': deadline.isoformat()
                })
        
        elif approval_status == 'approved':
            # 完了
            next_actions.append({
                'action_type': 'complete',
                'target_role': 'system',
                'deadline': datetime.now().isoformat()
            })
        
        elif approval_status == 'rejected':
            # 拒否
            next_actions.append({
                'action_type': 'reject',
                'target_role': 'system',
                'deadline': datetime.now().isoformat()
            })
        
        return next_actions
    
    def _generate_evidence_files(self, request: ApprovalRequest, policy: ApprovalPolicy,
                               approvals: List[CurrentApproval], status: str,
                               context: BlockContext) -> List[str]:
        """証跡ファイルの生成"""
        evidence_files = []
        
        try:
            # Evidence Vaultの取得
            evidence_vault = getattr(context, 'evidence_vault', None)
            if not evidence_vault:
                # Evidence Vaultが設定されていない場合は従来の方式でファイル保存
                evidence_files = self._generate_legacy_evidence_files(request, policy, approvals, status, context)
            else:
                # Evidence Vaultを使用した証跡保存
                evidence_files = self._generate_vault_evidence_files(request, policy, approvals, status, context, evidence_vault)
        
        except Exception as e:
            # 証跡生成失敗時は警告ログを出力するが処理は継続
            import logging
            logging.warning(f"証跡ファイル生成でエラーが発生しました: {str(e)}")
            evidence_files = []
        
        return evidence_files
    
    def _generate_legacy_evidence_files(self, request: ApprovalRequest, policy: ApprovalPolicy,
                                      approvals: List[CurrentApproval], status: str,
                                      context: BlockContext) -> List[str]:
        """従来方式での証跡ファイル生成"""
        evidence_files = []
        
        if context.workspace:
            # 承認要求ファイル
            request_file = os.path.join(context.workspace, f"approval_request_{request.request_id}_{context.run_id}.json")
            with open(request_file, 'w', encoding='utf-8') as f:
                json.dump(request.dict(), f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(request_file)
            
            # 承認履歴ファイル
            history_file = os.path.join(context.workspace, f"approval_history_{request.request_id}_{context.run_id}.json")
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump([approval.dict() for approval in approvals], f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(history_file)
            
            # 承認ポリシーファイル
            policy_file = os.path.join(context.workspace, f"approval_policy_{request.request_id}_{context.run_id}.json")
            with open(policy_file, 'w', encoding='utf-8') as f:
                json.dump(policy.dict(), f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(policy_file)
        
        return evidence_files
    
    def _generate_vault_evidence_files(self, request: ApprovalRequest, policy: ApprovalPolicy,
                                     approvals: List[CurrentApproval], status: str,
                                     context: BlockContext, evidence_vault: EvidenceVault) -> List[str]:
        """Evidence Vaultを使用した証跡保存"""
        evidence_files = []
        
        # 承認要求の証跡保存
        request_evidence_id = f"approval_request_{request.request_id}_{uuid.uuid4().hex[:8]}"
        request_metadata = EvidenceMetadata(
            evidence_id=request_evidence_id,
            evidence_type=EvidenceType.APPROVAL_RECORD,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{request_evidence_id}.json",
            file_hash="",  # store_evidenceで計算
            file_size=0,   # store_evidenceで計算
            retention_until=datetime.now() + timedelta(days=2555),  # 7年保存
            tags=['approval_control', 'request', request.request_id],
            creator_user_id=request.requester,
            department=getattr(context, 'department', None),
            risk_level='high' if request.amount > 1000000 else 'medium'
        )
        
        stored_id = evidence_vault.store_evidence(request.dict(), request_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        # 承認履歴の証跡保存
        history_evidence_id = f"approval_history_{request.request_id}_{uuid.uuid4().hex[:8]}"
        history_metadata = EvidenceMetadata(
            evidence_id=history_evidence_id,
            evidence_type=EvidenceType.APPROVAL_RECORD,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{history_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['approval_control', 'history', request.request_id],
            related_evidence=[request_evidence_id]
        )
        
        history_data = {
            'approvals': [approval.dict() for approval in approvals],
            'final_status': status,
            'evaluation_timestamp': datetime.now().isoformat()
        }
        
        stored_id = evidence_vault.store_evidence(history_data, history_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        # 承認ポリシーの証跡保存
        policy_evidence_id = f"approval_policy_{request.request_id}_{uuid.uuid4().hex[:8]}"
        policy_metadata = EvidenceMetadata(
            evidence_id=policy_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{policy_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['approval_control', 'policy', 'configuration'],
            related_evidence=[request_evidence_id, history_evidence_id]
        )
        
        stored_id = evidence_vault.store_evidence(policy.dict(), policy_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        return evidence_files


