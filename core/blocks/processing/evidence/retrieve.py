from __future__ import annotations

from typing import Any, Dict
from pathlib import Path
import base64
import hashlib
import os

from core.blocks.base import BlockContext, ProcessingBlock


class EvidenceRetrieveBlock(ProcessingBlock):
    id = "evidence.retrieve"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        evidence_id = inputs.get("evidence_id")
        name = inputs.get("name")
        path_in = inputs.get("path")
        verify = bool(inputs.get("verify_integrity", True))
        return_base64 = bool(inputs.get("return_base64", True))

        base_dir = Path(os.getenv("KEIRI_AGENT_EVIDENCE_DIR", "runs/evidence"))
        base_dir.mkdir(parents=True, exist_ok=True)

        # Resolve candidate path
        candidate: Path | None = None
        if isinstance(path_in, str) and path_in:
            p = Path(path_in)
            candidate = p if p.is_absolute() else (base_dir / p)
            if not candidate.exists():
                candidate = None
        if candidate is None and isinstance(name, str) and name:
            p = base_dir / name
            if p.exists():
                candidate = p
        
        # If evidence_id is provided (sha256), scan for file with matching hash
        matched_hash: str | None = None
        if candidate is None and isinstance(evidence_id, str) and evidence_id:
            # Scan shallow (non-recursive) under base_dir
            for p in base_dir.glob("**/*"):
                if not p.is_file():
                    continue
                try:
                    # Quick check: if file name contains id, prefer it
                    if evidence_id in p.name:
                        candidate = p
                        matched_hash = evidence_id
                        break
                except Exception:
                    pass
            # If not found by name hint, compute hashes to match
            if candidate is None:
                for p in base_dir.glob("**/*"):
                    if not p.is_file():
                        continue
                    try:
                        raw = p.read_bytes()
                        h = hashlib.sha256(raw).hexdigest()
                        if h == evidence_id:
                            candidate = p
                            matched_hash = h
                            break
                    except Exception:
                        continue

        if candidate is None or not candidate.exists():
            return {"found": False, "error": "evidence_not_found"}

        raw = candidate.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        integrity_ok = True
        if verify:
            if isinstance(evidence_id, str) and evidence_id:
                integrity_ok = (sha256 == evidence_id)
            elif isinstance(matched_hash, str) and matched_hash:
                integrity_ok = (sha256 == matched_hash)
            else:
                integrity_ok = True

        meta = {
            "id": sha256,
            "name": candidate.name,
            "path": str(candidate.resolve()),
            "size": len(raw),
            "hash": sha256,
        }

        if return_base64:
            data_b64 = base64.b64encode(raw).decode("utf-8")
            return {"found": True, "evidence_data_base64": data_b64, "metadata": meta, "integrity_ok": bool(integrity_ok)}
        else:
            return {"found": True, "evidence_data_bytes": raw, "metadata": meta, "integrity_ok": bool(integrity_ok)}