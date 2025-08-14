from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional, Union
import mimetypes
import json

from .execution_context import ExecutionContext


class FileInputHandler:
    """ファイル入力の統合ハンドラー"""
    
    def __init__(self, execution_context: ExecutionContext):
        self.execution_context = execution_context
    
    def resolve_file_input(self, file_id: str, fallback_path: Optional[Union[str, Path]] = None) -> Optional[bytes]:
        """ファイルIDに対応するファイルを解決"""
        # 1. 実行コンテキストから解決を試行
        result = self.execution_context.resolve_file_input(file_id)
        if result is not None:
            return result
        
        # 2. フォールバックパスから解決を試行
        if fallback_path:
            path = Path(fallback_path)
            if path.exists():
                return path.read_bytes()
        
        return None
    
    def resolve_file_inputs_for_node(self, node_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """ノードの入力からファイル入力を解決"""
        resolved_inputs = {}
        
        for key, value in node_inputs.items():
            if isinstance(value, str) and value.startswith("file:"):
                # file:employees_csv 形式の指定
                file_id = value[5:]  # "file:" を除去
                file_data = self.resolve_file_input(file_id)
                if file_data is not None:
                    resolved_inputs[key] = file_data
                else:
                    # ファイルが見つからない場合は元の値を保持
                    resolved_inputs[key] = value
            elif isinstance(value, dict) and "file_id" in value:
                # {file_id: "employees_csv", fallback: "path/to/file.csv"} 形式
                file_id = value["file_id"]
                fallback = value.get("fallback")
                file_data = self.resolve_file_input(file_id, fallback)
                if file_data is not None:
                    resolved_inputs[key] = file_data
                else:
                    resolved_inputs[key] = value
            else:
                resolved_inputs[key] = value
        
        return resolved_inputs
    
    def auto_resolve_file_inputs(self, requirements: list) -> Dict[str, bytes]:
        """requirementsから自動的にファイル入力を解決"""
        resolved_files = {}
        
        for req in requirements:
            if isinstance(req, dict):
                field_id = req.get("id")
                field_type = req.get("type")
                
                if field_id and field_type in ["file", "files", "folder"]:
                    file_data = self.resolve_file_input(field_id)
                    if file_data is not None:
                        resolved_files[field_id] = file_data
        
        return resolved_files
    
    def create_file_summary(self, file_data: bytes, file_name: str = "unknown") -> Dict[str, Any]:
        """ファイルのサマリー情報を作成"""
        mime_type, _ = mimetypes.guess_type(file_name)
        
        return {
            "name": file_name,
            "size": len(file_data),
            "mime_type": mime_type or "application/octet-stream",
            "bytes": file_data,
            "base64": base64.b64encode(file_data).decode("ascii")
        }
    
    def save_output_file(self, file_data: bytes, file_name: str, sub_dir: Optional[str] = None) -> Path:
        """出力ファイルを保存"""
        if self.execution_context.output_dir:
            output_dir = self.execution_context.output_dir
            if sub_dir:
                output_dir = output_dir / sub_dir
            output_dir.mkdir(parents=True, exist_ok=True)
        else:
            output_dir = Path("output")
            if sub_dir:
                output_dir = output_dir / sub_dir
            output_dir.mkdir(parents=True, exist_ok=True)
        
        output_path = output_dir / file_name
        output_path.write_bytes(file_data)
        return output_path
