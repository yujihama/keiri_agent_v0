"""暗号化機能

AES-256による強固な暗号化とHMAC-SHA256による改ざん検知機能を提供します。
"""

from __future__ import annotations
import os
import hashlib
import hmac
from typing import Union, Tuple
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64


class EncryptionManager:
    """暗号化管理クラス"""
    
    def __init__(self, password: str = None):
        """
        暗号化マネージャーの初期化
        
        Args:
            password: 暗号化パスワード（指定しない場合は自動生成）
        """
        if password:
            self.encryption_key = self._derive_key_from_password(password)
        else:
            self.encryption_key = Fernet.generate_key()
        
        self.cipher = Fernet(self.encryption_key)
    
    def _derive_key_from_password(self, password: str) -> bytes:
        """パスワードから暗号化キーを導出"""
        # ソルトは固定（本番環境では環境変数等から取得）
        salt = b'keiri_agent_salt_2025'
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key
    
    def encrypt(self, data: Union[str, bytes]) -> bytes:
        """
        データの暗号化
        
        Args:
            data: 暗号化するデータ
            
        Returns:
            暗号化されたデータ
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        return self.cipher.encrypt(data)
    
    def decrypt(self, encrypted_data: bytes) -> bytes:
        """
        データの復号化
        
        Args:
            encrypted_data: 暗号化されたデータ
            
        Returns:
            復号化されたデータ
        """
        return self.cipher.decrypt(encrypted_data)
    
    def calculate_hash(self, data: Union[str, bytes]) -> str:
        """
        データのハッシュ値計算（改ざん検知用）
        
        Args:
            data: ハッシュ化するデータ
            
        Returns:
            SHA256ハッシュ値（16進数文字列）
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        return hashlib.sha256(data).hexdigest()
    
    def calculate_hmac(self, data: Union[str, bytes]) -> str:
        """
        HMAC署名の計算（真正性検証用）
        
        Args:
            data: 署名するデータ
            
        Returns:
            HMAC-SHA256署名（16進数文字列）
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        return hmac.new(
            self.encryption_key,
            data,
            hashlib.sha256
        ).hexdigest()
    
    def verify_hmac(self, data: Union[str, bytes], signature: str) -> bool:
        """
        HMAC署名の検証
        
        Args:
            data: 検証するデータ
            signature: HMAC署名
            
        Returns:
            署名が正しい場合True
        """
        expected_signature = self.calculate_hmac(data)
        return hmac.compare_digest(expected_signature, signature)
    
    def get_key_info(self) -> dict:
        """
        暗号化キー情報の取得（デバッグ・監査用）
        
        Returns:
            キー情報の辞書
        """
        return {
            'algorithm': 'AES-256',
            'key_length': len(self.encryption_key),
            'key_hash': self.calculate_hash(self.encryption_key)[:16] + '...'  # 一部のみ表示
        }