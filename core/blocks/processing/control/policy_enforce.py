"""ポリシー強制実行ブロック

Policy-as-Codeによる自動ポリシー検証と違反検知を行います。
設定されたポリシーを適用し、違反の検出と記録を実行します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import time

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError
from core.policy.engine import PolicyEngine
from core.policy.models import PolicyType, RuleSeverity
from core.evidence.vault import EvidenceVault


class PolicyEnforceBlock(ProcessingBlock):
    """ポリシー強制実行ブロック"""
    
    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """ポリシー検証の実行"""
        try:
            start_time = time.time()
            
            # 入力データの取得
            data = inputs.get('data', {})
            policy_config = inputs.get('policy_config', {})
            
            transaction_data = data.get('transaction_data', {})
            metadata = data.get('metadata', {})
            
            # ポリシーエンジンの初期化
            evidence_vault = getattr(context, 'evidence_vault', None)
            policy_engine = PolicyEngine(evidence_vault=evidence_vault)
            
            # 適用するポリシーの決定
            policies_to_evaluate = self._determine_policies(policy_engine, policy_config)
            
            if not policies_to_evaluate:
                return {
                    'policy_result': {
                        'success': True,
                        'policies_evaluated': 0,
                        'total_violations': 0,
                        'critical_violations': 0,
                        'violations': [],
                        'execution_time_ms': (time.time() - start_time) * 1000,
                        'evidence_id': None
                    },
                    'violation_summary': {
                        'violation_count_by_severity': {},
                        'violation_count_by_type': {},
                        'affected_policies': []
                    }
                }
            
            # ポリシー評価の実行
            all_violations = []
            policies_evaluated = 0
            critical_violations = 0
            
            execution_context = {
                'run_id': getattr(context, 'run_id', ''),
                'actor': getattr(context, 'user', 'system'),
                'block_id': self.__class__.__name__,
                'department': metadata.get('department'),
                'timestamp': datetime.now().isoformat()
            }
            
            for policy in policies_to_evaluate:
                try:
                    result = policy_engine.evaluate_policy(
                        policy.policy_id,
                        transaction_data,
                        execution_context
                    )
                    
                    policies_evaluated += 1
                    all_violations.extend(result.violations)
                    critical_violations += len(result.get_violations_by_severity(RuleSeverity.CRITICAL))
                    
                except Exception as e:
                    # ポリシー評価エラーをログに記録
                    import logging
                    logging.error(f"ポリシー評価エラー {policy.policy_id}: {str(e)}")
            
            # 違反チェックと処理停止判定
            fail_on_violation = policy_config.get('fail_on_violation', False)
            severity_threshold = policy_config.get('severity_threshold', 'critical')
            
            should_fail = False
            if fail_on_violation and all_violations:
                threshold_severity = RuleSeverity(severity_threshold)
                for violation in all_violations:
                    if self._is_severity_above_threshold(violation.severity, threshold_severity):
                        should_fail = True
                        break
            
            # 結果サマリの生成
            violation_summary = self._generate_violation_summary(all_violations)
            
            # 証跡保存
            evidence_id = None
            if evidence_vault:
                evidence_id = self._store_policy_evidence(
                    evidence_vault, all_violations, execution_context, context
                )
            
            # 実行結果
            execution_time_ms = (time.time() - start_time) * 1000
            
            policy_result = {
                'success': not should_fail,
                'policies_evaluated': policies_evaluated,
                'total_violations': len(all_violations),
                'critical_violations': critical_violations,
                'violations': [v.dict() for v in all_violations],
                'execution_time_ms': execution_time_ms,
                'evidence_id': evidence_id
            }
            
            # 処理停止の判定
            if should_fail:
                raise BlockExecutionError(
                    f"ポリシー違反により処理を停止しました。違反数: {len(all_violations)}, "
                    f"重要違反数: {critical_violations}"
                )
            
            return {
                'policy_result': policy_result,
                'violation_summary': violation_summary
            }
            
        except BlockExecutionError:
            raise
        except Exception as e:
            raise BlockExecutionError(f"ポリシー検証処理でエラーが発生しました: {str(e)}")
    
    def _determine_policies(self, policy_engine: PolicyEngine, policy_config: Dict[str, Any]) -> List:
        """適用するポリシーを決定"""
        policies = []
        
        # 特定のポリシーIDが指定されている場合
        policy_ids = policy_config.get('policy_ids', [])
        if policy_ids:
            for policy_id in policy_ids:
                policy = policy_engine.get_policy(policy_id)
                if policy and policy.is_effective():
                    policies.append(policy)
            return policies
        
        # ポリシータイプで絞り込み
        policy_type = policy_config.get('policy_type')
        department = policy_config.get('department')
        
        active_policies = policy_engine.get_active_policies()
        
        for policy in active_policies:
            # ポリシータイプチェック
            if policy_type and policy.policy_type != policy_type:
                continue
            
            # 部署チェック
            if department and policy.department and policy.department != department:
                continue
            
            policies.append(policy)
        
        return policies
    
    def _is_severity_above_threshold(self, violation_severity: RuleSeverity, 
                                   threshold: RuleSeverity) -> bool:
        """違反重要度が閾値を超えているかチェック"""
        severity_order = {
            RuleSeverity.INFO: 0,
            RuleSeverity.LOW: 1,
            RuleSeverity.MEDIUM: 2,
            RuleSeverity.HIGH: 3,
            RuleSeverity.CRITICAL: 4
        }
        
        return severity_order.get(violation_severity, 0) >= severity_order.get(threshold, 4)
    
    def _generate_violation_summary(self, violations: List) -> Dict[str, Any]:
        """違反サマリの生成"""
        # 重要度別集計
        violation_count_by_severity = {}
        for severity in RuleSeverity:
            count = sum(1 for v in violations if v.severity == severity)
            if count > 0:
                violation_count_by_severity[severity.value] = count
        
        # タイプ別集計
        violation_count_by_type = {}
        for violation in violations:
            vtype = violation.violation_type.value
            violation_count_by_type[vtype] = violation_count_by_type.get(vtype, 0) + 1
        
        # 影響を受けたポリシー
        affected_policies = list(set(v.policy_id for v in violations))
        
        return {
            'violation_count_by_severity': violation_count_by_severity,
            'violation_count_by_type': violation_count_by_type,
            'affected_policies': affected_policies
        }
    
    def _store_policy_evidence(self, evidence_vault: EvidenceVault, violations: List,
                             execution_context: Dict[str, Any], context: BlockContext) -> str:
        """ポリシー検証結果をEvidence Vaultに保存"""
        try:
            from core.evidence.metadata import EvidenceMetadata, EvidenceType
            from datetime import timedelta
            
            evidence_id = f"policy_enforce_{uuid.uuid4().hex[:8]}"
            
            metadata = EvidenceMetadata(
                evidence_id=evidence_id,
                evidence_type=EvidenceType.CONTROL_RESULT,
                block_id=self.__class__.__name__,
                run_id=execution_ctx.get('run_id', ''),
                timestamp=datetime.now(),
                file_path=f"evidence/policy/{datetime.now().strftime('%Y-%m-%d')}/{evidence_id}.json",
                file_hash="",
                file_size=0,
                retention_until=datetime.now() + timedelta(days=2555),
                tags=['policy_enforcement', 'compliance_check', 'control_result'],
                department=execution_ctx.get('department'),
                risk_level='high' if violations else 'low'
            )
            
            evidence_data = {
                'policy_enforcement_result': {
                    'execution_context': execution_context,
                    'violations': [v.dict() for v in violations],
                    'violation_summary': self._generate_violation_summary(violations),
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            stored_id = evidence_vault.store_evidence(evidence_data, metadata)
            return stored_id
            
        except Exception as e:
            import logging
            logging.error(f"ポリシー証跡保存エラー: {str(e)}")
            return None


