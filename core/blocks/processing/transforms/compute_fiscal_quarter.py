from __future__ import annotations

from typing import Any, Dict
from datetime import date, timedelta

from core.blocks.base import BlockContext, ProcessingBlock


class ComputeFiscalQuarterBlock(ProcessingBlock):
    id = "transforms.compute_fiscal_quarter"
    version = "0.1.0"

    def run(self, ctx: BlockContext, inputs: Dict[str, Any]) -> Dict[str, Any]:
        # 入力値の正規化
        try:
            fiscal_year = int(inputs.get("fiscal_year"))
        except (TypeError, ValueError):
            fiscal_year = 0

        quarter_str = str(inputs.get("quarter") or "").upper().replace("Q", "").strip()
        try:
            quarter = int(quarter_str)
        except (TypeError, ValueError):
            quarter = 0

        try:
            fiscal_start_month = int(inputs.get("start_month") or 4)
        except (TypeError, ValueError):
            fiscal_start_month = 4

        if (
            fiscal_year <= 0
            or quarter not in {1, 2, 3, 4}
            or not (1 <= fiscal_start_month <= 12)
        ):
            return {
                "period": {"start": None, "end": None},
                "is_q1": False,
                "target_sheet_name": "",
                "template_sheet_name": "",
                "quarter_label": "",
            }

        # ユーティリティ: 月加算（1日固定）
        def add_months(d: date, months: int) -> date:
            total_months = d.year * 12 + (d.month - 1) + months
            year = total_months // 12
            month = total_months % 12 + 1
            return date(year, month, 1)

        # 期首日（例: 2025年度・4月始まり -> 2025-04-01）
        fiscal_year_start = date(fiscal_year, fiscal_start_month, 1)

        # 対象四半期の開始・終了日
        offset_months = (quarter - 1) * 3
        quarter_start = add_months(fiscal_year_start, offset_months)
        quarter_end = add_months(quarter_start, 3) - timedelta(days=1)

        # 対象四半期と前四半期のシート名（YYYY.M）
        target_end_month = quarter_end.month
        target_sheet_year = quarter_end.year

        prev_quarter_start = add_months(quarter_start, -3)
        prev_quarter_end = add_months(prev_quarter_start, 3) - timedelta(days=1)
        prev_end_month = prev_quarter_end.month
        prev_sheet_year = prev_quarter_end.year

        target_sheet = f"{target_sheet_year}.{target_end_month}"
        template_sheet = f"{prev_sheet_year}.{prev_end_month}"

        # ラベル（例: 2025年度4月～6月）
        label = f"{fiscal_year}年度{quarter_start.month}月～{quarter_end.month}月"

        return {
            "period": {"start": quarter_start.isoformat(), "end": quarter_end.isoformat()},
            "is_q1": quarter == 1,
            "target_sheet_name": target_sheet,
            "template_sheet_name": template_sheet,
            "quarter_label": label,
        }


