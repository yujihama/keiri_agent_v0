from __future__ import annotations

from typing import Any, Dict, List
from io import BytesIO

from openpyxl import load_workbook
from openpyxl.workbook import Workbook
from openpyxl.utils import get_column_letter
import base64

from core.blocks.base import BlockContext, ProcessingBlock


class ExcelWriteResultsBlock(ProcessingBlock):
    id = "excel.write_results"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Write match results into a provided workbook bytes.

        Inputs
        ------
        - workbook: { name: str, bytes: b"..." } or raw bytes
        - data: { matched: bool, items: [{file, count, sum}] }
        - output_config: { sheet: str, start_row: int, columns: ["A","B","C", ...] }

        Outputs
        -------
        - write_summary: { rows_written: int, sheet: str }
        """

        wb_bytes = None
        wb_name = None
        wb_input = inputs.get("workbook")
        if isinstance(wb_input, dict):
            wb_name = wb_input.get("name")
            wb_bytes = wb_input.get("bytes")
        elif isinstance(wb_input, (bytes, bytearray)):
            wb_bytes = wb_input

        if not isinstance(wb_bytes, (bytes, bytearray)):
            return {"write_summary": {"rows_written": 0, "sheet": None}}

        data = inputs.get("data") or {}
        # Normalize data: accept dict or JSON string; otherwise fallback to empty
        if isinstance(data, str):
            try:
                import json as _json
                data = _json.loads(data)
            except Exception:
                data = {}
        out_cfg = inputs.get("output_config") or {}
        # Normalize output_config as dict; if unresolved string, fallback to defaults
        if isinstance(out_cfg, str):
            out_cfg = {}
        sheet_name = out_cfg.get("sheet", "Results")
        start_row = int(out_cfg.get("start_row", 2))
        columns: List[str] = list(out_cfg.get("columns", ["A", "B", "C"]))
        # 列マッピング: キー名から列インデックスを解決可能に（列名指定優先、足りない場合は自動）
        header_map = out_cfg.get("header_map") or {"file": "File", "count": "Count", "sum": "Sum"}

        # Load workbook
        wb: Workbook = load_workbook(BytesIO(wb_bytes))
        ws = wb[sheet_name] if sheet_name in wb.sheetnames else wb.create_sheet(sheet_name)

        rows_written = 0
        items = data.get("items") or []
        # Ensure header
        if start_row > 1 and ws.max_row < start_row - 1:
            ws.cell(row=1, column=1, value=header_map.get("file", "File"))
            ws.cell(row=1, column=2, value=header_map.get("count", "Count"))
            ws.cell(row=1, column=3, value=header_map.get("sum", "Sum"))

        r = start_row
        for it in items:
            vals = [it.get("file"), it.get("count"), it.get("sum")]
            for idx, val in enumerate(vals, start=1):
                col = columns[idx - 1] if idx - 1 < len(columns) else get_column_letter(idx)
                ws.cell(row=r, column=idx, value=val)
            # 簡易な数値セルの書式設定（Sum列っぽい値に対して）
            try:
                sum_idx = 3
                if isinstance(vals[2], (int, float)):
                    ws.cell(row=r - 1, column=sum_idx).number_format = "#,##0.00"
            except Exception:
                pass
            r += 1
            rows_written += 1

        # Save back to bytes
        out_buf = BytesIO()
        wb.save(out_buf)
        out_buf.seek(0)
        out_bytes = out_buf.getvalue()

        summary = {"rows_written": rows_written, "sheet": sheet_name, "workbook_name": wb_name}
        # 書き戻ししたブックbytesも返せるように（今後の拡張用）
        # さらに base64 も提供して上位UIで安全に扱えるようにする
        return {
            "write_summary": summary,
            "workbook_updated": {"name": wb_name, "bytes": out_bytes},
            "workbook_b64": base64.b64encode(out_bytes).decode("ascii"),
        }


