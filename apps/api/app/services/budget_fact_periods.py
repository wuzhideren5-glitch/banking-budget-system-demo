from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat

import app.core.aiosqlite_compat as aiosqlite
from app.budget_window import budget_actual_allowed_for_month
from app.core.months import parse_month_index
from app.schemas import BudgetFactPeriod


@dataclass(frozen=True)
class BudgetFactPeriodContext:
    periods: list[BudgetFactPeriod]
    period_ids: list[int]
    month_by_period_id: dict[int, int]
    allowed_period_ids: list[int]


def budget_fact_month_index(month_label: str) -> int:
    return parse_month_index(month_label)


def is_budget_fact_month_editable(current_month: int, budget_actual: int, month_index: int) -> bool:
    if budget_actual == 0:
        return month_index >= current_month
    return month_index < current_month


def load_budget_fact_period_month_map_sync(
    db: sqlite3.Connection,
    *,
    year_label: str,
) -> dict[int, int]:
    rows = db.execute(
        """
        SELECT period_id, month
        FROM period
        WHERE year = ?
        ORDER BY period_id
        """,
        (year_label,),
    ).fetchall()
    out: dict[int, int] = {}
    for period_id_raw, month_label_raw in rows:
        month = budget_fact_month_index(str(month_label_raw or ""))
        if 1 <= month <= 12:
            out[int(period_id_raw)] = month
    return out


async def load_budget_fact_period_month_map_from_path(
    common_path: Path,
    *,
    year: int,
) -> dict[int, int]:
    year_label = f"Y{int(year)}"
    async with aiosqlite.connect(common_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT period_id, month
            FROM period
            WHERE year = ?
            ORDER BY period_id
            """,
            (year_label,),
        )
        rows = await cur.fetchall()

    out: dict[int, int] = {}
    for period_id_raw, month_label_raw in rows:
        month = budget_fact_month_index(str(month_label_raw or ""))
        if 1 <= month <= 12:
            out[int(period_id_raw)] = month
    return out


async def load_budget_fact_period_context(
    db: aiosqlite.Connection,
    *,
    year_label: str,
    current_month: int,
    budget_actual: int,
) -> BudgetFactPeriodContext:
    cur = await db.execute(
        """
        SELECT period_id, month
        FROM period
        WHERE year = ?
        ORDER BY period_id
        """,
        (year_label,),
    )
    rows = await cur.fetchall()

    periods: list[BudgetFactPeriod] = []
    month_by_period_id: dict[int, int] = {}
    for period_id_raw, month_label_raw in rows:
        period_id = int(period_id_raw)
        month_label = str(month_label_raw)
        month = budget_fact_month_index(month_label)
        month_by_period_id[period_id] = month
        periods.append(
            BudgetFactPeriod(
                period_id=period_id,
                month_label=month_label,
                month_index=month,
                editable=is_budget_fact_month_editable(current_month, budget_actual, month),
            )
        )

    period_ids = [period.period_id for period in periods]
    allowed_period_ids = [
        period_id
        for period_id in period_ids
        if budget_actual_allowed_for_month(
            budget_actual,
            month_by_period_id.get(period_id, 0),
            current_month,
        )
    ]
    return BudgetFactPeriodContext(
        periods=periods,
        period_ids=period_ids,
        month_by_period_id=month_by_period_id,
        allowed_period_ids=allowed_period_ids,
    )
