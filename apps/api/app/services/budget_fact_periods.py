from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat

from app.budget_window import budget_actual_allowed_for_month
from app.core.config import settings
from app.core.database import get_pool
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


def _uses_mysql_path(path: Path) -> bool:
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


def _period_month_map_from_rows(rows: list[Any]) -> dict[int, int]:
    out: dict[int, int] = {}
    for row in rows:
        period_id_raw = _row_value(row, "period_id", 0)
        month_label_raw = _row_value(row, "month", 1)
        month = budget_fact_month_index(str(month_label_raw or ""))
        if 1 <= month <= 12:
            out[int(period_id_raw)] = month
    return out


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
    return _period_month_map_from_rows(rows)


async def load_budget_fact_period_month_map_from_path(
    common_path: Path,
    *,
    year: int,
) -> dict[int, int]:
    year_label = f"Y{int(year)}"
    if _uses_mysql_path(common_path):
        rows = await get_pool().fetch_all(
            """
            SELECT period_id, month
            FROM period
            WHERE year = %s
            ORDER BY period_id
            """,
            (year_label,),
        )
    else:
        with sqlite3.connect(common_path) as db:
            rows = db.execute(
                """
                SELECT period_id, month
                FROM period
                WHERE year = ?
                ORDER BY period_id
                """,
                (year_label,),
            ).fetchall()

    return _period_month_map_from_rows(rows)


async def load_budget_fact_period_context(
    db: Any,
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
    for row in rows:
        period_id_raw = _row_value(row, "period_id", 0)
        month_label_raw = _row_value(row, "month", 1)
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
