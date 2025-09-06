from __future__ import annotations

from typing import Any, Dict, List, Tuple, Optional
import base64
import os

from core.blocks.base import BlockContext, ProcessingBlock
from core.errors import ErrorCode, create_input_error, wrap_exception
from core.plan.text_extractor import extract_texts as _extract_texts


class ExtractTextsBlock(ProcessingBlock):
    id = "file.extract_texts"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        files_in = inputs.get("files") or []
        if not isinstance(files_in, list) or not files_in:
            raise create_input_error(
                field="files",
                expected_type="non-empty list[{name, bytes|base64}]",
                actual_value=files_in,
                code=ErrorCode.INPUT_REQUIRED_MISSING,
            )

        pairs: List[Tuple[str, bytes]] = []
        for f in files_in:
            if not isinstance(f, dict):
                continue
            name = str(f.get("name") or f.get("path") or "document.txt")
            raw: Optional[bytes] = None
            b = f.get("bytes")
            if isinstance(b, (bytes, bytearray)):
                raw = bytes(b)
            elif isinstance(b, str):
                # ファイルパスとして扱う
                try:
                    with open(b, "rb") as file:
                        raw = file.read()
                except Exception:
                    raw = None
            elif isinstance(f.get("base64"), str):
                try:
                    raw = base64.b64decode(str(f.get("base64")))
                except Exception:
                    raw = None
            if raw is None:
                continue
            pairs.append((name, raw))

        try:
            texts = _extract_texts(pairs)
            out_files: List[Dict[str, Any]] = []
            for (name, raw), text in zip(pairs, texts):
                ext = ""
                if "." in name:
                    ext = name[name.rfind(".") :].lower()
                out_files.append({
                    "name": name,
                    "ext": ext,
                    "size": len(raw),
                    "text_excerpt": text,
                })
            return {"evidence": {"files": out_files}}
        except Exception as e:
            raise wrap_exception(e, ErrorCode.BLOCK_EXECUTION_FAILED, inputs)


