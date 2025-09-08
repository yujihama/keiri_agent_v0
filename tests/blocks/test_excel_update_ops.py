from __future__ import annotations

from core.blocks.base import BlockContext
from core.blocks.processing.excel.write import ExcelWriteBlock
from core.blocks.processing.excel.update_workbook import ExcelUpdateWorkbookBlock


CTX = BlockContext(run_id="unit")


def test_excel_update_rename_move_and_clear_cells():
    # start with new workbook via excel.write
    w = ExcelWriteBlock().run(CTX, {"workbook": b""})
    wb = w["workbook_updated"]

    upd = ExcelUpdateWorkbookBlock()
    out = upd.run(
        CTX,
        {
            "workbook": {"name": "t.xlsx", "bytes": wb["bytes"]},
            "operations": [
                {"type": "add_sheet", "sheet_name": "S1"},
                {"type": "update_cells", "sheet_name": "S1", "cells": {"A1": "X", "B2": 1}},
                # copy then move
                {"type": "copy_sheet", "sheet_name": "S1", "target": "S2"},
                {"type": "move_sheet", "sheet_name": "S2", "position": "first"},
                # clear specific cells
                {"type": "clear_cells", "sheet_name": "S2", "targets": ["A1", "B2"]},
            ],
        },
    )
    assert isinstance(out.get("workbook_updated"), dict)
    summary = out.get("summary") or {}
    # at least 2 cells were updated then cleared, counts reflect total operations executed
    assert summary.get("operations") >= 5
    assert summary.get("cells_updated") >= 2

