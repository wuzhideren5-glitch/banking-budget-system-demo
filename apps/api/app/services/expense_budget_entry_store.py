from __future__ import annotations

from collections import defaultdict
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.schemas import ExpenseBudgetEntryBatchRow, ExpenseBudgetEntryRow
from app.services.expense_budget_entry_amounts import (
    expense_budget_adjusted_amount,
    resolve_expense_budget_subject_total,
)
from app.core.config import settings
from app.core.database import get_pool
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


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row.get(key)
    keys = getattr(row, "keys", None)
    if callable(keys) and key in keys():
        return row[key]
    return row[index]


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


async def _table_exists_for_path(db_path: Path, table_name: str) -> bool:
    if _uses_mysql_path(db_path):
        row = await get_pool().fetch_one(
            """
            SELECT 1 AS exists_flag
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return bool(row)
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        return bool(row)


async def _delete_batch_for_path(db_path: Path, batch_id: int) -> int:
    if _uses_mysql_path(db_path):
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT id FROM expense_budget_entry_batch WHERE id = %s", (batch_id,))
                    row = await cur.fetchone()
                    if not row:
                        raise ExpenseBudgetEntryBatchMissingError(f"导入批次 {batch_id} 不存在")
                    await cur.execute("SELECT COUNT(*) FROM expense_budget_entry WHERE batch_id = %s", (batch_id,))
                    count_row = await cur.fetchone()
                    deleted_rows = int(_row_value(count_row, "COUNT(*)", 0) or 0) if count_row else 0
                    await cur.execute("DELETE FROM expense_budget_entry WHERE batch_id = %s", (batch_id,))
                    await cur.execute("DELETE FROM expense_budget_entry_batch WHERE id = %s", (batch_id,))
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return deleted_rows

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        row = db.execute("SELECT id FROM expense_budget_entry_batch WHERE id = ?", (batch_id,)).fetchone()
        if not row:
            raise ExpenseBudgetEntryBatchMissingError(f"导入批次 {batch_id} 不存在")
        deleted_rows = int(db.execute("SELECT COUNT(*) FROM expense_budget_entry WHERE batch_id = ?", (batch_id,)).fetchone()[0])
        db.execute("DELETE FROM expense_budget_entry WHERE batch_id = ?", (batch_id,))
        db.execute("DELETE FROM expense_budget_entry_batch WHERE id = ?", (batch_id,))
        db.commit()
    return deleted_rows


async def _update_row_for_path(
    db_path: Path,
    *,
    row_id: int,
    amount: float | None,
    adjustment_amount: float | None,
) -> ExpenseBudgetEntryRow:
    row = await _fetch_one_for_path(
        db_path,
        f"SELECT {_SELECT_ENTRY_COLUMNS} FROM expense_budget_entry WHERE id = ?",
        (row_id,),
    )
    if not row:
        raise ExpenseBudgetEntryRowMissingError(f"预算录入行 {row_id} 不存在")

    next_amount = float(amount if amount is not None else _row_value(row, "amount", 7) or 0.0)
    next_adjustment = float(
        adjustment_amount if adjustment_amount is not None else _row_value(row, "adjustment_amount", 8) or 0.0
    )
    if _uses_mysql_path(db_path):
        await get_pool().execute(
            """
            UPDATE expense_budget_entry
            SET amount = %s, adjustment_amount = %s
            WHERE id = %s
            """,
            (next_amount, next_adjustment, row_id),
        )
    else:
        with sqlite3.connect(db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute(
                """
                UPDATE expense_budget_entry
                SET amount = ?, adjustment_amount = ?
                WHERE id = ?
                """,
                (next_amount, next_adjustment, row_id),
            )
            db.commit()
    updated = await _fetch_one_for_path(
        db_path,
        f"SELECT {_SELECT_ENTRY_COLUMNS} FROM expense_budget_entry WHERE id = ?",
        (row_id,),
    )
    if not updated:
        raise ExpenseBudgetEntryRowMissingError(f"预算录入行 {row_id} 不存在")
    return _row_from_db(updated)


def _row_from_db(row: Any) -> ExpenseBudgetEntryRow:
    amount = float(_row_value(row, "amount", 7) or 0.0)
    adjustment_amount = float(_row_value(row, "adjustment_amount", 8) or 0.0)
    return ExpenseBudgetEntryRow(
        id=int(_row_value(row, "id", 0)),
        batch_id=int(_row_value(row, "batch_id", 1)),
        budget_year=int(_row_value(row, "budget_year", 2)),
        owner_name_raw=text(_row_value(row, "owner_name_raw", 3)),
        owner_name_mapped=text(_row_value(row, "owner_name_mapped", 4)) or None,
        budget_subject_raw=text(_row_value(row, "budget_subject_raw", 5)),
        budget_subject_mapped=text(_row_value(row, "budget_subject_mapped", 6)) or None,
        amount=amount,
        adjustment_amount=adjustment_amount,
        adjusted_amount=expense_budget_adjusted_amount(amount, adjustment_amount),
        match_status=_match_status(_row_value(row, "owner_matched", 9), _row_value(row, "subject_matched", 10)),
        match_note=text(_row_value(row, "match_note", 11)) or None,
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
    rows = await _fetch_all_for_path(
        db_path,
        """
        SELECT id, budget_year, file_name, import_mode, total_rows, matched_rows, unmatched_rows, created_at, note
        FROM expense_budget_entry_batch
        WHERE budget_year = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (budget_year, limit),
    )
    return [
        ExpenseBudgetEntryBatchRow(
            id=int(_row_value(row, "id", 0)),
            budget_year=int(_row_value(row, "budget_year", 1)),
            file_name=text(_row_value(row, "file_name", 2)),
            import_mode=text(_row_value(row, "import_mode", 3)),
            total_rows=int(_row_value(row, "total_rows", 4) or 0),
            matched_rows=int(_row_value(row, "matched_rows", 5) or 0),
            unmatched_rows=int(_row_value(row, "unmatched_rows", 6) or 0),
            created_at=text(_row_value(row, "created_at", 7)),
            note=text(_row_value(row, "note", 8)) or None,
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
    if batch_id is not None:
        rows = await _fetch_all_for_path(
            db_path,
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
        rows = await _fetch_all_for_path(
            db_path,
            f"""
            SELECT {_SELECT_ENTRY_COLUMNS}
            FROM expense_budget_entry
            WHERE budget_year = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (budget_year, limit),
        )
    return [_row_from_db(row) for row in rows]


async def delete_expense_budget_entry_batch(db_path: Path, *, batch_id: int) -> int:
    return await _delete_batch_for_path(db_path, batch_id)


async def update_expense_budget_entry_row(
    db_path: Path,
    *,
    row_id: int,
    amount: float | None = None,
    adjustment_amount: float | None = None,
) -> ExpenseBudgetEntryRow:
    if amount is None and adjustment_amount is None:
        raise ValueError("请至少提供预算金额或预算调整金额")

    return await _update_row_for_path(
        db_path,
        row_id=row_id,
        amount=amount,
        adjustment_amount=adjustment_amount,
    )


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

    if not await _table_exists_for_path(target_db, "expense_budget_entry"):
        return {}, empty_source
    rows = await _fetch_all_for_path(
        target_db,
        """
        SELECT owner_name_raw, owner_matched, budget_subject_mapped, amount, adjustment_amount
        FROM expense_budget_entry
        WHERE budget_year = ?
          AND subject_matched = 1
        ORDER BY id
        """,
        (budget_year,),
    )
    if not rows:
        return {}, empty_source

    entries_by_subject: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
    for row in rows:
        owner_name_raw = _row_value(row, "owner_name_raw", 0)
        owner_matched = _row_value(row, "owner_matched", 1)
        subject_mapped = _row_value(row, "budget_subject_mapped", 2)
        amount = _row_value(row, "amount", 3)
        adjustment_amount = _row_value(row, "adjustment_amount", 4)
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

    if not await _table_exists_for_path(target_db, "expense_budget_entry"):
        return {}, empty_source
    rows = await _fetch_all_for_path(
        target_db,
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
    if not rows:
        return {}, empty_source

    totals: dict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        owner_mapped = _row_value(row, "owner_name_mapped", 0)
        subject_mapped = _row_value(row, "budget_subject_mapped", 1)
        amount = _row_value(row, "amount", 2)
        adjustment_amount = _row_value(row, "adjustment_amount", 3)
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
