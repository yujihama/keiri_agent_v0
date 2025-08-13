from __future__ import annotations

from typing import Any, Dict

from core.blocks.base import BlockContext, ProcessingBlock


def _get_path(obj: Any, path: str) -> Any:
    cur: Any = obj
    # 空パスはそのまま返す（全体取得）
    if path is None or str(path) == "":
        return cur
    # トップレベルでの厳密キー一致を優先（キーにドットを含むケースをサポート）
    if isinstance(cur, dict) and str(path) in cur:
        return cur[str(path)]
    for seg in str(path).split(".") if path else []:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


class PickBytesBlock(ProcessingBlock):
    id = "transforms.pick_bytes"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        src = inputs.get("source")
        path = inputs.get("path")
        val = _get_path(src, path)
        if isinstance(val, (bytes, bytearray)):
            return {"value": bytes(val)}
        # best-effort: allow base64-encoded string
        if isinstance(val, str):
            try:
                import base64
                return {"value": base64.b64decode(val)}
            except Exception:
                return {"value": b""}
        return {"value": b""}


class PickObjectBlock(ProcessingBlock):
    id = "transforms.pick_object"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        src = inputs.get("source")
        path = inputs.get("path")
        val = _get_path(src, path)
        return {"value": val}


