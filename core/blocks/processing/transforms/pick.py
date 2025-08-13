from __future__ import annotations

from typing import Any, Dict

from core.blocks.base import BlockContext, ProcessingBlock


def _get_path(obj: Any, path: Any) -> Any:
    cur: Any = obj
    if path is None or str(path) == "":
        return cur
    if isinstance(cur, dict) and str(path) in cur:
        return cur[str(path)]
    for seg in str(path).split(".") if path else []:
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur


class PickBlock(ProcessingBlock):
    """Unified value picker with explicit return type.

    Inputs:
      - source: any
      - path: str | None
      - return: enum[bytes, object, string, number, boolean]
      - base64?: bool (only for return==bytes)

    Outputs:
      - value: any (type depends on return)
    """

    id = "transforms.pick"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        src = inputs.get("source")
        path = inputs.get("path")
        want = str(inputs.get("return") or "object").lower()
        as_b64 = bool(inputs.get("base64", False))

        val = _get_path(src, path)

        if want == "bytes":
            if isinstance(val, (bytes, bytearray)):
                return {"value": bytes(val)}
            if isinstance(val, str):
                # when base64 flag is true, decode; otherwise return empty on non-bytes
                if as_b64:
                    try:
                        import base64

                        return {"value": base64.b64decode(val)}
                    except Exception:
                        return {"value": b""}
                return {"value": b""}
            return {"value": b""}

        if want == "string":
            try:
                return {"value": "" if val is None else str(val)}
            except Exception:
                return {"value": ""}

        if want == "number":
            try:
                if isinstance(val, (int, float)):
                    return {"value": float(val)}
                if isinstance(val, str) and val.strip():
                    return {"value": float(val)}
            except Exception:
                pass
            return {"value": 0}

        if want == "boolean":
            if isinstance(val, bool):
                return {"value": val}
            if isinstance(val, (int, float)):
                return {"value": val != 0}
            if isinstance(val, str):
                s = val.strip().lower()
                return {"value": s in {"true", "1", "yes", "y"}}
            return {"value": False}

        # default: object
        return {"value": val}


