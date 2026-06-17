from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite

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

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        if normalized_import_mode == "overwrite":
            await db.execute("DELETE FROM expense_budget_entry WHERE budget_year = ?", (budget_year,))
            await db.execute("DELETE FROM expense_budget_entry_batch WHERE budget_year = ?", (budget_year,))
        cur = await db.execute(
            """
            INSERT INTO expense_budget_entry_batch(
              budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                budget_year,
                file_name,
                normalized_import_mode,
                len(importable_rows),
                len(importable_rows),
                len(skipped_rows),
                created_at or _iso_now(),
                NOTE_MATCHED_ONLY,
            ),
        )
        batch_id = int(cur.lastrowid)
        entry_rows = [
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
        await db.executemany(
            """
            INSERT INTO expense_budget_entry(
              batch_id, budget_year, owner_name_raw, owner_name_mapped,
              budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
              owner_matched, subject_matched, match_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            entry_rows,
        )
        await db.commit()

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
