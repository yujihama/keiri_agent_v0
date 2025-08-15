"""監査ダッシュボード

監査人・レビューワー向けのダッシュボード機能を提供します。
証跡統計、違反サマリ、リスク指標などを可視化します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from pathlib import Path

from core.evidence.vault import EvidenceVault
from core.policy.engine import PolicyEngine
from core.policy.models import RuleSeverity, ViolationType
from core.ui.auth import auth_manager, Permission


class ReviewerDashboard:
    """監査ダッシュボード"""
    
    def __init__(self, evidence_vault: EvidenceVault, policy_engine: PolicyEngine):
        """
        ダッシュボードの初期化
        
        Args:
            evidence_vault: Evidence Vault
            policy_engine: ポリシーエンジン
        """
        self.evidence_vault = evidence_vault
        self.policy_engine = policy_engine
    
    def render(self) -> None:
        """ダッシュボードの描画"""
        # 権限チェック
        auth_manager.require_permission(Permission.AUDIT_REVIEW)
        
        st.title("🔍 監査ダッシュボード")
        st.markdown("---")
        
        # 期間選択
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input(
                "開始日",
                value=datetime.now().date() - timedelta(days=30)
            )
        with col2:
            end_date = st.date_input(
                "終了日", 
                value=datetime.now().date()
            )
        
        # データ取得
        try:
            stats = self._get_dashboard_stats(start_date, end_date)
            
            # サマリメトリクス
            self._render_summary_metrics(stats)
            
            st.markdown("---")
            
            # チャート表示
            col1, col2 = st.columns(2)
            
            with col1:
                self._render_violation_trends(stats)
                self._render_evidence_types(stats)
            
            with col2:
                self._render_severity_distribution(stats)
                self._render_policy_compliance(stats)
            
            # 詳細テーブル
            st.markdown("---")
            self._render_recent_violations(stats)
            
        except Exception as e:
            st.error(f"ダッシュボードデータの取得に失敗しました: {str(e)}")
    
    def _get_dashboard_stats(self, start_date, end_date) -> Dict[str, Any]:
        """ダッシュボード統計データの取得"""
        stats = {
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'evidence': {
                'total_count': 0,
                'by_type': {},
                'by_date': {},
                'total_size_mb': 0
            },
            'violations': {
                'total_count': 0,
                'by_severity': {},
                'by_type': {},
                'by_date': {},
                'recent_violations': []
            },
            'policies': {
                'total_policies': 0,
                'active_policies': 0,
                'compliance_rate': 0
            }
        }
        
        try:
            # Evidence Vault統計
            vault_stats = self.evidence_vault.get_statistics()
            stats['evidence'].update({
                'total_count': vault_stats.total_evidence_count,
                'total_size_mb': vault_stats.total_data_size_mb
            })
            
            # 期間内の証跡検索
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            evidence_list = self.evidence_vault.search_evidence({
                'date_from': start_datetime,
                'date_to': end_datetime
            })
            
            # 証跡タイプ別集計
            type_counts = {}
            date_counts = {}
            
            for evidence in evidence_list:
                # タイプ別
                etype = evidence.evidence_type.value
                type_counts[etype] = type_counts.get(etype, 0) + 1
                
                # 日付別
                date_key = evidence.timestamp.date().isoformat()
                date_counts[date_key] = date_counts.get(date_key, 0) + 1
            
            stats['evidence']['by_type'] = type_counts
            stats['evidence']['by_date'] = date_counts
            
            # ポリシー統計
            all_policies = list(self.policy_engine.policies.values())
            active_policies = self.policy_engine.get_active_policies()
            
            stats['policies'].update({
                'total_policies': len(all_policies),
                'active_policies': len(active_policies),
                'compliance_rate': 95.2  # 実際の実装では計算
            })
            
            # 違反統計（サンプルデータ）
            stats['violations'].update({
                'total_count': 23,
                'by_severity': {
                    'critical': 2,
                    'high': 5,
                    'medium': 10,
                    'low': 6
                },
                'by_type': {
                    'threshold_exceeded': 8,
                    'missing_approval': 6,
                    'segregation_duty': 4,
                    'rule_violation': 5
                },
                'by_date': {
                    (datetime.now() - timedelta(days=i)).date().isoformat(): max(0, 5 - i)
                    for i in range(7)
                }
            })
            
        except Exception as e:
            st.warning(f"統計データの取得でエラーが発生しました: {str(e)}")
        
        return stats
    
    def _render_summary_metrics(self, stats: Dict[str, Any]) -> None:
        """サマリメトリクスの表示"""
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "総証跡数",
                stats['evidence']['total_count'],
                delta=f"+{stats['evidence'].get('growth', 15)}%"
            )
        
        with col2:
            st.metric(
                "ポリシー違反",
                stats['violations']['total_count'],
                delta=f"-{3}" if stats['violations']['total_count'] < 30 else f"+{2}",
                delta_color="inverse"
            )
        
        with col3:
            st.metric(
                "コンプライアンス率",
                f"{stats['policies']['compliance_rate']:.1f}%",
                delta=f"+{0.5}%"
            )
        
        with col4:
            st.metric(
                "アクティブポリシー",
                stats['policies']['active_policies'],
                delta=f"/{stats['policies']['total_policies']}"
            )
    
    def _render_violation_trends(self, stats: Dict[str, Any]) -> None:
        """違反トレンドチャート"""
        st.subheader("📈 違反トレンド")
        
        # データ準備
        violation_by_date = stats['violations']['by_date']
        dates = list(violation_by_date.keys())
        counts = list(violation_by_date.values())
        
        if dates and counts:
            df = pd.DataFrame({
                'date': pd.to_datetime(dates),
                'violations': counts
            })
            
            fig = px.line(
                df, 
                x='date', 
                y='violations',
                title='日別違反数推移',
                markers=True
            )
            fig.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("期間内の違反データがありません。")
    
    def _render_severity_distribution(self, stats: Dict[str, Any]) -> None:
        """重要度分布チャート"""
        st.subheader("⚠️ 違反重要度分布")
        
        severity_data = stats['violations']['by_severity']
        
        if severity_data:
            labels = list(severity_data.keys())
            values = list(severity_data.values())
            
            # 色分け
            colors = {
                'critical': '#FF4B4B',
                'high': '#FF8C00',
                'medium': '#FFD700',
                'low': '#32CD32'
            }
            
            fig = go.Figure(data=[go.Pie(
                labels=labels,
                values=values,
                marker_colors=[colors.get(label, '#1f77b4') for label in labels],
                textinfo='label+percent'
            )])
            
            fig.update_layout(
                title='重要度別違反数',
                height=300,
                showlegend=False
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("違反データがありません。")
    
    def _render_evidence_types(self, stats: Dict[str, Any]) -> None:
        """証跡タイプ分布"""
        st.subheader("📊 証跡タイプ分布")
        
        evidence_types = stats['evidence']['by_type']
        
        if evidence_types:
            df = pd.DataFrame(list(evidence_types.items()), columns=['Type', 'Count'])
            
            fig = px.bar(
                df,
                x='Type',
                y='Count',
                title='証跡タイプ別件数'
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("証跡データがありません。")
    
    def _render_policy_compliance(self, stats: Dict[str, Any]) -> None:
        """ポリシーコンプライアンス"""
        st.subheader("✅ ポリシーコンプライアンス")
        
        compliance_rate = stats['policies']['compliance_rate']
        
        # ゲージチャート
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=compliance_rate,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': "コンプライアンス率 (%)"},
            delta={'reference': 90},
            gauge={
                'axis': {'range': [None, 100]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 80], 'color': "gray"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            }
        ))
        
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    
    def _render_recent_violations(self, stats: Dict[str, Any]) -> None:
        """最近の違反一覧"""
        st.subheader("🚨 最近の違反")
        
        # サンプルデータ（実際の実装ではデータベースから取得）
        recent_violations = [
            {
                'date': '2024-01-15',
                'policy': '購買承認ポリシー',
                'severity': 'high',
                'type': 'missing_approval',
                'description': '100万円以上の購買に対する部長承認が不足',
                'department': '購買部',
                'status': 'open'
            },
            {
                'date': '2024-01-14',
                'policy': '支払いポリシー',
                'severity': 'medium',
                'type': 'threshold_exceeded',
                'description': '日次支払い限度額を超過',
                'department': '財務部',
                'status': 'resolved'
            },
            {
                'date': '2024-01-13',
                'policy': '職務分掌ポリシー',
                'severity': 'critical',
                'type': 'segregation_duty',
                'description': '申請者と承認者が同一人物',
                'department': '総務部',
                'status': 'open'
            }
        ]
        
        if recent_violations:
            df = pd.DataFrame(recent_violations)
            
            # 重要度に応じた色付け
            def get_severity_color(severity):
                colors = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢'
                }
                return colors.get(severity, '⚪')
            
            df['severity_icon'] = df['severity'].apply(get_severity_color)
            
            # 表示用データフレーム作成
            display_df = df[['date', 'severity_icon', 'policy', 'description', 'department', 'status']].copy()
            display_df.columns = ['日付', '重要度', 'ポリシー', '説明', '部署', 'ステータス']
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # ダウンロードボタン
            csv = df.to_csv(index=False)
            st.download_button(
                label="CSV ダウンロード",
                data=csv,
                file_name=f"violations_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        else:
            st.info("最近の違反データがありません。")