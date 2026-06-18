from __future__ import annotations

import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.services.expense_budget_entry_parser import ParsedBudgetEntryRow


NOTE_MATCHED_ONLY = "仅导入已匹配行"


def _is_matched_row(row: ParsedBudgetEntryRow) -> bool:
    return row.owner_matched and row.subject_matched


def matched_budget_entry_rows(rows: list[ParsedBudgetEntryRow]) -> list[ParsedBudgetEntryRow]:
    return [row for row in rows if _is_matched_row(row)]


def unmatched_budget_entry_rows(rows: list[ParsedBudgetEntryRow]) -> list[ParsedBudgetEntryRow]:
    return [row for row in rows if not _is_matched_row(row)]


@dataclass(frozen=True)
class ExpenseBudgetEntryApplyResult:
    batch_id: int
    budget_year: int
    file_name: str
    import_mode: str
    row_count: int
    matched_rows: int
    unmatched_rows: int
    note: str


def _iso_now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_import_mode(value: str | None) -> str:
    import_mode = (value or "").strip().lower()
    if import_mode not in {"append", "overwrite"}:
        raise ValueError("导入模式仅支持 append 或 overwrite")
    return import_mode


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


def _mysql_sql(sql: str) -> str:
    return sql.replace("?", "%s")


BATCH_INSERT_SQL = """
INSERT INTO expense_budget_entry_batch(
  budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


ENTRY_INSERT_SQL = """
INSERT INTO expense_budget_entry(
  batch_id, budget_year, owner_name_raw, owner_name_mapped,
  budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
  owner_matched, subject_matched, match_note
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _entry_values(
    *,
    batch_id: int,
    budget_year: int,
    importable_rows: list[ParsedBudgetEntryRow],
    skipped_rows: list[ParsedBudgetEntryRow],
) -> list[tuple[Any, ...]]:
    return [
        (
            batch_id,
            budget_year,
            row.owner_name_raw,
            row.owner_name_mapped,
            row.budget_subject_raw,
            row.budget_subject_mapped,
            row.amount,
            0.0,
            1,
            1,
            row.match_note,
        )
        for row in importable_rows
    ] + [
        (
            batch_id,
            budget_year,
            row.owner_name_raw,
            row.owner_name_mapped,
            row.budget_subject_raw,
            row.budget_subject_mapped,
            row.amount,
            0.0,
            1 if row.owner_matched else 0,
            1 if row.subject_matched else 0,
            row.match_note,
        )
        for row in skipped_rows
    ]


async def _apply_expense_budget_entry_rows_mysql(
    *,
    budget_year: int,
    import_mode: str,
    file_name: str,
    importable_rows: list[ParsedBudgetEntryRow],
    skipped_rows: list[ParsedBudgetEntryRow],
    created_at: str,
) -> int:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                if import_mode == "overwrite":
                    await cur.execute("DELETE FROM expense_budget_entry WHERE budget_year = %s", (budget_year,))
                    await cur.execute("DELETE FROM expense_budget_entry_batch WHERE budget_year = %s", (budget_year,))
                await cur.execute(
                    _mysql_sql(BATCH_INSERT_SQL),
                    (
                        budget_year,
                        file_name,
                        import_mode,
                        len(importable_rows),
                        len(importable_rows),
                        len(skipped_rows),
                        created_at,
                        NOTE_MATCHED_ONLY,
                    ),
                )
                batch_id = int(cur.lastrowid)
                values = _entry_values(
                    batch_id=batch_id,
                    budget_year=budget_year,
                    importable_rows=importable_rows,
                    skipped_rows=skipped_rows,
                )
                if values:
                    await cur.executemany(_mysql_sql(ENTRY_INSERT_SQL), values)
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return batch_id


async def _apply_expense_budget_entry_rows_sqlite(
    db_path: Path,
    *,
    budget_year: int,
    import_mode: str,
    file_name: str,
    importable_rows: list[ParsedBudgetEntryRow],
    skipped_rows: list[ParsedBudgetEntryRow],
    created_at: str,
) -> int:
    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        if import_mode == "overwrite":
            db.execute("DELETE FROM expense_budget_entry WHERE budget_year = ?", (budget_year,))
            db.execute("DELETE FROM expense_budget_entry_batch WHERE budget_year = ?", (budget_year,))
        cur = db.execute(
            BATCH_INSERT_SQL,
            (
                budget_year,
                file_name,
                import_mode,
                len(importable_rows),
                len(importable_rows),
                len(skipped_rows),
                created_at,
                NOTE_MATCHED_ONLY,
            ),
        )
        batch_id = int(cur.lastrowid)
        values = _entry_values(
            batch_id=batch_id,
            budget_year=budget_year,
            importable_rows=importable_rows,
            skipped_rows=skipped_rows,
        )
        if values:
            db.executemany(ENTRY_INSERT_SQL, values)
        db.commit()
    return batch_id


async def apply_expense_budget_entry_rows(
    db_path: str | Path,
    *,
    budget_year: int,
    import_mode: str,
    file_name: str,
    rows: list[ParsedBudgetEntryRow],
    created_at: str | None = None,
) -> ExpenseBudgetEntryApplyResult:
    normalized_import_mode = _normalize_import_mode(import_mode)
    importable_rows = matched_budget_entry_rows(rows)
    skipped_rows = unmatched_budget_entry_rows(rows)
    if not importable_rows:
        raise ValueError("没有可导入的已匹配预算行，请修正 Excel 中未匹配的部门或预算科目后再试")

    effective_created_at = created_at or _iso_now()
    apply_kwargs = {
        "budget_year": budget_year,
        "import_mode": normalized_import_mode,
        "file_name": file_name,
        "importable_rows": importable_rows,
        "skipped_rows": skipped_rows,
        "created_at": effective_created_at,
    }
    path = Path(db_path)
    if _uses_mysql_path(path):
        batch_id = await _apply_expense_budget_entry_rows_mysql(**apply_kwargs)
    else:
        batch_id = await _apply_expense_budget_entry_rows_sqlite(path, **apply_kwargs)

    return ExpenseBudgetEntryApplyResult(
        batch_id=batch_id,
        budget_year=budget_year,
        file_name=file_name,
        import_mode=normalized_import_mode,
        row_count=len(importable_rows),
        matched_rows=len(importable_rows),
        unmatched_rows=len(skipped_rows),
        note=NOTE_MATCHED_ONLY,
    )
