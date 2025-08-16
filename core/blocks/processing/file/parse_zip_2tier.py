from __future__ import annotations

from typing import Any, Dict, List
from io import BytesIO
import zipfile
import hashlib
import base64
import mimetypes

from core.plan.text_extractor import extract_texts

from core.blocks.base import BlockContext, ProcessingBlock


class ParseZip2TierBlock(ProcessingBlock):
    id = "file.parse_zip_2tier"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a 2-tier evidence ZIP and produce structured metadata and text.

        Inputs
        ------
        - zip_bytes: bytes of a .zip archive. The archive may contain files at the
          root (tier 1) and/or within directories (tier 2). Deeper nesting is ignored.

        Outputs
        -------
        evidence: dict with keys
          - raw_size: int, size of original zip
          - total_files: int, number of extracted file entries (non-directories)
          - files: list of { path, name, size, ext, sha1, text_excerpt }
          - by_dir: mapping { top_dir_or_empty: [ relative_paths ] }
        """

        zip_bytes = inputs.get("zip_bytes", b"")
        if not isinstance(zip_bytes, (bytes, bytearray)) or len(zip_bytes) == 0:
            return {"evidence": {"raw_size": 0, "total_files": 0, "files": [], "by_dir": {}}}

        files_info: List[Dict[str, Any]] = []
        by_dir: Dict[str, List[str]] = {}

        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                # Only include file entries
                for zi in zf.infolist():
                    if zi.is_dir():
                        # track dir grouping keys even if empty, for completeness
                        top = zi.filename.strip("/").split("/", 1)[0] if "/" in zi.filename else ""
                        by_dir.setdefault(top, [])
                        continue
                    path = zi.filename
                    name = path.split("/")[-1]
                    try:
                        data = zf.read(zi)
                    except Exception:
                        data = b""
                    size = len(data)
                    ext = ("." + name.split(".")[-1].lower()) if ("." in name) else ""
                    sha1 = hashlib.sha1(data).hexdigest() if data else ""

                    # Group by top-level directory (or empty)
                    top_dir = path.split("/", 1)[0] if "/" in path else ""
                    rel_path = path[len(top_dir) + 1 :] if top_dir else name
                    by_dir.setdefault(top_dir, []).append(rel_path)

                    # Extract a small text excerpt for matching (best-effort)
                    excerpt = ""
                    try:
                        texts = extract_texts([(name, data)])
                        excerpt = (texts[0] if texts else "")[:2000]
                    except Exception:
                        excerpt = ""

                    # Infer mime type and attach base64 for images/PDF for downstream multimodal/evidence use
                    mime_type, _ = mimetypes.guess_type(name)
                    mime_type = mime_type or "application/octet-stream"

                    file_entry: Dict[str, Any] = {
                        "path": path,
                        "name": name,
                        "size": size,
                        "ext": ext,
                        "sha1": sha1,
                        "text_excerpt": excerpt,
                        "mime_type": mime_type,
                    }

                    try:
                        if mime_type in ("image/png", "image/jpeg", "application/pdf") and data:
                            file_entry["base64"] = base64.b64encode(data).decode("ascii")
                    except Exception:
                        pass

                    files_info.append(file_entry)
        except zipfile.BadZipFile:
            # Return empty evidence on invalid zip
            return {"evidence": {"raw_size": len(zip_bytes), "total_files": 0, "files": [], "by_dir": {}}}

        evidence = {
            "raw_size": len(zip_bytes),
            "total_files": len(files_info),
            "files": files_info,
            "by_dir": by_dir,
        }
        return {"evidence": evidence}


