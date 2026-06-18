from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from app.core.config import settings
from app.core.database import get_pool
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


def _uses_mysql_path(path: Path | str) -> bool:
    try:
        candidate = Path(path).expanduser().resolve()
    except TypeError:
        return False
    temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    try:
        candidate.relative_to(temp_root)
        return False
    except ValueError:
        pass
    data_dir = Path(settings.data_dir).expanduser().resolve()
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return candidate.name == "common.db"


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


async def _fetch_all_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_all(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchall()


async def _fetch_one_for_path(db_path: Path, sql: str, params: tuple[Any, ...] = ()) -> Any:
    if _uses_mysql_path(db_path):
        return await get_pool().fetch_one(_mysql_sql(sql), params)
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        return db.execute(sql, params).fetchone()


async def _delete_batch_for_path(db_path: Path, batch_id: int) -> tuple[Any, int, int]:
    if _uses_mysql_path(db_path):
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT file_name, total_rows, import_kind
                        FROM expense_actual_import_batch
                        WHERE id = %s
                        """,
                        (batch_id,),
                    )
                    batch_row = await cur.fetchone()
                    if not batch_row:
                        raise ExpenseActualImportBatchMissingError("导入批次不存在")
                    await cur.execute("DELETE FROM expense_actual_detail_raw WHERE batch_id = %s", (batch_id,))
                    deleted_rows = int(cur.rowcount or 0)
                    await cur.execute("DELETE FROM expense_actual_import_batch WHERE id = %s", (batch_id,))
                    deleted_batches = int(cur.rowcount or 0)
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return batch_row, deleted_rows, deleted_batches

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        batch_row = db.execute(
            """
            SELECT file_name, total_rows, import_kind
            FROM expense_actual_import_batch
            WHERE id = ?
            """,
            (batch_id,),
        ).fetchone()
        if not batch_row:
            raise ExpenseActualImportBatchMissingError("导入批次不存在")
        detail_cur = db.execute("DELETE FROM expense_actual_detail_raw WHERE batch_id = ?", (batch_id,))
        batch_cur = db.execute("DELETE FROM expense_actual_import_batch WHERE id = ?", (batch_id,))
        db.commit()
    return batch_row, int(detail_cur.rowcount or 0), int(batch_cur.rowcount or 0)


async def list_expense_actual_import_batches(
    db_path: Path,
    *,
    import_kind: str = "current_year_actual",
    limit: int = 20,
) -> list[ExpenseActualImportBatchRow]:
    normalized_import_kind = normalize_import_kind(import_kind)
    rows = await _fetch_all_for_path(
        db_path,
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
    return [
        ExpenseActualImportBatchRow(
            id=int(_row_value(row, "id", 0)),
            import_kind=text_value(_row_value(row, "import_kind", 1)) or "current_year_actual",
            file_name=text_value(_row_value(row, "file_name", 2)),
            import_mode=text_value(_row_value(row, "import_mode", 3)),
            periods=[item for item in text_value(_row_value(row, "periods_text", 4)).split(",") if item],
            total_rows=int(_row_value(row, "total_rows", 5) or 0),
            matched_owner_rows=int(_row_value(row, "matched_owner_rows", 6) or 0),
            matched_subject_rows=int(_row_value(row, "matched_subject_rows", 7) or 0),
            unmatched_rows=int(_row_value(row, "unmatched_rows", 8) or 0),
            created_at=text_value(_row_value(row, "created_at", 9)),
            note=text_value(_row_value(row, "note", 10)) or None,
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
    target_batch_id = batch_id
    if target_batch_id is None:
        row = await _fetch_one_for_path(
            db_path,
            "SELECT MAX(id) AS max_id FROM expense_actual_import_batch WHERE import_kind = ?",
            (normalized_import_kind,),
        )
        target_batch_id = int(_row_value(row, "max_id", 0) or 0) if row else 0
    if not target_batch_id:
        raise ExpenseActualImportExportMissingError("暂无可导出的费用执行明细导入批次")
    batch_row = await _fetch_one_for_path(
        db_path,
        """
        SELECT file_name, import_kind
        FROM expense_actual_import_batch
        WHERE id = ?
        """,
        (target_batch_id,),
    )
    if not batch_row:
        raise ExpenseActualImportBatchMissingError("导入批次不存在")
    batch_import_kind = text_value(_row_value(batch_row, "import_kind", 1)) or "current_year_actual"
    rows = await _fetch_all_for_path(
        db_path,
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
    if not rows:
        raise ExpenseActualImportExportMissingError("该导入批次没有可导出的明细")

    wb = Workbook()
    ws = wb.active
    ws.title = "费用执行明细匹配结果"
    ws.append([label for _key, label in EXPORT_COLUMNS])
    for row in rows:
        row_data: dict[str, str | float] = {
            "period_ym": text_value(_row_value(row, "period_ym", 0)),
            "org_code": text_value(_row_value(row, "org_code", 1)),
            "org_name": text_value(_row_value(row, "org_name", 2)),
            "dep_code": text_value(_row_value(row, "dep_code", 3)),
            "dep_name": text_value(_row_value(row, "dep_name", 4)),
            "subject_code": text_value(_row_value(row, "subject_code", 5)),
            "subject_name": text_value(_row_value(row, "subject_name", 6)),
            "amount": float(_row_value(row, "amount", 7) or 0),
            "fee_type_code": text_value(_row_value(row, "fee_type_code", 8)),
            "fee_type_name": text_value(_row_value(row, "fee_type_name", 9)),
            "bi_ai_source_code": text_value(_row_value(row, "bi_ai_source_code", 10)),
            "bi_ai_source_name": text_value(_row_value(row, "bi_ai_source_name", 11)),
            "manage_department_code": text_value(_row_value(row, "manage_department_code", 12)),
            "owner_name_raw": text_value(_row_value(row, "owner_name_raw", 13)),
            "owner_name_mapped": text_value(_row_value(row, "owner_name_mapped", 14)),
            "monthly_caliber": text_value(_row_value(row, "monthly_caliber", 15)),
            "budget_subject_raw": text_value(_row_value(row, "budget_subject_raw", 16)),
            "budget_subject_mapped": text_value(_row_value(row, "budget_subject_mapped", 17)),
            "fee_major_mapped": text_value(_row_value(row, "fee_major_mapped", 18)),
            "fee_category_mapped": text_value(_row_value(row, "fee_category_mapped", 19)),
            "budget_release_caliber_mapped": text_value(_row_value(row, "budget_release_caliber_mapped", 20)),
            "manage_department2": text_value(_row_value(row, "manage_department2", 21)),
            "special_control_tag": text_value(_row_value(row, "special_control_tag", 22)),
            "period_text": text_value(_row_value(row, "period_text", 23))
            or text_value(_row_value(row, "period_ym", 0)),
            "journal_name": text_value(_row_value(row, "journal_name", 25)),
            "serial_no": text_value(_row_value(row, "serial_no", 26)),
            "line_desc": text_value(_row_value(row, "line_desc", 27)),
            "data_date": text_value(_row_value(row, "data_date", 28)),
            "match_note": text_value(_row_value(row, "match_note", 24)),
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
    batch_row, deleted_rows, deleted_batches = await _delete_batch_for_path(db_path, batch_id)
    if deleted_batches == 0:
        raise ExpenseActualImportBatchMissingError("导入批次不存在")
    return ExpenseActualImportDeletedBatch(
        batch_id=batch_id,
        deleted_rows=deleted_rows,
        file_name=text_value(_row_value(batch_row, "file_name", 0)),
        total_rows=int(_row_value(batch_row, "total_rows", 1) or 0),
        import_kind=text_value(_row_value(batch_row, "import_kind", 2)) or "current_year_actual",
    )
