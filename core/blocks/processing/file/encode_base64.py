from __future__ import annotations

from typing import Any, Dict, Optional
import base64
import mimetypes
from pathlib import Path

from core.blocks.base import BlockContext, ProcessingBlock


class EncodeBase64Block(ProcessingBlock):
    id = "file.encode_base64"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Encode given file bytes (or a file at path) into Base64.

        Inputs:
          - data: bytes | string (optional). If string and points to an existing file, the file is read.
          - path: string (optional). File system path to read if provided.
          - name: string (optional). Preferred name for the output; inferred from path if not given.
          - mime_type: string (optional). If not provided, guessed from name/path.
          - as_data_uri: boolean (optional, default false). Also return a data URI.

        Output:
          - encoded: {
              name: string,
              mime_type: string,
              size: integer,
              base64: string,
              data_uri?: string
            }
        """

        data = inputs.get("data")
        path_in: Optional[str] = inputs.get("path")
        name: Optional[str] = inputs.get("name")
        mime_type: Optional[str] = inputs.get("mime_type")
        as_data_uri: bool = bool(inputs.get("as_data_uri", False))

        raw: Optional[bytes] = None
        used_path: Optional[Path] = None

        if isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
        elif isinstance(data, str):
            p = Path(data)
            if p.exists() and p.is_file():
                used_path = p
                raw = p.read_bytes()

        if raw is None and path_in:
            p2 = Path(str(path_in))
            if p2.exists() and p2.is_file():
                used_path = p2
                raw = p2.read_bytes()

        if raw is None:
            f = inputs.get("file")
            if isinstance(f, (bytes, bytearray)):
                raw = bytes(f)

        # Fallbacks for naming and mime
        resolved_name = name or (used_path.name if used_path else (path_in or "unknown"))
        resolved_mime = mime_type
        if not resolved_mime:
            guessed, _ = mimetypes.guess_type(resolved_name)
            resolved_mime = guessed or "application/octet-stream"

        if raw is None:
            # Nothing to encode
            out: Dict[str, Any] = {
                "name": resolved_name,
                "mime_type": resolved_mime,
                "size": 0,
                "base64": "",
            }
            if as_data_uri:
                out["data_uri"] = f"data:{resolved_mime};base64,"
            return {"encoded": out}

        b64 = base64.b64encode(raw).decode("ascii")
        out: Dict[str, Any] = {
            "name": resolved_name,
            "mime_type": resolved_mime,
            "size": len(raw),
            "base64": b64,
        }
        if as_data_uri:
            out["data_uri"] = f"data:{resolved_mime};base64,{b64}"

        return {"encoded": out}


