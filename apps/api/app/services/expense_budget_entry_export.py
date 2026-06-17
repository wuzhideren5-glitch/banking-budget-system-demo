from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from openpyxl import Workbook

from app.services.expense_budget_entry_parser import ParsedBudgetEntryRow
from app.services.expense_budget_entry_units import amount_unit_meta, from_base_amount


@dataclass(frozen=True)
class ExpenseBudgetEntryExportWorkbook:
    content: bytes
    filename: str


def build_matched_preview_export_workbook(
    *,
    rows: list[ParsedBudgetEntryRow],
    file_name: str,
    amount_unit: str,
) -> ExpenseBudgetEntryExportWorkbook:
    unit_label, _divisor = amount_unit_meta(amount_unit)
    wb = Workbook()
    ws = wb.active
    ws.title = "预算匹配结果"
    headers = [
        "部门",
        "预算科目",
        f"预算金额（{unit_label}）",
        "匹配部门",
        "匹配科目",
        "匹配状态",
        "说明",
    ]
    ws.append(headers)
    for row in rows:
        match_status = "已匹配" if row.owner_matched and row.subject_matched else "待确认"
        ws.append(
            [
                row.owner_name_raw,
                row.budget_subject_raw,
                from_base_amount(row.amount, amount_unit),
                row.owner_name_mapped or "",
                row.budget_subject_mapped or "",
                match_status,
                row.match_note or "",
            ]
        )

    for column_cells in ws.columns:
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 32)
        ws.column_dimensions[column_cells[0].column_letter].width = width

    buffer = BytesIO()
    wb.save(buffer)
    stem = file_name.rsplit(".", 1)[0] if file_name else "预算录入"
    return ExpenseBudgetEntryExportWorkbook(
        content=buffer.getvalue(),
        filename=f"预算录入_匹配结果_{stem}.xlsx",
    )
