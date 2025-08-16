from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import os

from core.blocks.base import BlockContext, ProcessingBlock


class EvidenceSearchBlock(ProcessingBlock):
    id = "evidence.search"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        criteria = inputs.get("search_criteria") or {}
        compute_hash = bool(inputs.get("compute_hash", False))
        
        base_dir = Path(os.getenv("KEIRI_AGENT_EVIDENCE_DIR", "runs/evidence"))
        base_dir.mkdir(parents=True, exist_ok=True)

        name_contains = (criteria.get("name_contains") or "").lower()
        ext_in = criteria.get("ext")
        if isinstance(ext_in, str) and ext_in and not ext_in.startswith("."):
            ext_filter = "." + ext_in.lower()
        elif isinstance(ext_in, str):
            ext_filter = ext_in.lower()
        else:
            ext_filter = None
        min_size = criteria.get("min_size")
        max_size = criteria.get("max_size")

        results: List[Dict[str, Any]] = []
        total_count = 0
        for p in base_dir.glob("**/*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
                size = st.st_size
                if name_contains and name_contains not in p.name.lower():
                    continue
                if ext_filter and p.suffix.lower() != ext_filter:
                    continue
                if isinstance(min_size, (int, float)) and size < float(min_size):
                    continue
                if isinstance(max_size, (int, float)) and size > float(max_size):
                    continue

                entry: Dict[str, Any] = {
                    "name": p.name,
                    "path": str(p.resolve()),
                    "size": size,
                    "mtime": st.st_mtime,
                }
                if compute_hash:
                    try:
                        import hashlib

                        raw = p.read_bytes()
                        entry["hash"] = hashlib.sha256(raw).hexdigest()
                    except Exception:
                        entry["hash"] = None
                results.append(entry)
            except Exception:
                continue
        total_count = len(results)
        # Sort by mtime desc
        results.sort(key=lambda x: x.get("mtime", 0), reverse=True)
        return {"search_results": results, "total_count": total_count}