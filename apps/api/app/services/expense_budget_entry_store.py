from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import app.core.aiosqlite_compat as aiosqlite
from app.schemas import ExpenseBudgetEntryBatchRow, ExpenseBudgetEntryRow
from app.services.expense_budget_entry_amounts import (
    expense_budget_adjusted_amount,
    resolve_expense_budget_subject_total,
)
from app.core.db_paths import common_db_path
from app.services.expense_budget_execution_framework import (
    FrameworkContext,
    canonical_owner_name,
    canonical_subject,
    text,
)


class ExpenseBudgetEntryBatchMissingError(LookupError):
    pass


class ExpenseBudgetEntryRowMissingError(LookupError):
    pass


def _row_from_db(row: tuple) -> ExpenseBudgetEntryRow:
    amount = float(row[7] or 0.0)
    adjustment_amount = float(row[8] or 0.0)
    return ExpenseBudgetEntryRow(
        id=int(row[0]),
        batch_id=int(row[1]),
        budget_year=int(row[2]),
        owner_name_raw=text(row[3]),
        owner_name_mapped=text(row[4]) or None,
        budget_subject_raw=text(row[5]),
        budget_subject_mapped=text(row[6]) or None,
        amount=amount,
        adjustment_amount=adjustment_amount,
        adjusted_amount=expense_budget_adjusted_amount(amount, adjustment_amount),
        match_status=_match_status(row[9], row[10]),
        match_note=text(row[11]) or None,
    )


_SELECT_ENTRY_COLUMNS = """
    id, batch_id, budget_year, owner_name_raw, owner_name_mapped,
    budget_subject_raw, budget_subject_mapped, amount, adjustment_amount,
    owner_matched, subject_matched, match_note
"""


def _match_status(owner_matched: int, subject_matched: int) -> str:
    return "已匹配" if int(owner_matched) == 1 and int(subject_matched) == 1 else "待确认"


async def list_expense_budget_entry_batches(
    db_path: Path,
    *,
    budget_year: int,
    limit: int = 20,
) -> list[ExpenseBudgetEntryBatchRow]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
            FROM expense_budget_entry_batch
            WHERE budget_year = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (budget_year, limit),
        )
        rows = await cur.fetchall()
    return [
        ExpenseBudgetEntryBatchRow(
            id=int(row[0]),
            budget_year=int(row[1]),
            file_name=text(row[2]),
            import_mode=text(row[3]),
            total_rows=int(row[4] or 0),
            matched_rows=int(row[5] or 0),
            unmatched_rows=int(row[6] or 0),
            created_at=text(row[7]),
            note=text(row[8]) or None,
        )
        for row in rows
    ]


async def list_expense_budget_entries(
    db_path: Path,
    *,
    budget_year: int,
    batch_id: int | None = None,
    limit: int = 500,
) -> list[ExpenseBudgetEntryRow]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        if batch_id is not None:
            cur = await db.execute(
                f"""
                SELECT {_SELECT_ENTRY_COLUMNS}
                FROM expense_budget_entry
                WHERE budget_year = ? AND batch_id = ?
                ORDER BY id
                LIMIT ?
                """,
                (budget_year, batch_id, limit),
            )
        else:
            cur = await db.execute(
                f"""
                SELECT {_SELECT_ENTRY_COLUMNS}
                FROM expense_budget_entry
                WHERE budget_year = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (budget_year, limit),
            )
        rows = await cur.fetchall()
    return [_row_from_db(row) for row in rows]


async def delete_expense_budget_entry_batch(db_path: Path, *, batch_id: int) -> int:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT id FROM expense_budget_entry_batch WHERE id = ?", (batch_id,))
        row = await cur.fetchone()
        if not row:
            raise ExpenseBudgetEntryBatchMissingError(f"导入批次 {batch_id} 不存在")
        cur = await db.execute("SELECT COUNT(*) FROM expense_budget_entry WHERE batch_id = ?", (batch_id,))
        deleted_rows = int((await cur.fetchone())[0])
        await db.execute("DELETE FROM expense_budget_entry_batch WHERE id = ?", (batch_id,))
        await db.commit()
    return deleted_rows


async def update_expense_budget_entry_row(
    db_path: Path,
    *,
    row_id: int,
    amount: float | None = None,
    adjustment_amount: float | None = None,
) -> ExpenseBudgetEntryRow:
    if amount is None and adjustment_amount is None:
        raise ValueError("请至少提供预算金额或预算调整金额")

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            f"SELECT {_SELECT_ENTRY_COLUMNS} FROM expense_budget_entry WHERE id = ?",
            (row_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise ExpenseBudgetEntryRowMissingError(f"预算录入行 {row_id} 不存在")

        next_amount = float(amount if amount is not None else row[7] or 0.0)
        next_adjustment = float(adjustment_amount if adjustment_amount is not None else row[8] or 0.0)
        await db.execute(
            """
            UPDATE expense_budget_entry
            SET amount = ?, adjustment_amount = ?
            WHERE id = ?
            """,
            (next_amount, next_adjustment, row_id),
        )
        await db.commit()
        cur = await db.execute(
            f"SELECT {_SELECT_ENTRY_COLUMNS} FROM expense_budget_entry WHERE id = ?",
            (row_id,),
        )
        updated = await cur.fetchone()
    if not updated:
        raise ExpenseBudgetEntryRowMissingError(f"预算录入行 {row_id} 不存在")
    return _row_from_db(updated)


MATCHED_IMPORTED_BUDGET_SOURCE_LABEL = "预算导入-已匹配及导入预算表"


async def load_expense_budget_entry_subject_totals(
    ctx: FrameworkContext,
    *,
    budget_year: int,
    db_path: Path | None = None,
) -> tuple[dict[str, float], str | None]:
    """Load bank-wide budget totals per subject for expense statistics reports."""
    target_db = db_path or common_db_path()
    empty_source = f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（暂无数据）"

    async with aiosqlite.connect(target_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_budget_entry'"
        )
        if not await cur.fetchone():
            return {}, empty_source
        cur = await db.execute(
            """
            SELECT owner_name_raw, owner_matched, budget_subject_mapped, amount, adjustment_amount
            FROM expense_budget_entry
            WHERE budget_year = ?
              AND subject_matched = 1
            ORDER BY id
            """,
            (budget_year,),
        )
        rows = await cur.fetchall()
    if not rows:
        return {}, empty_source

    entries_by_subject: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    for owner_name_raw, owner_matched, subject_mapped, amount, adjustment_amount in rows:
        subject = canonical_subject(text(subject_mapped), ctx)
        if not subject:
            continue
        entries_by_subject[subject].append(
            (
                text(owner_name_raw),
                int(owner_matched or 0),
                expense_budget_adjusted_amount(amount, adjustment_amount),
            )
        )

    if not entries_by_subject:
        return {}, f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（暂无有效已匹配行）"

    totals = {
        subject_name: resolve_expense_budget_subject_total(entries)
        for subject_name, entries in entries_by_subject.items()
        if resolve_expense_budget_subject_total(entries)
    }
    return (
        {key: round(value, 2) for key, value in totals.items()},
        (
            f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（{len(rows)} 行，"
            "全行视图优先取「全行合计」行，否则取已匹配部门明细汇总，"
            "内部单位：元）"
        ),
    )


async def load_expense_budget_entry_by_owner_subject(
    ctx: FrameworkContext,
    *,
    budget_year: int,
    db_path: Path | None = None,
) -> tuple[dict[tuple[str, str], float], str | None]:
    """Load matched-and-imported budget rows for expense execution reports."""
    target_db = db_path or common_db_path()
    empty_source = f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（暂无数据）"

    async with aiosqlite.connect(target_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expense_budget_entry'"
        )
        if not await cur.fetchone():
            return {}, empty_source
        cur = await db.execute(
            """
            SELECT owner_name_mapped, budget_subject_mapped, amount, adjustment_amount
            FROM expense_budget_entry
            WHERE budget_year = ?
              AND owner_matched = 1
              AND subject_matched = 1
            ORDER BY id
            """,
            (budget_year,),
        )
        rows = await cur.fetchall()
    if not rows:
        return {}, empty_source

    totals: dict[tuple[str, str], float] = defaultdict(float)
    for owner_mapped, subject_mapped, amount, adjustment_amount in rows:
        owner = canonical_owner_name(text(owner_mapped), ctx)
        subject = canonical_subject(text(subject_mapped), ctx)
        if not owner or not subject:
            continue
        totals[(owner, subject)] += expense_budget_adjusted_amount(amount, adjustment_amount)

    if not totals:
        return {}, f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（暂无有效已匹配行）"

    return (
        {key: round(value, 2) for key, value in totals.items()},
        (
            f"{MATCHED_IMPORTED_BUDGET_SOURCE_LABEL}（{len(rows)} 行，"
            "主表费用归属部门匹配源表部门、预算科目匹配源表预算科目，"
            "本年预算取源表预算调整后金额，内部单位：元）"
        ),
    )
