from __future__ import annotations

from core.blocks.base import BlockContext
from core.blocks.processing.table.unpivot import TableUnpivotBlock
from core.blocks.processing.table.pivot import TablePivotBlock


def test_unpivot_then_pivot_salary_excel_roundtrip():
    ctx = BlockContext(run_id="test_unpivot_salary")
    # ピボット横持ちの最小データ（1行=項目、列=氏名）
    rows_norm = [
        {"項目": "社員番号", "山田太郎": 1001, "田中花子": 1002},
        {"項目": "支給日", "山田太郎": "2025-06-30", "田中花子": "2025-06-30"},
        {"項目": "基本給", "山田太郎": 500000, "田中花子": 450000},
    ]
    assert rows_norm and "項目" in rows_norm[0]

    # 3) アンピボット（縦持ち化）
    unpivoted = TableUnpivotBlock().run(
        ctx,
        {
            "rows": rows_norm,
            "id_vars": "項目",
            "var_name": "氏名",
            "value_name": "value",
        },
    )
    rows_unpivot = unpivoted.get("rows") or []
    assert rows_unpivot and {"項目", "氏名", "value"}.issubset(rows_unpivot[0].keys())

    # 4) ピボットで行に復元
    pivoted = TablePivotBlock().run(
        ctx,
        {
            "rows": rows_unpivot,
            "index": "氏名",
            "columns": "項目",
            "values": "value",
            "aggfunc": "first",
            "flatten_multiindex": True,
        },
    )
    rows_final = pivoted.get("rows") or []
    assert rows_final and "氏名" in rows_final[0]
    # 代表的な項目列が復元されていること
    assert {"社員番号", "支給日", "基本給"}.issubset(rows_final[0].keys())


