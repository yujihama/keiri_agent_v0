"""認証・権限管理モジュール

Keiri Agentにおけるユーザー認証、ロールベースアクセス制御、権限管理を提供します。
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from enum import Enum
import streamlit as st
import hashlib
import secrets
import json
import os


class UserRole(str, Enum):
    """ユーザーロール"""
    ADMIN = "admin"
    AUDITOR = "auditor"
    REVIEWER = "reviewer"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, Enum):
    """権限"""
    EVIDENCE_READ = "evidence_read"
    EVIDENCE_WRITE = "evidence_write"
    EVIDENCE_DELETE = "evidence_delete"
    PLAN_EXECUTE = "plan_execute"
    PLAN_MODIFY = "plan_modify"
    CONTROL_CONFIG = "control_config"
    POLICY_MANAGE = "policy_manage"
    USER_MANAGE = "user_manage"
    AUDIT_REVIEW = "audit_review"
    SYSTEM_CONFIG = "system_config"


class UserProfile(BaseModel):
    """ユーザープロファイル"""
    user_id: str
    username: str
    display_name: str
    email: str
    roles: List[UserRole]
    department: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    preferences: Dict[str, Any] = {}


class AuthSession(BaseModel):
    """認証セッション"""
    session_id: str
    user_id: str
    username: str
    roles: List[UserRole]
    permissions: Set[Permission]
    created_at: datetime
    expires_at: datetime
    last_activity: datetime


class AuthManager:
    """認証管理クラス"""
    
    def __init__(self, config_path: str = None):
        """
        認証マネージャーの初期化
        
        Args:
            config_path: 認証設定ファイルのパス
        """
        self.config_path = config_path or os.path.join(os.getcwd(), "auth_config.json")
        self.role_permissions = self._load_role_permissions()
        self.users = self._load_users()
        
    def _load_role_permissions(self) -> Dict[UserRole, Set[Permission]]:
        """ロール権限マッピングの読み込み"""
        return {
            UserRole.ADMIN: {
                Permission.EVIDENCE_READ, Permission.EVIDENCE_WRITE, Permission.EVIDENCE_DELETE,
                Permission.PLAN_EXECUTE, Permission.PLAN_MODIFY, Permission.CONTROL_CONFIG,
                Permission.POLICY_MANAGE, Permission.USER_MANAGE, Permission.AUDIT_REVIEW,
                Permission.SYSTEM_CONFIG
            },
            UserRole.AUDITOR: {
                Permission.EVIDENCE_READ, Permission.AUDIT_REVIEW, Permission.PLAN_EXECUTE,
                Permission.CONTROL_CONFIG
            },
            UserRole.REVIEWER: {
                Permission.EVIDENCE_READ, Permission.AUDIT_REVIEW, Permission.PLAN_EXECUTE
            },
            UserRole.ANALYST: {
                Permission.EVIDENCE_READ, Permission.EVIDENCE_WRITE, Permission.PLAN_EXECUTE,
                Permission.PLAN_MODIFY
            },
            UserRole.OPERATOR: {
                Permission.EVIDENCE_READ, Permission.PLAN_EXECUTE
            },
            UserRole.VIEWER: {
                Permission.EVIDENCE_READ
            }
        }
    
    def _load_users(self) -> Dict[str, UserProfile]:
        """ユーザー情報の読み込み"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    users = {}
                    for user_data in config.get('users', []):
                        user = UserProfile(**user_data)
                        users[user.user_id] = user
                    return users
            except Exception as e:
                st.warning(f"ユーザー設定の読み込みに失敗しました: {str(e)}")
        
        # デフォルトユーザーの作成
        return self._create_default_users()
    
    def _create_default_users(self) -> Dict[str, UserProfile]:
        """デフォルトユーザーの作成"""
        default_users = {
            "admin": UserProfile(
                user_id="admin",
                username="admin",
                display_name="システム管理者",
                email="admin@example.com",
                roles=[UserRole.ADMIN],
                department="システム管理部",
                created_at=datetime.now()
            ),
            "auditor": UserProfile(
                user_id="auditor",
                username="auditor",
                display_name="監査人",
                email="auditor@example.com",
                roles=[UserRole.AUDITOR],
                department="監査部",
                created_at=datetime.now()
            ),
            "analyst": UserProfile(
                user_id="analyst",
                username="analyst",
                display_name="分析者",
                email="analyst@example.com",
                roles=[UserRole.ANALYST],
                department="財務部",
                created_at=datetime.now()
            )
        }
        
        # デフォルト設定の保存
        self._save_users(default_users)
        return default_users
    
    def _save_users(self, users: Dict[str, UserProfile]) -> None:
        """ユーザー情報の保存"""
        try:
            config = {
                'users': [user.dict() for user in users.values()]
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            st.error(f"ユーザー設定の保存に失敗しました: {str(e)}")
    
    def authenticate(self, username: str, password: str = None) -> Optional[AuthSession]:
        """ユーザー認証"""
        # 簡易実装（本格運用時は適切な認証システムを使用）
        user = None
        for u in self.users.values():
            if u.username == username:
                user = u
                break
        
        if not user or not user.is_active:
            return None
        
        # セッション作成
        session = AuthSession(
            session_id=secrets.token_hex(16),
            user_id=user.user_id,
            username=user.username,
            roles=user.roles,
            permissions=self._get_user_permissions(user.roles),
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=8),
            last_activity=datetime.now()
        )
        
        # Streamlitセッションに保存
        st.session_state.auth_session = session
        
        return session
    
    def logout(self) -> None:
        """ログアウト"""
        if 'auth_session' in st.session_state:
            del st.session_state.auth_session
    
    def get_current_session(self) -> Optional[AuthSession]:
        """現在のセッション取得"""
        session = st.session_state.get('auth_session')
        if not session:
            return None
        
        # セッション有効性チェック
        if datetime.now() > session.expires_at:
            self.logout()
            return None
        
        # 最終活動時刻の更新
        session.last_activity = datetime.now()
        st.session_state.auth_session = session
        
        return session
    
    def check_permission(self, permission: Permission) -> bool:
        """権限チェック"""
        session = self.get_current_session()
        if not session:
            return False
        
        return permission in session.permissions
    
    def require_permission(self, permission: Permission) -> bool:
        """権限要求（権限がない場合は例外発生）"""
        if not self.check_permission(permission):
            st.error(f"この操作には {permission.value} 権限が必要です。")
            st.stop()
        return True
    
    def require_role(self, role: UserRole) -> bool:
        """ロール要求"""
        session = self.get_current_session()
        if not session or role not in session.roles:
            st.error(f"この操作には {role.value} ロールが必要です。")
            st.stop()
        return True
    
    def _get_user_permissions(self, roles: List[UserRole]) -> Set[Permission]:
        """ユーザーの権限を計算"""
        permissions = set()
        for role in roles:
            permissions.update(self.role_permissions.get(role, set()))
        return permissions
    
    def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """ユーザープロファイル取得"""
        return self.users.get(user_id)
    
    def update_user_profile(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """ユーザープロファイル更新"""
        if user_id not in self.users:
            return False
        
        user = self.users[user_id]
        for key, value in updates.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self._save_users(self.users)
        return True


# グローバル認証マネージャー
auth_manager = AuthManager()


def require_auth() -> AuthSession:
    """認証必須デコレータ"""
    session = auth_manager.get_current_session()
    if not session:
        st.error("ログインが必要です。")
        st.stop()
    return session


def login_form() -> None:
    """ログインフォーム"""
    st.title("Keiri Agent - ログイン")
    
    with st.form("login_form"):
        username = st.text_input("ユーザー名")
        password = st.text_input("パスワード", type="password")
        submit = st.form_submit_button("ログイン")
        
        if submit:
            session = auth_manager.authenticate(username, password)
            if session:
                st.success(f"ようこそ、{session.username} さん")
                st.rerun()
            else:
                st.error("認証に失敗しました。")


def sidebar_user_info() -> None:
    """サイドバーユーザー情報"""
    session = auth_manager.get_current_session()
    if session:
        st.sidebar.write("---")
        st.sidebar.write(f"**ユーザー:** {session.username}")
        st.sidebar.write(f"**ロール:** {', '.join([r.value for r in session.roles])}")
        if st.sidebar.button("ログアウト"):
            auth_manager.logout()
            st.rerun()
    else:
        st.sidebar.info("ログインしていません")