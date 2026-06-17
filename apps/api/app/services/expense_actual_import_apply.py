"""Apply parsed expense actual import rows into the current raw import tables."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import app.core.aiosqlite_compat as aiosqlite
from app.services.expense_actual_import_batches import normalize_import_kind
from app.services.expense_actual_import_parser import ParsedActualDetailRow, build_preview_response
from app.schemas import ExpenseActualImportManageDepartmentWarning


NOTE_ALLOW_UNMATCHED = "允许未匹配明细入库并预警"


@dataclass(frozen=True)
class ExpenseActualImportApplyResult:
    batch_id: int
    import_kind: str
    file_name: str
    import_mode: str
    row_count: int
    periods: list[str]
    matched_owner_rows: int
    matched_subject_rows: int
    unmatched_rows: int
    note: str
    manage_department_warnings: list[ExpenseActualImportManageDepartmentWarning]


def _iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_import_mode(value: str | None) -> str:
    import_mode = (value or "").strip().lower()
    if import_mode not in {"append", "overwrite"}:
        raise ValueError("导入模式仅支持 append 或 overwrite")
    return import_mode


async def apply_expense_actual_import_rows(
    db_path: str | Path,
    *,
    import_kind: str,
    import_mode: str,
    file_name: str,
    rows: list[ParsedActualDetailRow],
    created_at: str | None = None,
) -> ExpenseActualImportApplyResult:
    normalized_import_kind = normalize_import_kind(import_kind)
    normalized_import_mode = _normalize_import_mode(import_mode)
    preview = build_preview_response(file_name, rows)
    periods = preview.periods

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        if normalized_import_mode == "overwrite" and periods:
            placeholders = ",".join("?" for _ in periods)
            await db.execute(
                f"DELETE FROM expense_actual_detail_raw WHERE import_kind = ? AND period_ym IN ({placeholders})",
                (normalized_import_kind, *periods),
            )
        cur = await db.execute(
            """
            INSERT INTO expense_actual_import_batch(
              import_kind, file_name, import_mode, periods_text, total_rows,
              matched_owner_rows, matched_subject_rows, unmatched_rows, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_import_kind,
                file_name,
                normalized_import_mode,
                ",".join(periods),
                preview.row_count,
                preview.matched_owner_rows,
                preview.matched_subject_rows,
                preview.unmatched_rows,
                created_at or _iso_now(),
                NOTE_ALLOW_UNMATCHED,
            ),
        )
        batch_id = int(cur.lastrowid)
        await db.executemany(
            """
            INSERT INTO expense_actual_detail_raw(
              batch_id, import_kind, data_date, period_ym, period_text, org_code, org_name, dep_code, dep_name,
              subject_code, subject_name, journal_name, serial_no, line_desc,
              amount, fee_type_code, fee_type_name,
              bi_ai_source_code, bi_ai_source_name, manage_department_code,
              owner_name_raw, owner_name_mapped, monthly_caliber,
              budget_subject_raw, budget_subject_mapped,
              fee_major_mapped, fee_category_mapped, budget_release_caliber_mapped,
              manage_department2, special_control_tag,
              owner_matched, subject_matched, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    batch_id,
                    normalized_import_kind,
                    row.data_date,
                    row.period_ym,
                    row.period_text,
                    row.org_code,
                    row.org_name,
                    row.dep_code,
                    row.dep_name,
                    row.subject_code,
                    row.subject_name,
                    row.journal_name,
                    row.serial_no,
                    row.line_desc,
                    row.amount,
                    row.fee_type_code,
                    row.fee_type_name,
                    row.bi_ai_source_code,
                    row.bi_ai_source_name,
                    row.manage_department_code,
                    row.owner_name_raw,
                    row.owner_name_mapped,
                    row.monthly_caliber,
                    row.budget_subject_raw,
                    row.budget_subject_mapped,
                    row.fee_major_mapped,
                    row.fee_category_mapped,
                    row.budget_release_caliber_mapped,
                    row.manage_department2,
                    row.special_control_tag,
                    1 if row.owner_matched else 0,
                    1 if row.subject_matched else 0,
                    row.match_note,
                )
                for row in rows
            ],
        )
        await db.commit()

    return ExpenseActualImportApplyResult(
        batch_id=batch_id,
        import_kind=normalized_import_kind,
        file_name=file_name,
        import_mode=normalized_import_mode,
        row_count=preview.row_count,
        periods=periods,
        matched_owner_rows=preview.matched_owner_rows,
        matched_subject_rows=preview.matched_subject_rows,
        unmatched_rows=preview.unmatched_rows,
        note=NOTE_ALLOW_UNMATCHED,
        manage_department_warnings=preview.manage_department_warnings,
    )
