from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import base64
import hashlib
import os

from core.blocks.base import BlockContext, ProcessingBlock


class EvidenceVaultStoreBlock(ProcessingBlock):
    id = "evidence.vault.store"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        items = inputs.get("items") or []
        retention = inputs.get("retention_policy") or {}
        access_policy = inputs.get("access_policy") or {}

        if not isinstance(items, list):
            items = []

        # Determine base directory for evidence storage
        base_dir = Path(os.getenv("KEIRI_AGENT_EVIDENCE_DIR", "runs/evidence"))
        base_dir.mkdir(parents=True, exist_ok=True)

        stored: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = it.get("name") or "artifact.bin"
            raw: bytes | None = None
            if isinstance(it.get("bytes"), (bytes, bytearray)):
                raw = bytes(it.get("bytes"))  # type: ignore[arg-type]
            elif isinstance(it.get("base64"), str):
                try:
                    raw = base64.b64decode(it.get("base64"))
                except Exception:
                    raw = None
            if raw is None:
                continue
            # compute hash for integrity
            sha256 = hashlib.sha256(raw).hexdigest()
            safe_name = "".join(c for c in str(name) if c not in '<>:"/\\|?*\n\r\t').strip() or f"evidence_{sha256[:8]}.bin"
            path = base_dir / safe_name
            path.write_bytes(raw)
            stored.append({
                "id": sha256,
                "name": safe_name,
                "path": str(path),
                "size": len(raw),
                "hash": sha256,
                "retention_policy": retention or {},
                "access_policy": access_policy or {},
            })

        return {"stored": stored, "summary": {"count": len(stored), "dir": str(base_dir)}}


