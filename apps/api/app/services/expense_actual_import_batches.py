from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import app.core.aiosqlite_compat as aiosqlite
from openpyxl import Workbook

from app.schemas import ExpenseActualImportBatchRow


IMPORT_KIND_LABELS = {
    "current_year_actual": "本年实际导入",
    "prior_year_actual": "上年实际导入",
}


EXPORT_COLUMNS = [
    ("data_date", "数据日期"),
    ("org_code", "费用归属部门编码"),
    ("org_name", "费用部门"),
    ("dep_code", "责任中心编码"),
    ("dep_name", "责任中心"),
    ("subject_code", "科目编码"),
    ("subject_name", "科目描述"),
    ("period_text", "期间"),
    ("journal_name", "日记帐名"),
    ("serial_no", "流水号"),
    ("line_desc", "行说明"),
    ("amount", "金额"),
    ("fee_type_code", "费用类别编码"),
    ("fee_type_name", "费用类别"),
    ("bi_ai_source_code", "BI-AI源编码"),
    ("bi_ai_source_name", "BI-AI源名称"),
    ("manage_department_code", "归口管理部门编码"),
    ("owner_name_raw", "归口管理部门"),
    ("fee_major_mapped", "费用大类"),
    ("fee_category_mapped", "费用类别（一级）"),
    ("budget_release_caliber_mapped", "预算发布口径（二级）"),
    ("manage_department2", "归口管理部门2"),
    ("special_control_tag", "专项管控打标"),
    ("match_status", "匹配状态"),
    ("match_note", "说明"),
]


class ExpenseActualImportBatchMissingError(LookupError):
    pass


class ExpenseActualImportExportMissingError(LookupError):
    pass


@dataclass(frozen=True)
class ExpenseActualImportExportWorkbook:
    content: bytes
    filename: str


@dataclass(frozen=True)
class ExpenseActualImportDeletedBatch:
    batch_id: int
    deleted_rows: int
    file_name: str
    total_rows: int
    import_kind: str


def text_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_import_kind(value: str | None) -> str:
    import_kind = text_value(value) or "current_year_actual"
    if import_kind not in IMPORT_KIND_LABELS:
        raise ValueError("导入类型仅支持本年实际导入、上年实际导入")
    return import_kind


async def list_expense_actual_import_batches(
    db_path: Path,
    *,
    import_kind: str = "current_year_actual",
    limit: int = 20,
) -> list[ExpenseActualImportBatchRow]:
    normalized_import_kind = normalize_import_kind(import_kind)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, import_kind, file_name, import_mode, periods_text, total_rows,
                   matched_owner_rows, matched_subject_rows, unmatched_rows, created_at, note
            FROM expense_actual_import_batch
            WHERE import_kind = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (normalized_import_kind, limit),
        )
        rows = await cur.fetchall()
    return [
        ExpenseActualImportBatchRow(
            id=int(row[0]),
            import_kind=text_value(row[1]) or "current_year_actual",
            file_name=text_value(row[2]),
            import_mode=text_value(row[3]),
            periods=[item for item in text_value(row[4]).split(",") if item],
            total_rows=int(row[5] or 0),
            matched_owner_rows=int(row[6] or 0),
            matched_subject_rows=int(row[7] or 0),
            unmatched_rows=int(row[8] or 0),
            created_at=text_value(row[9]),
            note=text_value(row[10]) or None,
        )
        for row in rows
    ]


async def export_expense_actual_import_batch(
    db_path: Path,
    *,
    batch_id: int | None = None,
    import_kind: str = "current_year_actual",
) -> ExpenseActualImportExportWorkbook:
    normalized_import_kind = normalize_import_kind(import_kind)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        target_batch_id = batch_id
        if target_batch_id is None:
            cur = await db.execute(
                "SELECT MAX(id) FROM expense_actual_import_batch WHERE import_kind = ?",
                (normalized_import_kind,),
            )
            target_batch_id = int((await cur.fetchone())[0] or 0)
        if not target_batch_id:
            raise ExpenseActualImportExportMissingError("暂无可导出的费用执行明细导入批次")
        cur = await db.execute(
            """
            SELECT file_name, import_kind
            FROM expense_actual_import_batch
            WHERE id = ?
            """,
            (target_batch_id,),
        )
        batch_row = await cur.fetchone()
        if not batch_row:
            raise ExpenseActualImportBatchMissingError("导入批次不存在")
        batch_import_kind = text_value(batch_row[1]) or "current_year_actual"
        cur = await db.execute(
            """
            SELECT period_ym, org_code, org_name, dep_code, dep_name,
                   subject_code, subject_name, amount, fee_type_code, fee_type_name,
                   bi_ai_source_code, bi_ai_source_name, manage_department_code,
                   owner_name_raw, owner_name_mapped, monthly_caliber,
                   budget_subject_raw, budget_subject_mapped,
                   fee_major_mapped, fee_category_mapped, budget_release_caliber_mapped,
                   manage_department2, special_control_tag,
                   period_text, match_note, journal_name, serial_no, line_desc, data_date
            FROM expense_actual_detail_raw
            WHERE batch_id = ?
            ORDER BY id
            """,
            (target_batch_id,),
        )
        rows = await cur.fetchall()
    if not rows:
        raise ExpenseActualImportExportMissingError("该导入批次没有可导出的明细")

    wb = Workbook()
    ws = wb.active
    ws.title = "费用执行明细匹配结果"
    ws.append([label for _key, label in EXPORT_COLUMNS])
    for row in rows:
        row_data: dict[str, str | float] = {
            "period_ym": text_value(row[0]),
            "org_code": text_value(row[1]),
            "org_name": text_value(row[2]),
            "dep_code": text_value(row[3]),
            "dep_name": text_value(row[4]),
            "subject_code": text_value(row[5]),
            "subject_name": text_value(row[6]),
            "amount": float(row[7] or 0),
            "fee_type_code": text_value(row[8]),
            "fee_type_name": text_value(row[9]),
            "bi_ai_source_code": text_value(row[10]),
            "bi_ai_source_name": text_value(row[11]),
            "manage_department_code": text_value(row[12]),
            "owner_name_raw": text_value(row[13]),
            "owner_name_mapped": text_value(row[14]),
            "monthly_caliber": text_value(row[15]),
            "budget_subject_raw": text_value(row[16]),
            "budget_subject_mapped": text_value(row[17]),
            "fee_major_mapped": text_value(row[18]),
            "fee_category_mapped": text_value(row[19]),
            "budget_release_caliber_mapped": text_value(row[20]),
            "manage_department2": text_value(row[21]),
            "special_control_tag": text_value(row[22]),
            "period_text": text_value(row[23]) or text_value(row[0]),
            "journal_name": text_value(row[25]),
            "serial_no": text_value(row[26]),
            "line_desc": text_value(row[27]),
            "data_date": text_value(row[28]),
            "match_note": text_value(row[24]),
        }
        row_data["match_status"] = (
            "已匹配"
            if not row_data["match_note"]
            else "部分匹配"
            if row_data["owner_name_mapped"] or row_data["budget_subject_mapped"] or row_data["manage_department2"]
            else "未匹配"
        )
        ws.append([row_data.get(key, "") for key, _label in EXPORT_COLUMNS])

    for column_cells in ws.columns:
        width = min(max(len(str(cell.value or "")) for cell in column_cells) + 2, 32)
        ws.column_dimensions[column_cells[0].column_letter].width = width

    buffer = BytesIO()
    wb.save(buffer)
    filename = f"{IMPORT_KIND_LABELS.get(batch_import_kind, '费用执行明细')}_匹配结果_批次{target_batch_id}.xlsx"
    return ExpenseActualImportExportWorkbook(content=buffer.getvalue(), filename=filename)


async def delete_expense_actual_import_batch(
    db_path: Path,
    *,
    batch_id: int,
) -> ExpenseActualImportDeletedBatch:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT file_name, total_rows, import_kind
            FROM expense_actual_import_batch
            WHERE id = ?
            """,
            (batch_id,),
        )
        batch_row = await cur.fetchone()
        if not batch_row:
            raise ExpenseActualImportBatchMissingError("导入批次不存在")
        detail_cur = await db.execute("DELETE FROM expense_actual_detail_raw WHERE batch_id = ?", (batch_id,))
        batch_cur = await db.execute("DELETE FROM expense_actual_import_batch WHERE id = ?", (batch_id,))
        await db.commit()
    if batch_cur.rowcount == 0:
        raise ExpenseActualImportBatchMissingError("导入批次不存在")
    return ExpenseActualImportDeletedBatch(
        batch_id=batch_id,
        deleted_rows=int(detail_cur.rowcount or 0),
        file_name=text_value(batch_row[0]),
        total_rows=int(batch_row[1] or 0),
        import_kind=text_value(batch_row[2]) or "current_year_actual",
    )
