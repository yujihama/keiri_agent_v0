from __future__ import annotations

from typing import Any, Dict, List
from pathlib import Path
import csv
import os
import time
import hashlib

from core.blocks.base import BlockContext, ProcessingBlock


class EvidenceAuditReportBlock(ProcessingBlock):
    id = "evidence.audit_report"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        scope = inputs.get("report_scope") or {}
        verify = bool(inputs.get("verify_integrity", False))
        
        base_dir = Path(os.getenv("KEIRI_AGENT_EVIDENCE_DIR", "runs/evidence"))
        base_dir.mkdir(parents=True, exist_ok=True)

        rows: List[Dict[str, Any]] = []
        for p in base_dir.glob("**/*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
                row: Dict[str, Any] = {
                    "name": p.name,
                    "path": str(p.resolve()),
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
                if verify:
                    try:
                        raw = p.read_bytes()
                        row["hash"] = hashlib.sha256(raw).hexdigest()
                    except Exception:
                        row["hash"] = None
                rows.append(row)
            except Exception:
                continue

        ts = time.strftime("%Y%m%dT%H%M%S")
        report_dir = base_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / f"evidence_audit_{ts}.csv"
        with report_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["name", "path", "size", "mtime", "hash"]) 
            writer.writeheader()
            for r in rows:
                writer.writerow(r)

        return {
            "audit_report": {
                "count": len(rows),
                "verified": verify,
            },
            "report_file_path": str(report_path.resolve()),
        }