# Reviewer Workspace 詳細設計

## 概要

Reviewer Workspaceは、監査人・レビューワー向けの専用ユーザーインターフェースです。既存のStreamlit UI（app.py）を拡張し、監査・内部統制業務に特化した機能を提供します。Control Blocks、Evidence Vault、Policy-as-Codeと連携し、効率的な監査プロセスを実現します。

## 設計原則

### 1. 監査人中心の設計
- 監査プロセスに最適化されたワークフロー
- 直感的で効率的なユーザーインターフェース
- 監査基準・規制要件への準拠

### 2. 既存アーキテクチャとの統合
- 既存のStreamlit UI（app.py）の拡張
- `core/ui/`モジュールとの連携
- セッション状態管理の強化

### 3. 証跡管理との統合
- Evidence Vaultとのシームレス連携
- リアルタイム証跡表示
- 監査証跡の完全性確認

### 4. ユーザビリティ重視
- ごちゃごちゃ感のないクリーンなデザイン
- 絵文字の使用を控えたプロフェッショナルな外観
- レスポンシブデザイン対応

## アーキテクチャ設計

### 1. UI構造拡張

#### 既存app.pyの拡張
```python
# app.py の拡張
import streamlit as st
from pathlib import Path
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from core.ui.reviewer_workspace import ReviewerWorkspace
from core.ui.admin_panel import AdminPanel
from core.ui.audit_dashboard import AuditDashboard

def main():
    st.set_page_config(
        page_title="Keiri Agent - 監査・内部統制プラットフォーム",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # カスタムCSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: 600;
        color: #1f2937;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }
    .status-success { color: #059669; }
    .status-warning { color: #d97706; }
    .status-error { color: #dc2626; }
    </style>
    """, unsafe_allow_html=True)
    
    # サイドバーナビゲーション
    with st.sidebar:
        st.title("Keiri Agent")
        
        # ユーザー認証（簡易版）
        user_role = st.selectbox(
            "ユーザーロール",
            ["監査人", "レビューワー", "管理者", "一般ユーザー"]
        )
        
        # ナビゲーションメニュー
        if user_role in ["監査人", "レビューワー"]:
            page = st.selectbox(
                "ページ選択",
                [
                    "監査ダッシュボード",
                    "レビューワークスペース", 
                    "証跡管理",
                    "ポリシー管理",
                    "レポート生成"
                ]
            )
        elif user_role == "管理者":
            page = st.selectbox(
                "ページ選択",
                [
                    "管理者パネル",
                    "システム設定",
                    "ユーザー管理",
                    "ポリシー設定"
                ]
            )
        else:
            page = st.selectbox(
                "ページ選択",
                [
                    "プラン実行",
                    "結果確認"
                ]
            )
    
    # メインコンテンツ
    if page == "レビューワークスペース":
        reviewer_workspace = ReviewerWorkspace()
        reviewer_workspace.render()
    elif page == "監査ダッシュボード":
        audit_dashboard = AuditDashboard()
        audit_dashboard.render()
    elif page == "管理者パネル":
        admin_panel = AdminPanel()
        admin_panel.render()
    else:
        # 既存の機能
        render_default_interface()

def render_default_interface():
    """既存のデフォルトインターフェース"""
    st.markdown('<h1 class="main-header">Keiri Agent</h1>', unsafe_allow_html=True)
    
    # 既存のプラン実行機能
    st.subheader("プラン実行")
    # ... 既存のコード ...

if __name__ == "__main__":
    main()
```

### 2. ReviewerWorkspace実装

#### 基本構造
```python
# core/ui/reviewer_workspace.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json
from pathlib import Path

from core.evidence.vault import EvidenceVault
from core.policy.engine import PolicyEngine
from core.ui.components import (
    EvidenceViewer, PolicyViewer, AuditTrailViewer,
    ComplianceScorecard, ViolationSummary
)

class ReviewerWorkspace:
    """レビューワー専用ワークスペース"""
    
    def __init__(self):
        self.evidence_vault = self._initialize_evidence_vault()
        self.policy_engine = self._initialize_policy_engine()
        
    def _initialize_evidence_vault(self) -> Optional[EvidenceVault]:
        """Evidence Vaultの初期化"""
        try:
            vault_path = st.session_state.get('vault_path', './workspace/evidence_vault')
            return EvidenceVault(vault_path)
        except Exception as e:
            st.error(f"Evidence Vault初期化エラー: {e}")
            return None
    
    def _initialize_policy_engine(self) -> Optional[PolicyEngine]:
        """Policy Engineの初期化"""
        try:
            policy_path = st.session_state.get('policy_path', './designs/policies')
            return PolicyEngine(policy_path)
        except Exception as e:
            st.error(f"Policy Engine初期化エラー: {e}")
            return None
    
    def render(self):
        """メインレンダリング"""
        st.markdown('<h1 class="main-header">レビューワークスペース</h1>', unsafe_allow_html=True)
        
        # タブ構成
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "ダッシュボード", "監査レビュー", "証跡管理", "ポリシー確認", "レポート生成"
        ])
        
        with tab1:
            self._render_dashboard()
        
        with tab2:
            self._render_audit_review()
        
        with tab3:
            self._render_evidence_management()
        
        with tab4:
            self._render_policy_review()
        
        with tab5:
            self._render_report_generation()
    
    def _render_dashboard(self):
        """ダッシュボード表示"""
        st.subheader("監査ダッシュボード")
        
        # メトリクス表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div class="metric-card">
                <h3>進行中の監査</h3>
                <h2 class="status-warning">5</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="metric-card">
                <h3>完了した監査</h3>
                <h2 class="status-success">23</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="metric-card">
                <h3>ポリシー違反</h3>
                <h2 class="status-error">3</h2>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
            <div class="metric-card">
                <h3>コンプライアンススコア</h3>
                <h2 class="status-success">87%</h2>
            </div>
            """, unsafe_allow_html=True)
        
        # 最近のアクティビティ
        st.subheader("最近のアクティビティ")
        
        activities = [
            {
                "時刻": "2025-01-15 14:30",
                "アクション": "承認統制テスト完了",
                "ステータス": "成功",
                "詳細": "財務部門 - 支払承認プロセス"
            },
            {
                "時刻": "2025-01-15 13:45", 
                "アクション": "ポリシー違反検知",
                "ステータス": "警告",
                "詳細": "職務分掌違反 - 同一人物による承認"
            },
            {
                "時刻": "2025-01-15 12:15",
                "アクション": "証跡保存完了",
                "ステータス": "成功", 
                "詳細": "月次決算プロセス - 全証跡暗号化済み"
            }
        ]
        
        df_activities = pd.DataFrame(activities)
        st.dataframe(df_activities, use_container_width=True)
        
        # 監査進捗チャート
        st.subheader("監査進捗")
        
        progress_data = {
            "監査項目": ["承認統制", "職務分掌", "データ品質", "アクセス制御", "変更管理"],
            "進捗率": [85, 70, 95, 60, 40],
            "ステータス": ["進行中", "進行中", "完了", "進行中", "開始前"]
        }
        
        df_progress = pd.DataFrame(progress_data)
        
        for idx, row in df_progress.iterrows():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(row["監査項目"])
            with col2:
                st.progress(row["進捗率"] / 100)
            with col3:
                status_class = {
                    "完了": "status-success",
                    "進行中": "status-warning", 
                    "開始前": "status-error"
                }.get(row["ステータス"], "")
                st.markdown(f'<span class="{status_class}">{row["ステータス"]}</span>', 
                          unsafe_allow_html=True)
    
    def _render_audit_review(self):
        """監査レビュー画面"""
        st.subheader("監査レビュー")
        
        # 監査セッション選択
        col1, col2 = st.columns([2, 1])
        
        with col1:
            audit_sessions = [
                "audit_2025_q1_finance_001",
                "audit_2025_q1_hr_002", 
                "audit_2025_q1_it_003"
            ]
            selected_session = st.selectbox("監査セッション", audit_sessions)
        
        with col2:
            if st.button("新規監査開始", type="primary"):
                self._start_new_audit()
        
        if selected_session:
            # 監査詳細情報
            audit_info = self._get_audit_info(selected_session)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("監査情報")
                st.write(f"**セッションID**: {audit_info['session_id']}")
                st.write(f"**部門**: {audit_info['department']}")
                st.write(f"**監査人**: {audit_info['auditor']}")
                st.write(f"**開始日**: {audit_info['start_date']}")
                st.write(f"**ステータス**: {audit_info['status']}")
            
            with col2:
                st.subheader("統制テスト結果")
                
                # コンプライアンススコアカード
                compliance_scorecard = ComplianceScorecard(audit_info['compliance_results'])
                compliance_scorecard.render()
            
            # 違反サマリー
            st.subheader("発見事項")
            violation_summary = ViolationSummary(audit_info['violations'])
            violation_summary.render()
            
            # アクションボタン
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("証跡確認"):
                    st.session_state['show_evidence'] = True
            
            with col2:
                if st.button("レポート生成"):
                    self._generate_audit_report(selected_session)
            
            with col3:
                if st.button("承認"):
                    self._approve_audit(selected_session)
            
            with col4:
                if st.button("差し戻し"):
                    self._reject_audit(selected_session)
    
    def _render_evidence_management(self):
        """証跡管理画面"""
        st.subheader("証跡管理")
        
        if not self.evidence_vault:
            st.error("Evidence Vaultが利用できません")
            return
        
        # 検索フィルター
        with st.expander("検索フィルター", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                search_run_id = st.text_input("実行ID")
                search_block_id = st.text_input("ブロックID")
            
            with col2:
                search_evidence_type = st.selectbox(
                    "証跡タイプ",
                    ["", "input", "output", "control_result", "audit_finding"]
                )
                search_date_from = st.date_input("開始日")
            
            with col3:
                search_tags = st.text_input("タグ（カンマ区切り）")
                search_date_to = st.date_input("終了日")
            
            if st.button("検索実行"):
                search_criteria = {
                    "run_id": search_run_id if search_run_id else None,
                    "block_id": search_block_id if search_block_id else None,
                    "evidence_type": search_evidence_type if search_evidence_type else None,
                    "date_from": search_date_from.isoformat() if search_date_from else None,
                    "date_to": search_date_to.isoformat() if search_date_to else None,
                    "tags": [tag.strip() for tag in search_tags.split(",")] if search_tags else None
                }
                
                # 検索結果をセッション状態に保存
                st.session_state['evidence_search_results'] = self._search_evidence(search_criteria)
        
        # 検索結果表示
        if 'evidence_search_results' in st.session_state:
            results = st.session_state['evidence_search_results']
            
            if results:
                st.subheader(f"検索結果 ({len(results)}件)")
                
                # 結果テーブル
                df_results = pd.DataFrame(results)
                
                # 選択可能なデータフレーム
                selected_indices = st.multiselect(
                    "証跡を選択",
                    range(len(df_results)),
                    format_func=lambda x: f"{df_results.iloc[x]['evidence_id']} - {df_results.iloc[x]['evidence_type']}"
                )
                
                st.dataframe(df_results, use_container_width=True)
                
                # 選択された証跡の詳細表示
                if selected_indices:
                    for idx in selected_indices:
                        evidence_id = df_results.iloc[idx]['evidence_id']
                        self._render_evidence_detail(evidence_id)
            else:
                st.info("検索条件に一致する証跡が見つかりませんでした")
    
    def _render_policy_review(self):
        """ポリシー確認画面"""
        st.subheader("ポリシー確認")
        
        if not self.policy_engine:
            st.error("Policy Engineが利用できません")
            return
        
        # ポリシー一覧
        policies = list(self.policy_engine.loaded_policies.keys())
        
        if policies:
            selected_policy = st.selectbox("ポリシー選択", policies)
            
            if selected_policy:
                policy = self.policy_engine.loaded_policies[selected_policy]
                
                # ポリシー詳細表示
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("ポリシー情報")
                    st.write(f"**名前**: {policy.metadata.name}")
                    st.write(f"**バージョン**: {policy.metadata.version}")
                    st.write(f"**有効期間**: {policy.metadata.effective_date}")
                    st.write(f"**所有者**: {policy.metadata.owner}")
                    st.write(f"**説明**: {policy.metadata.description}")
                
                with col2:
                    st.subheader("適用範囲")
                    scope = policy.spec.get('scope', {})
                    applies_to = scope.get('applies_to', {})
                    
                    if 'plan_types' in applies_to:
                        st.write(f"**プランタイプ**: {', '.join(applies_to['plan_types'])}")
                    if 'departments' in applies_to:
                        st.write(f"**部門**: {', '.join(applies_to['departments'])}")
                    if 'risk_levels' in applies_to:
                        st.write(f"**リスクレベル**: {', '.join(applies_to['risk_levels'])}")
                
                # ポリシールール表示
                st.subheader("ポリシールール")
                
                policies_spec = policy.spec.get('policies', {})
                for section_name, section_data in policies_spec.items():
                    with st.expander(f"{section_data['name']}", expanded=False):
                        st.write(section_data['description'])
                        
                        for rule in section_data['rules']:
                            st.markdown(f"**ルールID**: {rule['rule_id']}")
                            st.markdown(f"**条件**: `{rule['condition']}`")
                            st.markdown(f"**実行レベル**: {rule['enforcement']}")
                            st.markdown(f"**違反時アクション**: {rule['violation_action']}")
                            
                            if 'requirement' in rule:
                                st.json(rule['requirement'])
                            
                            st.markdown("---")
        else:
            st.info("利用可能なポリシーがありません")
    
    def _render_report_generation(self):
        """レポート生成画面"""
        st.subheader("レポート生成")
        
        # レポートタイプ選択
        report_type = st.selectbox(
            "レポートタイプ",
            [
                "監査サマリーレポート",
                "コンプライアンスレポート", 
                "ポリシー違反レポート",
                "証跡完全性レポート",
                "統制有効性レポート"
            ]
        )
        
        # レポート設定
        with st.expander("レポート設定", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                report_period_start = st.date_input("期間開始")
                report_departments = st.multiselect(
                    "対象部門",
                    ["finance", "hr", "it", "procurement", "sales"]
                )
            
            with col2:
                report_period_end = st.date_input("期間終了")
                report_format = st.selectbox(
                    "出力形式",
                    ["Excel", "PDF", "HTML"]
                )
        
        # 詳細設定
        include_evidence_links = st.checkbox("証跡リンクを含める", value=True)
        include_recommendations = st.checkbox("推奨事項を含める", value=True)
        confidential_mode = st.checkbox("機密情報をマスク", value=False)
        
        # レポート生成実行
        if st.button("レポート生成", type="primary"):
            with st.spinner("レポートを生成中..."):
                report_config = {
                    "type": report_type,
                    "period_start": report_period_start.isoformat(),
                    "period_end": report_period_end.isoformat(),
                    "departments": report_departments,
                    "format": report_format,
                    "include_evidence_links": include_evidence_links,
                    "include_recommendations": include_recommendations,
                    "confidential_mode": confidential_mode
                }
                
                report_result = self._generate_report(report_config)
                
                if report_result:
                    st.success("レポートが正常に生成されました")
                    
                    # ダウンロードリンク
                    with open(report_result['file_path'], 'rb') as f:
                        st.download_button(
                            label="レポートをダウンロード",
                            data=f.read(),
                            file_name=report_result['file_name'],
                            mime=report_result['mime_type']
                        )
                    
                    # プレビュー（HTML形式の場合）
                    if report_format == "HTML":
                        with st.expander("レポートプレビュー"):
                            with open(report_result['file_path'], 'r', encoding='utf-8') as f:
                                st.markdown(f.read(), unsafe_allow_html=True)
                else:
                    st.error("レポート生成に失敗しました")
```


### 3. UIコンポーネント実装

#### ComplianceScorecard
```python
# core/ui/components/compliance_scorecard.py
import streamlit as st
import plotly.graph_objects as go
from typing import Dict, Any

class ComplianceScorecard:
    """コンプライアンススコアカード"""
    
    def __init__(self, compliance_data: Dict[str, Any]):
        self.compliance_data = compliance_data
    
    def render(self):
        """スコアカードの表示"""
        overall_score = self.compliance_data.get('overall_score', 0)
        
        # 総合スコアゲージ
        fig = go.Figure(go.Indicator(
            mode = "gauge+number+delta",
            value = overall_score,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "総合コンプライアンススコア"},
            delta = {'reference': 90},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': self._get_score_color(overall_score)},
                'steps': [
                    {'range': [0, 50], 'color': "lightgray"},
                    {'range': [50, 80], 'color': "yellow"},
                    {'range': [80, 100], 'color': "lightgreen"}
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
        
        # 領域別スコア
        area_scores = self.compliance_data.get('area_scores', {})
        if area_scores:
            st.subheader("領域別スコア")
            
            for area, score in area_scores.items():
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.write(self._translate_area(area))
                
                with col2:
                    st.progress(score / 100)
                
                with col3:
                    color_class = self._get_score_color_class(score)
                    st.markdown(f'<span class="{color_class}">{score}%</span>', 
                              unsafe_allow_html=True)
    
    def _get_score_color(self, score: float) -> str:
        """スコアに基づく色の取得"""
        if score >= 90:
            return "green"
        elif score >= 70:
            return "yellow"
        else:
            return "red"
    
    def _get_score_color_class(self, score: float) -> str:
        """スコアに基づくCSSクラスの取得"""
        if score >= 90:
            return "status-success"
        elif score >= 70:
            return "status-warning"
        else:
            return "status-error"
    
    def _translate_area(self, area: str) -> str:
        """領域名の日本語変換"""
        translations = {
            "approval_control": "承認統制",
            "segregation_of_duties": "職務分掌",
            "data_quality": "データ品質",
            "access_control": "アクセス制御",
            "change_management": "変更管理"
        }
        return translations.get(area, area)

class ViolationSummary:
    """違反サマリー"""
    
    def __init__(self, violations: list):
        self.violations = violations
    
    def render(self):
        """違反サマリーの表示"""
        if not self.violations:
            st.success("違反事項はありません")
            return
        
        # 重要度別集計
        severity_counts = {}
        for violation in self.violations:
            severity = violation.get('severity', 'unknown')
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # 重要度別表示
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            critical_count = severity_counts.get('critical', 0)
            st.metric("重大", critical_count, delta=None)
        
        with col2:
            high_count = severity_counts.get('high', 0)
            st.metric("高", high_count, delta=None)
        
        with col3:
            medium_count = severity_counts.get('medium', 0)
            st.metric("中", medium_count, delta=None)
        
        with col4:
            low_count = severity_counts.get('low', 0)
            st.metric("低", low_count, delta=None)
        
        # 違反詳細リスト
        st.subheader("違反詳細")
        
        for i, violation in enumerate(self.violations):
            with st.expander(f"違反 {i+1}: {violation.get('rule_id', 'Unknown')}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**ルールID**: {violation.get('rule_id', 'N/A')}")
                    st.write(f"**ポリシー**: {violation.get('policy_name', 'N/A')}")
                    st.write(f"**重要度**: {violation.get('severity', 'N/A')}")
                
                with col2:
                    st.write(f"**発生時刻**: {violation.get('timestamp', 'N/A')}")
                    st.write(f"**アクション**: {violation.get('action_taken', 'N/A')}")
                
                st.write(f"**説明**: {violation.get('description', 'N/A')}")
                
                # コンテキスト情報
                if 'context' in violation:
                    st.json(violation['context'])

class EvidenceViewer:
    """証跡ビューワー"""
    
    def __init__(self, evidence_vault):
        self.evidence_vault = evidence_vault
    
    def render_evidence_detail(self, evidence_id: str):
        """証跡詳細の表示"""
        try:
            evidence_data, metadata = self.evidence_vault.retrieve_evidence(evidence_id)
            
            st.subheader(f"証跡詳細: {evidence_id}")
            
            # メタデータ表示
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**証跡ID**: {metadata.evidence_id}")
                st.write(f"**タイプ**: {metadata.evidence_type}")
                st.write(f"**ブロックID**: {metadata.block_id}")
                st.write(f"**実行ID**: {metadata.run_id}")
            
            with col2:
                st.write(f"**作成日時**: {metadata.timestamp}")
                st.write(f"**ファイルサイズ**: {metadata.file_size} bytes")
                st.write(f"**ハッシュ**: {metadata.file_hash[:16]}...")
                st.write(f"**保存期限**: {metadata.retention_until}")
            
            # タグ表示
            if metadata.tags:
                st.write(f"**タグ**: {', '.join(metadata.tags)}")
            
            # データ内容表示
            st.subheader("データ内容")
            
            if isinstance(evidence_data, dict):
                st.json(evidence_data)
            elif isinstance(evidence_data, str):
                st.text(evidence_data)
            else:
                st.write("バイナリデータ")
            
            # 関連証跡
            if metadata.related_evidence:
                st.subheader("関連証跡")
                for related_id in metadata.related_evidence:
                    if st.button(f"証跡 {related_id} を表示", key=f"related_{related_id}"):
                        st.session_state[f'show_evidence_{related_id}'] = True
            
        except Exception as e:
            st.error(f"証跡取得エラー: {e}")

class AuditTrailViewer:
    """監査証跡ビューワー"""
    
    def __init__(self, evidence_vault):
        self.evidence_vault = evidence_vault
    
    def render_audit_trail(self, run_id: str):
        """監査証跡の表示"""
        try:
            audit_file = self.evidence_vault.vault_path / 'audit_trail' / f"{run_id}_audit.jsonl"
            
            if not audit_file.exists():
                st.warning("監査証跡が見つかりません")
                return
            
            st.subheader(f"監査証跡: {run_id}")
            
            # 証跡エントリの読み込み
            entries = []
            with open(audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    entries.append(json.loads(line))
            
            # 時系列表示
            for entry in entries:
                with st.expander(f"{entry['timestamp']} - {entry['event_type']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write(f"**イベントタイプ**: {entry['event_type']}")
                        st.write(f"**ブロックID**: {entry['block_id']}")
                        st.write(f"**ステータス**: {entry['status']}")
                        st.write(f"**実行時間**: {entry['execution_time_ms']}ms")
                    
                    with col2:
                        if entry.get('user_id'):
                            st.write(f"**ユーザーID**: {entry['user_id']}")
                        if entry.get('error_details'):
                            st.error(f"**エラー**: {entry['error_details']}")
                    
                    # 入力・出力データ
                    if entry.get('inputs'):
                        st.subheader("入力データ")
                        st.json(entry['inputs'])
                    
                    if entry.get('outputs'):
                        st.subheader("出力データ")
                        st.json(entry['outputs'])
                    
                    # デジタル署名
                    if entry.get('signature'):
                        st.write(f"**デジタル署名**: {entry['signature'][:32]}...")
            
        except Exception as e:
            st.error(f"監査証跡表示エラー: {e}")
```

### 4. ヘルパー機能実装

#### ReviewerWorkspaceヘルパーメソッド
```python
# core/ui/reviewer_workspace.py の続き

    def _get_audit_info(self, session_id: str) -> Dict[str, Any]:
        """監査情報の取得"""
        # 実際の実装では、データベースやファイルから取得
        return {
            "session_id": session_id,
            "department": "finance",
            "auditor": "監査人A",
            "start_date": "2025-01-15",
            "status": "進行中",
            "compliance_results": {
                "overall_score": 87,
                "area_scores": {
                    "approval_control": 92,
                    "segregation_of_duties": 78,
                    "data_quality": 95,
                    "access_control": 85
                }
            },
            "violations": [
                {
                    "rule_id": "sod_001",
                    "policy_name": "corporate_internal_control_policy",
                    "severity": "high",
                    "description": "同一人物による承認と処理",
                    "timestamp": "2025-01-15T13:45:00",
                    "action_taken": "warn",
                    "context": {
                        "transaction_id": "TXN_001",
                        "initiator": "user_001",
                        "approver": "user_001"
                    }
                }
            ]
        }
    
    def _search_evidence(self, criteria: Dict[str, Any]) -> list:
        """証跡検索の実行"""
        if not self.evidence_vault:
            return []
        
        try:
            # Evidence Vaultの検索機能を使用
            # 実際の実装では、EvidenceSearchBlockを使用
            results = []
            
            # サンプルデータ（実際の実装では検索結果を返す）
            sample_results = [
                {
                    "evidence_id": "evidence_001",
                    "evidence_type": "input",
                    "block_id": "excel.read_data",
                    "timestamp": "2025-01-15T10:00:00",
                    "file_path": "evidence/raw/run_001/evidence_001.json",
                    "tags": ["audit_input", "finance"],
                    "relevance_score": 0.95
                },
                {
                    "evidence_id": "evidence_002",
                    "evidence_type": "control_result",
                    "block_id": "control.approval",
                    "timestamp": "2025-01-15T11:30:00",
                    "file_path": "evidence/outputs/run_001/evidence_002.json",
                    "tags": ["approval_control", "finance"],
                    "relevance_score": 0.88
                }
            ]
            
            return sample_results
            
        except Exception as e:
            st.error(f"証跡検索エラー: {e}")
            return []
    
    def _render_evidence_detail(self, evidence_id: str):
        """証跡詳細の表示"""
        evidence_viewer = EvidenceViewer(self.evidence_vault)
        evidence_viewer.render_evidence_detail(evidence_id)
    
    def _start_new_audit(self):
        """新規監査の開始"""
        st.session_state['show_new_audit_modal'] = True
        
        # モーダルダイアログ（Streamlitの制限により簡易実装）
        with st.form("new_audit_form"):
            st.subheader("新規監査開始")
            
            audit_name = st.text_input("監査名")
            department = st.selectbox("対象部門", ["finance", "hr", "it", "procurement"])
            audit_type = st.selectbox("監査タイプ", ["internal_control", "compliance", "operational"])
            risk_level = st.selectbox("リスクレベル", ["low", "medium", "high", "critical"])
            
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("開始"):
                    # 新規監査セッションの作成
                    new_session_id = f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    audit_config = {
                        "session_id": new_session_id,
                        "name": audit_name,
                        "department": department,
                        "audit_type": audit_type,
                        "risk_level": risk_level,
                        "created_at": datetime.now().isoformat(),
                        "status": "started"
                    }
                    
                    # 監査設定の保存（実際の実装では永続化）
                    st.session_state[f'audit_{new_session_id}'] = audit_config
                    st.success(f"監査セッション {new_session_id} を開始しました")
                    st.rerun()
            
            with col2:
                if st.form_submit_button("キャンセル"):
                    st.session_state['show_new_audit_modal'] = False
                    st.rerun()
    
    def _generate_audit_report(self, session_id: str):
        """監査レポートの生成"""
        with st.spinner("レポートを生成中..."):
            try:
                # 実際の実装では、evidence.audit_reportブロックを使用
                report_data = {
                    "session_id": session_id,
                    "generated_at": datetime.now().isoformat(),
                    "report_type": "audit_summary",
                    "content": {
                        "executive_summary": "監査結果のサマリー",
                        "findings": ["発見事項1", "発見事項2"],
                        "recommendations": ["推奨事項1", "推奨事項2"]
                    }
                }
                
                # レポートファイルの生成
                report_file = f"audit_report_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                with open(report_file, 'w', encoding='utf-8') as f:
                    json.dump(report_data, f, ensure_ascii=False, indent=2)
                
                st.success("レポートが生成されました")
                
                # ダウンロードボタン
                with open(report_file, 'rb') as f:
                    st.download_button(
                        label="レポートをダウンロード",
                        data=f.read(),
                        file_name=report_file,
                        mime="application/json"
                    )
                
            except Exception as e:
                st.error(f"レポート生成エラー: {e}")
    
    def _approve_audit(self, session_id: str):
        """監査の承認"""
        if st.session_state.get(f'audit_{session_id}'):
            st.session_state[f'audit_{session_id}']['status'] = 'approved'
            st.session_state[f'audit_{session_id}']['approved_at'] = datetime.now().isoformat()
            st.success(f"監査セッション {session_id} を承認しました")
            st.rerun()
    
    def _reject_audit(self, session_id: str):
        """監査の差し戻し"""
        with st.form("reject_form"):
            st.subheader("監査差し戻し")
            
            reject_reason = st.text_area("差し戻し理由", height=100)
            
            if st.form_submit_button("差し戻し"):
                if reject_reason:
                    if st.session_state.get(f'audit_{session_id}'):
                        st.session_state[f'audit_{session_id}']['status'] = 'rejected'
                        st.session_state[f'audit_{session_id}']['rejected_at'] = datetime.now().isoformat()
                        st.session_state[f'audit_{session_id}']['reject_reason'] = reject_reason
                        st.warning(f"監査セッション {session_id} を差し戻しました")
                        st.rerun()
                else:
                    st.error("差し戻し理由を入力してください")
    
    def _generate_report(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """レポート生成の実行"""
        try:
            report_type = config['type']
            
            # レポートタイプに応じた処理
            if report_type == "監査サマリーレポート":
                return self._generate_audit_summary_report(config)
            elif report_type == "コンプライアンスレポート":
                return self._generate_compliance_report(config)
            elif report_type == "ポリシー違反レポート":
                return self._generate_violation_report(config)
            else:
                return self._generate_generic_report(config)
                
        except Exception as e:
            st.error(f"レポート生成エラー: {e}")
            return None
    
    def _generate_audit_summary_report(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """監査サマリーレポートの生成"""
        # 実際の実装では、テンプレートエンジンやレポート生成ライブラリを使用
        
        report_content = f"""
        # 監査サマリーレポート
        
        ## 期間
        {config['period_start']} ～ {config['period_end']}
        
        ## 対象部門
        {', '.join(config['departments'])}
        
        ## 監査結果
        - 総合コンプライアンススコア: 87%
        - 発見事項: 3件
        - 推奨事項: 5件
        
        ## 詳細
        詳細な監査結果については、添付の証跡を参照してください。
        """
        
        file_name = f"audit_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        with open(file_name, 'w', encoding='utf-8') as f:
            f.write(f"<html><body><pre>{report_content}</pre></body></html>")
        
        return {
            "file_path": file_name,
            "file_name": file_name,
            "mime_type": "text/html"
        }
    
    def _generate_compliance_report(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """コンプライアンスレポートの生成"""
        # 実装省略（同様のパターン）
        pass
    
    def _generate_violation_report(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """ポリシー違反レポートの生成"""
        # 実装省略（同様のパターン）
        pass
    
    def _generate_generic_report(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """汎用レポートの生成"""
        # 実装省略（同様のパターン）
        pass
```


### 5. 管理者パネル実装

#### AdminPanel
```python
# core/ui/admin_panel.py
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json
import os

class AdminPanel:
    """管理者パネル"""
    
    def __init__(self):
        self.config_path = "./config"
        self.users_path = "./config/users.json"
        self.system_config_path = "./config/system.json"
    
    def render(self):
        """管理者パネルの表示"""
        st.markdown('<h1 class="main-header">管理者パネル</h1>', unsafe_allow_html=True)
        
        # タブ構成
        tab1, tab2, tab3, tab4 = st.tabs([
            "システム概要", "ユーザー管理", "ポリシー管理", "システム設定"
        ])
        
        with tab1:
            self._render_system_overview()
        
        with tab2:
            self._render_user_management()
        
        with tab3:
            self._render_policy_management()
        
        with tab4:
            self._render_system_settings()
    
    def _render_system_overview(self):
        """システム概要の表示"""
        st.subheader("システム概要")
        
        # システムメトリクス
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("アクティブユーザー", "25", delta="3")
        
        with col2:
            st.metric("実行中のプラン", "8", delta="-2")
        
        with col3:
            st.metric("今月の監査", "15", delta="5")
        
        with col4:
            st.metric("システム稼働率", "99.8%", delta="0.1%")
        
        # システム状態
        st.subheader("システム状態")
        
        system_status = [
            {"コンポーネント": "Evidence Vault", "状態": "正常", "最終確認": "2025-01-15 14:30"},
            {"コンポーネント": "Policy Engine", "状態": "正常", "最終確認": "2025-01-15 14:30"},
            {"コンポーネント": "UI Server", "状態": "正常", "最終確認": "2025-01-15 14:30"},
            {"コンポーネント": "Database", "状態": "警告", "最終確認": "2025-01-15 14:25"}
        ]
        
        df_status = pd.DataFrame(system_status)
        
        # 状態に応じた色付け
        def color_status(val):
            if val == "正常":
                return "color: green"
            elif val == "警告":
                return "color: orange"
            else:
                return "color: red"
        
        styled_df = df_status.style.applymap(color_status, subset=['状態'])
        st.dataframe(styled_df, use_container_width=True)
        
        # 最近のアクティビティ
        st.subheader("最近のシステムアクティビティ")
        
        activities = [
            {"時刻": "2025-01-15 14:30", "イベント": "ポリシー更新", "ユーザー": "admin", "詳細": "承認統制ポリシー v2025.1.1"},
            {"時刻": "2025-01-15 14:15", "イベント": "ユーザー追加", "ユーザー": "admin", "詳細": "新規監査人アカウント作成"},
            {"時刻": "2025-01-15 13:45", "イベント": "システム警告", "ユーザー": "system", "詳細": "データベース接続遅延"}
        ]
        
        st.dataframe(pd.DataFrame(activities), use_container_width=True)
    
    def _render_user_management(self):
        """ユーザー管理の表示"""
        st.subheader("ユーザー管理")
        
        # ユーザー一覧
        users = self._load_users()
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("ユーザー一覧")
        
        with col2:
            if st.button("新規ユーザー追加", type="primary"):
                st.session_state['show_add_user'] = True
        
        # ユーザーテーブル
        if users:
            df_users = pd.DataFrame(users)
            
            # 編集可能なデータフレーム
            edited_df = st.data_editor(
                df_users,
                column_config={
                    "active": st.column_config.CheckboxColumn("アクティブ"),
                    "role": st.column_config.SelectboxColumn(
                        "ロール",
                        options=["admin", "auditor", "reviewer", "user"]
                    )
                },
                disabled=["user_id", "created_at"],
                use_container_width=True
            )
            
            # 変更の保存
            if st.button("変更を保存"):
                self._save_users(edited_df.to_dict('records'))
                st.success("ユーザー情報を更新しました")
                st.rerun()
        
        # 新規ユーザー追加フォーム
        if st.session_state.get('show_add_user'):
            with st.form("add_user_form"):
                st.subheader("新規ユーザー追加")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    user_id = st.text_input("ユーザーID")
                    user_name = st.text_input("ユーザー名")
                    email = st.text_input("メールアドレス")
                
                with col2:
                    role = st.selectbox("ロール", ["admin", "auditor", "reviewer", "user"])
                    department = st.selectbox("部門", ["finance", "hr", "it", "procurement", "audit"])
                    active = st.checkbox("アクティブ", value=True)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if st.form_submit_button("追加"):
                        new_user = {
                            "user_id": user_id,
                            "user_name": user_name,
                            "email": email,
                            "role": role,
                            "department": department,
                            "active": active,
                            "created_at": datetime.now().isoformat()
                        }
                        
                        users.append(new_user)
                        self._save_users(users)
                        st.success(f"ユーザー {user_id} を追加しました")
                        st.session_state['show_add_user'] = False
                        st.rerun()
                
                with col2:
                    if st.form_submit_button("キャンセル"):
                        st.session_state['show_add_user'] = False
                        st.rerun()
    
    def _render_policy_management(self):
        """ポリシー管理の表示"""
        st.subheader("ポリシー管理")
        
        # ポリシー一覧
        policies = self._load_policies()
        
        if policies:
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.subheader("ポリシー一覧")
            
            with col2:
                if st.button("新規ポリシー作成", type="primary"):
                    st.session_state['show_create_policy'] = True
            
            # ポリシーテーブル
            policy_list = []
            for policy_name, policy_data in policies.items():
                policy_list.append({
                    "ポリシー名": policy_name,
                    "バージョン": policy_data.get('metadata', {}).get('version', 'N/A'),
                    "有効期間": policy_data.get('metadata', {}).get('effective_date', 'N/A'),
                    "所有者": policy_data.get('metadata', {}).get('owner', 'N/A'),
                    "ステータス": "有効" if self._is_policy_active(policy_data) else "無効"
                })
            
            df_policies = pd.DataFrame(policy_list)
            
            # 選択可能なテーブル
            selected_policy = st.selectbox(
                "ポリシー選択",
                options=range(len(df_policies)),
                format_func=lambda x: df_policies.iloc[x]['ポリシー名']
            )
            
            st.dataframe(df_policies, use_container_width=True)
            
            # 選択されたポリシーの詳細
            if selected_policy is not None:
                policy_name = df_policies.iloc[selected_policy]['ポリシー名']
                self._render_policy_detail(policy_name, policies[policy_name])
        
        # 新規ポリシー作成フォーム
        if st.session_state.get('show_create_policy'):
            self._render_create_policy_form()
    
    def _render_policy_detail(self, policy_name: str, policy_data: Dict[str, Any]):
        """ポリシー詳細の表示"""
        with st.expander(f"ポリシー詳細: {policy_name}", expanded=True):
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("編集", key=f"edit_{policy_name}"):
                    st.session_state[f'edit_policy_{policy_name}'] = True
            
            with col2:
                if st.button("無効化", key=f"disable_{policy_name}"):
                    self._disable_policy(policy_name)
                    st.success(f"ポリシー {policy_name} を無効化しました")
                    st.rerun()
            
            with col3:
                if st.button("削除", key=f"delete_{policy_name}"):
                    if st.session_state.get(f'confirm_delete_{policy_name}'):
                        self._delete_policy(policy_name)
                        st.success(f"ポリシー {policy_name} を削除しました")
                        st.rerun()
                    else:
                        st.session_state[f'confirm_delete_{policy_name}'] = True
                        st.warning("もう一度クリックして削除を確認してください")
            
            # ポリシー内容表示
            st.json(policy_data)
    
    def _render_system_settings(self):
        """システム設定の表示"""
        st.subheader("システム設定")
        
        # 設定カテゴリ
        setting_category = st.selectbox(
            "設定カテゴリ",
            ["一般設定", "セキュリティ設定", "監査設定", "通知設定", "バックアップ設定"]
        )
        
        if setting_category == "一般設定":
            self._render_general_settings()
        elif setting_category == "セキュリティ設定":
            self._render_security_settings()
        elif setting_category == "監査設定":
            self._render_audit_settings()
        elif setting_category == "通知設定":
            self._render_notification_settings()
        elif setting_category == "バックアップ設定":
            self._render_backup_settings()
    
    def _render_general_settings(self):
        """一般設定の表示"""
        st.subheader("一般設定")
        
        with st.form("general_settings"):
            system_name = st.text_input("システム名", value="Keiri Agent")
            timezone = st.selectbox("タイムゾーン", ["Asia/Tokyo", "UTC", "America/New_York"])
            language = st.selectbox("言語", ["日本語", "English"])
            
            session_timeout = st.number_input("セッションタイムアウト（分）", min_value=5, max_value=480, value=60)
            max_file_size = st.number_input("最大ファイルサイズ（MB）", min_value=1, max_value=1000, value=100)
            
            if st.form_submit_button("設定を保存"):
                settings = {
                    "system_name": system_name,
                    "timezone": timezone,
                    "language": language,
                    "session_timeout": session_timeout,
                    "max_file_size": max_file_size
                }
                self._save_system_settings("general", settings)
                st.success("一般設定を保存しました")
    
    def _render_security_settings(self):
        """セキュリティ設定の表示"""
        st.subheader("セキュリティ設定")
        
        with st.form("security_settings"):
            password_policy = st.checkbox("強力なパスワードポリシーを有効化", value=True)
            two_factor_auth = st.checkbox("二要素認証を有効化", value=False)
            
            login_attempts = st.number_input("ログイン試行回数制限", min_value=3, max_value=10, value=5)
            lockout_duration = st.number_input("アカウントロック時間（分）", min_value=5, max_value=60, value=15)
            
            encryption_enabled = st.checkbox("データ暗号化を有効化", value=True)
            audit_logging = st.checkbox("監査ログを有効化", value=True)
            
            if st.form_submit_button("設定を保存"):
                settings = {
                    "password_policy": password_policy,
                    "two_factor_auth": two_factor_auth,
                    "login_attempts": login_attempts,
                    "lockout_duration": lockout_duration,
                    "encryption_enabled": encryption_enabled,
                    "audit_logging": audit_logging
                }
                self._save_system_settings("security", settings)
                st.success("セキュリティ設定を保存しました")
    
    def _load_users(self) -> List[Dict[str, Any]]:
        """ユーザー情報の読み込み"""
        try:
            if os.path.exists(self.users_path):
                with open(self.users_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # デフォルトユーザー
                return [
                    {
                        "user_id": "admin",
                        "user_name": "管理者",
                        "email": "admin@company.com",
                        "role": "admin",
                        "department": "audit",
                        "active": True,
                        "created_at": "2025-01-01T00:00:00"
                    }
                ]
        except Exception:
            return []
    
    def _save_users(self, users: List[Dict[str, Any]]):
        """ユーザー情報の保存"""
        try:
            os.makedirs(os.path.dirname(self.users_path), exist_ok=True)
            with open(self.users_path, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"ユーザー情報保存エラー: {e}")
    
    def _load_policies(self) -> Dict[str, Any]:
        """ポリシー情報の読み込み"""
        policies = {}
        policy_dir = Path("./designs/policies")
        
        if policy_dir.exists():
            for policy_file in policy_dir.glob("**/*.yaml"):
                try:
                    with open(policy_file, 'r', encoding='utf-8') as f:
                        import yaml
                        policy_data = yaml.safe_load(f)
                        policy_name = policy_data.get('metadata', {}).get('name', policy_file.stem)
                        policies[policy_name] = policy_data
                except Exception:
                    continue
        
        return policies
    
    def _is_policy_active(self, policy_data: Dict[str, Any]) -> bool:
        """ポリシーの有効性確認"""
        try:
            effective_date = policy_data.get('metadata', {}).get('effective_date')
            expiry_date = policy_data.get('metadata', {}).get('expiry_date')
            
            now = datetime.now()
            
            if effective_date:
                effective = datetime.fromisoformat(effective_date.replace('Z', '+00:00'))
                if now < effective:
                    return False
            
            if expiry_date:
                expiry = datetime.fromisoformat(expiry_date.replace('Z', '+00:00'))
                if now > expiry:
                    return False
            
            return True
        except Exception:
            return False

### 6. 監査ダッシュボード実装

#### AuditDashboard
```python
# core/ui/audit_dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from typing import Dict, Any, List

class AuditDashboard:
    """監査ダッシュボード"""
    
    def __init__(self):
        self.data_source = self._initialize_data_source()
    
    def _initialize_data_source(self):
        """データソースの初期化"""
        # 実際の実装では、データベースやAPIから取得
        return {
            "audit_metrics": self._get_audit_metrics(),
            "compliance_trends": self._get_compliance_trends(),
            "violation_analysis": self._get_violation_analysis(),
            "department_performance": self._get_department_performance()
        }
    
    def render(self):
        """ダッシュボードの表示"""
        st.markdown('<h1 class="main-header">監査ダッシュボード</h1>', unsafe_allow_html=True)
        
        # 期間選択
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            date_from = st.date_input("開始日", value=datetime.now() - timedelta(days=30))
        
        with col2:
            date_to = st.date_input("終了日", value=datetime.now())
        
        with col3:
            if st.button("更新", type="primary"):
                st.rerun()
        
        # メトリクス表示
        self._render_metrics()
        
        # チャート表示
        col1, col2 = st.columns(2)
        
        with col1:
            self._render_compliance_trend_chart()
            self._render_department_performance_chart()
        
        with col2:
            self._render_violation_analysis_chart()
            self._render_audit_progress_chart()
        
        # 詳細テーブル
        self._render_detailed_tables()
    
    def _render_metrics(self):
        """メトリクス表示"""
        metrics = self.data_source["audit_metrics"]
        
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric(
                "総監査数",
                metrics["total_audits"],
                delta=metrics["audit_delta"]
            )
        
        with col2:
            st.metric(
                "完了率",
                f"{metrics['completion_rate']}%",
                delta=f"{metrics['completion_delta']}%"
            )
        
        with col3:
            st.metric(
                "平均コンプライアンススコア",
                f"{metrics['avg_compliance_score']}%",
                delta=f"{metrics['compliance_delta']}%"
            )
        
        with col4:
            st.metric(
                "発見事項",
                metrics["total_findings"],
                delta=metrics["findings_delta"]
            )
        
        with col5:
            st.metric(
                "重大違反",
                metrics["critical_violations"],
                delta=metrics["critical_delta"]
            )
    
    def _render_compliance_trend_chart(self):
        """コンプライアンストレンドチャート"""
        st.subheader("コンプライアンストレンド")
        
        trend_data = self.data_source["compliance_trends"]
        df_trend = pd.DataFrame(trend_data)
        
        fig = px.line(
            df_trend,
            x="date",
            y="compliance_score",
            title="月次コンプライアンススコア推移",
            markers=True
        )
        
        fig.update_layout(
            xaxis_title="日付",
            yaxis_title="コンプライアンススコア (%)",
            yaxis=dict(range=[0, 100])
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def _render_violation_analysis_chart(self):
        """違反分析チャート"""
        st.subheader("違反分析")
        
        violation_data = self.data_source["violation_analysis"]
        
        # 重要度別違反数
        severity_counts = violation_data["by_severity"]
        
        fig = go.Figure(data=[
            go.Bar(
                x=list(severity_counts.keys()),
                y=list(severity_counts.values()),
                marker_color=['red', 'orange', 'yellow', 'green']
            )
        ])
        
        fig.update_layout(
            title="重要度別違反数",
            xaxis_title="重要度",
            yaxis_title="違反数"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def _render_department_performance_chart(self):
        """部門別パフォーマンスチャート"""
        st.subheader("部門別パフォーマンス")
        
        dept_data = self.data_source["department_performance"]
        df_dept = pd.DataFrame(dept_data)
        
        fig = px.bar(
            df_dept,
            x="department",
            y="compliance_score",
            color="compliance_score",
            title="部門別コンプライアンススコア",
            color_continuous_scale="RdYlGn"
        )
        
        fig.update_layout(
            xaxis_title="部門",
            yaxis_title="コンプライアンススコア (%)",
            yaxis=dict(range=[0, 100])
        )
        
        st.plotly_chart(fig, use_container_width=True)
    
    def _render_audit_progress_chart(self):
        """監査進捗チャート"""
        st.subheader("監査進捗")
        
        # サンプルデータ
        progress_data = {
            "完了": 15,
            "進行中": 8,
            "計画中": 5,
            "延期": 2
        }
        
        fig = go.Figure(data=[
            go.Pie(
                labels=list(progress_data.keys()),
                values=list(progress_data.values()),
                hole=0.3
            )
        ])
        
        fig.update_layout(title="監査ステータス分布")
        
        st.plotly_chart(fig, use_container_width=True)
    
    def _render_detailed_tables(self):
        """詳細テーブル表示"""
        st.subheader("詳細情報")
        
        tab1, tab2, tab3 = st.tabs(["最近の監査", "重要な発見事項", "改善提案"])
        
        with tab1:
            recent_audits = [
                {
                    "監査ID": "AUD_2025_001",
                    "部門": "財務部",
                    "監査人": "監査人A",
                    "開始日": "2025-01-10",
                    "ステータス": "完了",
                    "スコア": "92%"
                },
                {
                    "監査ID": "AUD_2025_002",
                    "部門": "人事部",
                    "監査人": "監査人B",
                    "開始日": "2025-01-12",
                    "ステータス": "進行中",
                    "スコア": "85%"
                }
            ]
            
            st.dataframe(pd.DataFrame(recent_audits), use_container_width=True)
        
        with tab2:
            critical_findings = [
                {
                    "発見事項ID": "FIND_001",
                    "重要度": "高",
                    "カテゴリ": "承認統制",
                    "説明": "高額取引の承認プロセス不備",
                    "発見日": "2025-01-14",
                    "ステータス": "対応中"
                },
                {
                    "発見事項ID": "FIND_002",
                    "重要度": "中",
                    "カテゴリ": "職務分掌",
                    "説明": "同一人物による承認と処理",
                    "発見日": "2025-01-13",
                    "ステータス": "未対応"
                }
            ]
            
            st.dataframe(pd.DataFrame(critical_findings), use_container_width=True)
        
        with tab3:
            recommendations = [
                {
                    "推奨事項ID": "REC_001",
                    "優先度": "高",
                    "カテゴリ": "プロセス改善",
                    "説明": "承認権限マトリックスの見直し",
                    "期待効果": "承認統制の強化",
                    "実装期間": "2週間"
                },
                {
                    "推奨事項ID": "REC_002",
                    "優先度": "中",
                    "カテゴリ": "システム改善",
                    "説明": "自動化ルールの追加",
                    "期待効果": "効率性向上",
                    "実装期間": "1ヶ月"
                }
            ]
            
            st.dataframe(pd.DataFrame(recommendations), use_container_width=True)
    
    def _get_audit_metrics(self) -> Dict[str, Any]:
        """監査メトリクスの取得"""
        return {
            "total_audits": 30,
            "audit_delta": 5,
            "completion_rate": 75,
            "completion_delta": 10,
            "avg_compliance_score": 87,
            "compliance_delta": 3,
            "total_findings": 12,
            "findings_delta": -2,
            "critical_violations": 3,
            "critical_delta": 1
        }
    
    def _get_compliance_trends(self) -> List[Dict[str, Any]]:
        """コンプライアンストレンドの取得"""
        return [
            {"date": "2024-10", "compliance_score": 82},
            {"date": "2024-11", "compliance_score": 85},
            {"date": "2024-12", "compliance_score": 88},
            {"date": "2025-01", "compliance_score": 87}
        ]
    
    def _get_violation_analysis(self) -> Dict[str, Any]:
        """違反分析データの取得"""
        return {
            "by_severity": {
                "重大": 3,
                "高": 5,
                "中": 8,
                "低": 12
            },
            "by_category": {
                "承認統制": 8,
                "職務分掌": 6,
                "データ品質": 4,
                "アクセス制御": 10
            }
        }
    
    def _get_department_performance(self) -> List[Dict[str, Any]]:
        """部門別パフォーマンスの取得"""
        return [
            {"department": "財務部", "compliance_score": 92},
            {"department": "人事部", "compliance_score": 85},
            {"department": "IT部", "compliance_score": 88},
            {"department": "調達部", "compliance_score": 78},
            {"department": "営業部", "compliance_score": 82}
        ]
```

### 7. 期待効果とメリット

#### 監査効率化
- **統合ワークスペース**: 監査業務の一元管理
- **リアルタイム監視**: 即座の問題検知と対応
- **自動レポート生成**: 手動作業の90%削減

#### ユーザビリティ向上
- **直感的インターフェース**: 学習コストの最小化
- **ロールベースアクセス**: 適切な権限管理
- **レスポンシブデザイン**: デバイス非依存の操作性

#### 意思決定支援
- **ダッシュボード**: 視覚的な状況把握
- **トレンド分析**: データドリブンな改善
- **アラート機能**: 重要事項の即座通知

