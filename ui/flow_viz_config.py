"""
D3.js専用フロー図表示の設定管理
"""
import os

# デフォルト設定（横幅を広めに）
DEFAULT_FLOW_HEIGHT = 400
DEFAULT_FLOW_WIDTH = 1400


def get_flow_config() -> dict:
    """D3.jsフロー図表示の設定を取得"""
    return {
        "width": int(os.getenv("KEIRI_FLOW_WIDTH", str(DEFAULT_FLOW_WIDTH))),
        "height": int(os.getenv("KEIRI_FLOW_HEIGHT", str(DEFAULT_FLOW_HEIGHT))),
        "node_radius": int(os.getenv("KEIRI_FLOW_NODE_RADIUS", "65")),
        "link_distance": int(os.getenv("KEIRI_FLOW_LINK_DISTANCE", "150")),
        "charge_strength": int(os.getenv("KEIRI_FLOW_CHARGE", "-600")),
        # エッジ重複回避設定
        "edge_offset": int(os.getenv("KEIRI_EDGE_OFFSET", "15")),
        "edge_opacity": float(os.getenv("KEIRI_EDGE_OPACITY", "0.6")),
        "enable_edge_highlight": os.getenv("KEIRI_EDGE_HIGHLIGHT", "true").lower() == "true",
    }


def is_dev_mode() -> bool:
    """開発モードかどうか（レガシーサポート用）"""
    return os.getenv("KEIRI_DEV_MODE", "false").lower() == "true"
