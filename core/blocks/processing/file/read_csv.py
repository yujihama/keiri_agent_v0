from __future__ import annotations

from typing import Any, Dict, List

import csv

from core.blocks.base import BlockContext, ProcessingBlock
from core.plan.logger import export_log


class ReadCSVBlock(ProcessingBlock):
    id = "file.read_csv"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        path = str(inputs.get("path") or "")
        encoding = str(inputs.get("encoding") or "utf-8")
        delimiter = str(inputs.get("delimiter") or ",")
        has_header = bool(inputs.get("has_header", True))
        data_bytes = inputs.get("bytes")

        if not path and not isinstance(data_bytes, (bytes, bytearray)):
            return {"rows": [], "summary": {"path": path, "rows": 0}}

        rows: List[Dict[str, Any]] = []
        try:
            if isinstance(data_bytes, (bytes, bytearray)):
                text = data_bytes.decode(encoding, errors="replace")
                from io import StringIO
                f = StringIO(text)
            else:
                f = open(path, "r", encoding=encoding, newline="")
            with f:
                if has_header:
                    reader = csv.DictReader(f, delimiter=delimiter)
                    for r in reader:
                        rows.append(dict(r))
                else:
                    reader = csv.reader(f, delimiter=delimiter)
                    for r in reader:
                        rows.append({str(i): v for i, v in enumerate(r)})
        except Exception:
            return {"rows": [], "summary": {"path": path, "rows": 0, "error": True}}

        # ログ: 概要（列名と件数のみ）
        try:
            cols = list(rows[0].keys()) if rows else []
            export_log({"source": path or "<bytes>", "rows": len(rows), "columns": cols[:50]}, ctx=ctx, tag="file.read_csv")
        except Exception:
            pass

        return {"rows": rows, "summary": {"path": path, "rows": len(rows)}}


