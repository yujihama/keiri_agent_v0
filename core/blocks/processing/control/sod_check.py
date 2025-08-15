"""職務分掌チェックブロック

職務分掌の検証と利益相反の検知を行います。
同一人物による複数ロール実行、非互換ロール組み合わせ、カスタム利益相反ルールのチェックを提供します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import json
import os
import uuid

from core.blocks.base import ProcessingBlock, BlockContext
from core.errors import BlockExecutionError
from core.evidence.vault import EvidenceVault
from core.evidence.metadata import EvidenceMetadata, EvidenceType


class TransactionData(BaseModel):
    """取引データ"""
    transaction_id: str
    transaction_type: str
    amount: Optional[float] = None
    initiator: str
    approver: Optional[str] = None
    processor: Optional[str] = None
    reviewer: Optional[str] = None
    timestamp: Optional[datetime] = None


class Role(BaseModel):
    """ロール定義"""
    role_id: str
    role_name: str
    permissions: List[str]


class IncompatibleRole(BaseModel):
    """非互換ロール"""
    role1: str
    role2: str
    reason: str


class SodMatrix(BaseModel):
    """職務分掌マトリックス"""
    roles: List[Role]
    incompatible_roles: List[IncompatibleRole]
    user_roles: Dict[str, List[str]]


class ConflictRule(BaseModel):
    """利益相反ルール"""
    rule_id: str
    rule_name: str
    condition: str
    severity: str  # low, medium, high, critical
    description: str


class Violation(BaseModel):
    """違反事項"""
    violation_type: str
    severity: str
    description: str
    involved_users: List[str]
    involved_roles: List[str]
    recommendation: str


class SodCheckBlock(ProcessingBlock):
    """職務分掌チェックブロック"""
    
    def execute(self, inputs: Dict[str, Any], context: BlockContext) -> Dict[str, Any]:
        """職務分掌チェックの実行"""
        try:
            # 入力データの検証と変換
            transaction = self._parse_transaction_data(inputs['transaction_data'])
            sod_matrix = SodMatrix(**inputs['sod_matrix'])
            conflict_rules = [ConflictRule(**rule) for rule in inputs.get('conflict_rules', [])]
            
            # ロール分析
            role_analysis = self._analyze_roles(transaction, sod_matrix)
            
            # 違反検知
            violations = self._detect_violations(transaction, sod_matrix, conflict_rules, role_analysis)
            
            # 状況判定
            sod_status = self._determine_sod_status(violations)
            
            # コンプライアンススコア計算
            compliance_score = self._calculate_compliance_score(violations)
            
            # 証跡ファイル生成
            evidence_files = self._generate_evidence_files(
                transaction, sod_matrix, violations, role_analysis, context
            )
            
            return {
                'sod_status': sod_status,
                'violations': [violation.dict() for violation in violations],
                'role_analysis': role_analysis,
                'compliance_score': compliance_score,
                'evidence_files': evidence_files
            }
            
        except Exception as e:
            raise BlockExecutionError(f"職務分掌チェックでエラーが発生しました: {str(e)}")
    
    def _parse_transaction_data(self, transaction_data: Dict[str, Any]) -> TransactionData:
        """取引データのパース"""
        # timestampの変換
        if isinstance(transaction_data.get('timestamp'), str):
            transaction_data['timestamp'] = datetime.fromisoformat(transaction_data['timestamp'].replace('Z', '+00:00'))
        elif transaction_data.get('timestamp') is None:
            transaction_data['timestamp'] = datetime.now()
        
        return TransactionData(**transaction_data)
    
    def _analyze_roles(self, transaction: TransactionData, sod_matrix: SodMatrix) -> Dict[str, Any]:
        """ロール分析"""
        analysis = {
            'initiator_roles': sod_matrix.user_roles.get(transaction.initiator, []),
            'approver_roles': sod_matrix.user_roles.get(transaction.approver, []) if transaction.approver else [],
            'processor_roles': sod_matrix.user_roles.get(transaction.processor, []) if transaction.processor else [],
            'reviewer_roles': sod_matrix.user_roles.get(transaction.reviewer, []) if transaction.reviewer else []
        }
        return analysis
    
    def _detect_violations(self, transaction: TransactionData, sod_matrix: SodMatrix,
                          conflict_rules: List[ConflictRule], role_analysis: Dict[str, Any]) -> List[Violation]:
        """違反検知"""
        violations = []
        
        # 同一人物による複数ロール実行チェック
        violations.extend(self._check_same_person_multiple_roles(transaction, role_analysis))
        
        # 非互換ロール組み合わせチェック
        violations.extend(self._check_incompatible_roles(transaction, sod_matrix, role_analysis))
        
        # カスタム利益相反ルールチェック
        violations.extend(self._check_conflict_rules(transaction, conflict_rules, role_analysis))
        
        return violations
    
    def _check_same_person_multiple_roles(self, transaction: TransactionData, 
                                        role_analysis: Dict[str, Any]) -> List[Violation]:
        """同一人物による複数ロール実行チェック"""
        violations = []
        users = []
        
        if transaction.initiator:
            users.append(('initiator', transaction.initiator))
        if transaction.approver:
            users.append(('approver', transaction.approver))
        if transaction.processor:
            users.append(('processor', transaction.processor))
        if transaction.reviewer:
            users.append(('reviewer', transaction.reviewer))
        
        # 同一人物チェック
        user_roles = {}
        for role_type, user in users:
            if user in user_roles:
                user_roles[user].append(role_type)
            else:
                user_roles[user] = [role_type]
        
        for user, roles in user_roles.items():
            if len(roles) > 1:
                severity = self._determine_violation_severity(roles, transaction.amount)
                violations.append(Violation(
                    violation_type='same_person_multiple_roles',
                    severity=severity,
                    description=f'同一人物 {user} が複数の役割を実行: {", ".join(roles)}',
                    involved_users=[user],
                    involved_roles=roles,
                    recommendation=self._generate_same_person_recommendation(roles, transaction.amount)
                ))
        
        return violations
    
    def _check_incompatible_roles(self, transaction: TransactionData, sod_matrix: SodMatrix,
                                role_analysis: Dict[str, Any]) -> List[Violation]:
        """非互換ロール組み合わせチェック"""
        violations = []
        
        # 全ユーザーのロールを収集
        all_user_roles = []
        for user_type, roles in role_analysis.items():
            for role in roles:
                all_user_roles.append((user_type, role))
        
        # 非互換ロールチェック
        for incompatible in sod_matrix.incompatible_roles:
            role1_found = any(role == incompatible.role1 for _, role in all_user_roles)
            role2_found = any(role == incompatible.role2 for _, role in all_user_roles)
            
            if role1_found and role2_found:
                violations.append(Violation(
                    violation_type='role_conflict',
                    severity='critical',
                    description=f'非互換ロールの組み合わせ: {incompatible.role1} と {incompatible.role2}',
                    involved_users=self._get_users_with_roles(transaction, [incompatible.role1, incompatible.role2], role_analysis),
                    involved_roles=[incompatible.role1, incompatible.role2],
                    recommendation=f'理由: {incompatible.reason}。ロール分離を実施してください'
                ))
        
        return violations
    
    def _check_conflict_rules(self, transaction: TransactionData, conflict_rules: List[ConflictRule],
                            role_analysis: Dict[str, Any]) -> List[Violation]:
        """カスタム利益相反ルールチェック"""
        violations = []
        
        for rule in conflict_rules:
            if self._evaluate_conflict_condition(rule.condition, transaction, role_analysis):
                violations.append(Violation(
                    violation_type='permission_overlap',
                    severity=rule.severity,
                    description=f'利益相反ルール違反: {rule.rule_name} - {rule.description}',
                    involved_users=self._extract_involved_users_from_transaction(transaction),
                    involved_roles=self._extract_all_roles_from_analysis(role_analysis),
                    recommendation=f'ルール {rule.rule_id} に従って適切な分離を実施してください'
                ))
        
        return violations
    
    def _determine_violation_severity(self, roles: List[str], amount: Optional[float]) -> str:
        """違反の重要度決定"""
        if amount is None:
            return 'medium'
        
        # 金額とロールの組み合わせで重要度を決定
        if amount > 10000000:  # 1000万円以上
            return 'critical'
        elif amount > 1000000:  # 100万円以上
            return 'high'
        elif len(roles) > 2:  # 3つ以上の役割
            return 'high'
        else:
            return 'medium'
    
    def _generate_same_person_recommendation(self, roles: List[str], amount: Optional[float]) -> str:
        """同一人物違反の推奨対応生成"""
        base_recommendation = "異なる担当者による役割分担を実施してください"
        
        if amount and amount > 5000000:
            return f"{base_recommendation}。高額取引のため、特に厳格な分離が必要です"
        elif 'approver' in roles and 'processor' in roles:
            return f"{base_recommendation}。承認と処理の分離は特に重要です"
        else:
            return base_recommendation
    
    def _get_users_with_roles(self, transaction: TransactionData, target_roles: List[str], 
                            role_analysis: Dict[str, Any]) -> List[str]:
        """指定されたロールを持つユーザーを取得"""
        users = []
        
        role_to_user = {
            'initiator_roles': transaction.initiator,
            'approver_roles': transaction.approver,
            'processor_roles': transaction.processor,
            'reviewer_roles': transaction.reviewer
        }
        
        for role_type, user in role_to_user.items():
            if user and role_analysis.get(role_type):
                user_roles = role_analysis[role_type]
                if any(role in target_roles for role in user_roles):
                    users.append(user)
        
        return list(set(users))  # 重複除去
    
    def _evaluate_conflict_condition(self, condition: str, transaction: TransactionData, 
                                   role_analysis: Dict[str, Any]) -> bool:
        """利益相反条件の評価"""
        try:
            # 簡易的な条件評価（実際にはより高度なパーサーが必要）
            context = {
                'transaction_type': transaction.transaction_type,
                'amount': transaction.amount or 0,
                'initiator': transaction.initiator,
                'approver': transaction.approver,
                'processor': transaction.processor,
                'reviewer': transaction.reviewer,
                'initiator_roles': role_analysis.get('initiator_roles', []),
                'approver_roles': role_analysis.get('approver_roles', []),
                'processor_roles': role_analysis.get('processor_roles', []),
                'reviewer_roles': role_analysis.get('reviewer_roles', [])
            }
            
            # 基本的な条件式を評価
            return self._safe_eval_condition(condition, context)
            
        except Exception:
            # 評価エラーの場合は False を返す
            return False
    
    def _safe_eval_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """安全な条件評価"""
        # セキュリティのため、限定的な条件のみサポート
        safe_operators = ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in']
        
        # 簡易的な条件チェック
        if 'transaction_type ==' in condition:
            parts = condition.split('==')
            if len(parts) == 2:
                field = parts[0].strip()
                value = parts[1].strip().strip('"\'')
                return context.get(field) == value
        
        if 'amount >' in condition:
            parts = condition.split('>')
            if len(parts) == 2:
                try:
                    threshold = float(parts[1].strip())
                    return (context.get('amount', 0) > threshold)
                except ValueError:
                    return False
        
        # より複雑な条件は将来的に実装
        return False
    
    def _extract_involved_users_from_transaction(self, transaction: TransactionData) -> List[str]:
        """取引から関与ユーザーを抽出"""
        users = []
        for user in [transaction.initiator, transaction.approver, transaction.processor, transaction.reviewer]:
            if user:
                users.append(user)
        return list(set(users))
    
    def _extract_all_roles_from_analysis(self, role_analysis: Dict[str, Any]) -> List[str]:
        """ロール分析から全ロールを抽出"""
        all_roles = []
        for roles in role_analysis.values():
            if isinstance(roles, list):
                all_roles.extend(roles)
        return list(set(all_roles))
    
    def _determine_sod_status(self, violations: List[Violation]) -> str:
        """職務分掌状況の判定"""
        if not violations:
            return 'compliant'
        
        critical_violations = [v for v in violations if v.severity == 'critical']
        high_violations = [v for v in violations if v.severity == 'high']
        
        if critical_violations or high_violations:
            return 'violation'
        else:
            return 'warning'
    
    def _calculate_compliance_score(self, violations: List[Violation]) -> float:
        """コンプライアンススコア計算"""
        if not violations:
            return 100.0
        
        severity_weights = {
            'low': 5,
            'medium': 15,
            'high': 30,
            'critical': 50
        }
        
        total_deduction = sum(severity_weights.get(v.severity, 0) for v in violations)
        score = max(0, 100 - total_deduction)
        
        return score
    
    def _generate_evidence_files(self, transaction: TransactionData, sod_matrix: SodMatrix,
                               violations: List[Violation], role_analysis: Dict[str, Any],
                               context: BlockContext) -> List[str]:
        """証跡ファイルの生成"""
        evidence_files = []
        
        try:
            # Evidence Vaultの取得
            evidence_vault = getattr(context, 'evidence_vault', None)
            if not evidence_vault:
                # Evidence Vaultが設定されていない場合は従来の方式でファイル保存
                evidence_files = self._generate_legacy_evidence_files(transaction, sod_matrix, violations, role_analysis, context)
            else:
                # Evidence Vaultを使用した証跡保存
                evidence_files = self._generate_vault_evidence_files(transaction, sod_matrix, violations, role_analysis, context, evidence_vault)
        
        except Exception as e:
            # 証跡生成失敗時は警告ログを出力するが処理は継続
            import logging
            logging.warning(f"証跡ファイル生成でエラーが発生しました: {str(e)}")
            evidence_files = []
        
        return evidence_files
    
    def _generate_legacy_evidence_files(self, transaction: TransactionData, sod_matrix: SodMatrix,
                                      violations: List[Violation], role_analysis: Dict[str, Any],
                                      context: BlockContext) -> List[str]:
        """従来方式での証跡ファイル生成"""
        evidence_files = []
        
        if context.workspace:
            # 取引データファイル
            transaction_file = os.path.join(context.workspace, f"sod_transaction_{transaction.transaction_id}_{context.run_id}.json")
            with open(transaction_file, 'w', encoding='utf-8') as f:
                json.dump(transaction.dict(), f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(transaction_file)
            
            # 違反結果ファイル
            violations_file = os.path.join(context.workspace, f"sod_violations_{transaction.transaction_id}_{context.run_id}.json")
            with open(violations_file, 'w', encoding='utf-8') as f:
                json.dump([v.dict() for v in violations], f, ensure_ascii=False, indent=2, default=str)
            evidence_files.append(violations_file)
            
            # ロール分析ファイル
            analysis_file = os.path.join(context.workspace, f"sod_analysis_{transaction.transaction_id}_{context.run_id}.json")
            with open(analysis_file, 'w', encoding='utf-8') as f:
                json.dump(role_analysis, f, ensure_ascii=False, indent=2)
            evidence_files.append(analysis_file)
        
        return evidence_files
    
    def _generate_vault_evidence_files(self, transaction: TransactionData, sod_matrix: SodMatrix,
                                     violations: List[Violation], role_analysis: Dict[str, Any],
                                     context: BlockContext, evidence_vault: EvidenceVault) -> List[str]:
        """Evidence Vaultを使用した証跡保存"""
        evidence_files = []
        
        # 取引データの証跡保存
        transaction_evidence_id = f"sod_transaction_{transaction.transaction_id}_{uuid.uuid4().hex[:8]}"
        transaction_metadata = EvidenceMetadata(
            evidence_id=transaction_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{transaction_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['sod_control', 'transaction', transaction.transaction_id],
            creator_user_id=transaction.initiator,
            department=getattr(context, 'department', None),
            risk_level='high' if violations else 'medium'
        )
        
        stored_id = evidence_vault.store_evidence(transaction.dict(), transaction_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        # 違反結果の証跡保存
        violations_evidence_id = f"sod_violations_{transaction.transaction_id}_{uuid.uuid4().hex[:8]}"
        violations_metadata = EvidenceMetadata(
            evidence_id=violations_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{violations_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['sod_control', 'violations', transaction.transaction_id],
            related_evidence=[transaction_evidence_id]
        )
        
        violations_data = {
            'violations': [v.dict() for v in violations],
            'compliance_score': self._calculate_compliance_score(violations),
            'evaluation_timestamp': datetime.now().isoformat()
        }
        
        stored_id = evidence_vault.store_evidence(violations_data, violations_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        # ロール分析の証跡保存
        analysis_evidence_id = f"sod_analysis_{transaction.transaction_id}_{uuid.uuid4().hex[:8]}"
        analysis_metadata = EvidenceMetadata(
            evidence_id=analysis_evidence_id,
            evidence_type=EvidenceType.CONTROL_RESULT,
            block_id=self.__class__.__name__,
            run_id=context.run_id,
            timestamp=datetime.now(),
            file_path=f"evidence/control/{context.run_id}/{analysis_evidence_id}.json",
            file_hash="",
            file_size=0,
            retention_until=datetime.now() + timedelta(days=2555),
            tags=['sod_control', 'analysis', transaction.transaction_id],
            related_evidence=[transaction_evidence_id, violations_evidence_id]
        )
        
        stored_id = evidence_vault.store_evidence(role_analysis, analysis_metadata)
        evidence_files.append(f"vault:{stored_id}")
        
        return evidence_files


