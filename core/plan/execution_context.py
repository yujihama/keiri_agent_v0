from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass, field


@dataclass
class ExecutionContext:
    """プラン実行のための統合コンテキスト"""
    
    # 基本設定
    headless_mode: bool = False
    output_dir: Optional[Path] = None
    
    # 変数オーバーライド
    vars_overrides: Dict[str, Any] = field(default_factory=dict)
    
    # ファイル入力（ファイルパス → 実際のファイル）
    file_inputs: Dict[str, Path] = field(default_factory=dict)
    
    # 事前読み込み済みデータ
    preloaded_data: Dict[str, Any] = field(default_factory=dict)
    
    # UIブロックのモック応答
    ui_mock_responses: Dict[str, Any] = field(default_factory=dict)
    
    # 設定ファイルからの読み込み
    @classmethod
    def from_config_file(cls, config_path: Union[str, Path]) -> "ExecutionContext":
        """設定ファイルからExecutionContextを作成"""
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)
        
        return cls(
            headless_mode=config.get("headless_mode", False),
            output_dir=Path(config.get("output_dir", "output")) if config.get("output_dir") else None,
            vars_overrides=config.get("vars", {}),
            file_inputs={k: Path(v) for k, v in config.get("file_inputs", {}).items()},
            preloaded_data=config.get("preloaded_data", {}),
            ui_mock_responses=config.get("ui_mocks", {})
        )
    
    def resolve_file_input(self, file_id: str) -> Optional[bytes]:
        """ファイルIDに対応するファイルを読み込み"""
        # 事前読み込み済みデータを優先
        if file_id in self.preloaded_data:
            data = self.preloaded_data[file_id]
            if isinstance(data, bytes):
                return data
            elif isinstance(data, str):
                return data.encode('utf-8')
            else:
                return str(data).encode('utf-8')
        
        # ファイルパスから読み込み
        if file_id in self.file_inputs:
            file_path = self.file_inputs[file_id]
            if file_path.exists():
                return file_path.read_bytes()
            else:
                raise FileNotFoundError(f"File not found: {file_path}")
        
        return None
    
    def get_ui_mock_response(self, block_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        """UIブロックのモック応答を取得
        優先順位:
          1) ノードID直下
          2) ブロックID下のノードID
          3) ブロックIDに紐づく単一レスポンス（approved/metadata を含むもののみ）
        """
        # 1) ノード固有
        if node_id in self.ui_mock_responses:
            val = self.ui_mock_responses[node_id]
            return val if isinstance(val, dict) else None

        # 2) ブロックID配下
        blk = self.ui_mock_responses.get(block_id)
        if isinstance(blk, dict):
            if node_id and node_id in blk and isinstance(blk[node_id], dict):
                return blk[node_id]  # type: ignore[index]
            # 3) 単一レスポンス（approved/metadata が含まれる時のみ）
            if all(k in blk for k in ("approved", "metadata")):
                return blk  # type: ignore[return-value]

        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式で出力"""
        return {
            "headless_mode": self.headless_mode,
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "vars_overrides": self.vars_overrides,
            "file_inputs": {k: str(v) for k, v in self.file_inputs.items()},
            "preloaded_data": {k: str(v) if isinstance(v, (bytes, Path)) else v 
                              for k, v in self.preloaded_data.items()},
            "ui_mock_responses": self.ui_mock_responses
        }
