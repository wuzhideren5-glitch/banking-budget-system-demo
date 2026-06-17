"""Read metric-bound budget data used by expense forecast rules."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


async def load_expense_forecast_metric_source_month_map(
    *,
    common_db_path: Path,
    budget_db_path: Path,
    year: int,
    indicator_code: str,
    product_code: str | None = None,
) -> dict[int, float]:
    """Return month -> budget value for runtime metric refs bound to a metric indicator."""
    indicator = _text(indicator_code).upper()
    if not indicator or not budget_db_path.exists():
        return {}

    product = _text(product_code).upper()
    runtime_refs = await _load_bound_runtime_metric_ref_codes(
        common_db_path=common_db_path,
        indicator=indicator,
        product=product,
    )
    if not runtime_refs:
        return {}

    version_id = await _latest_budget_version_id(budget_db_path)
    if version_id is None:
        return {}

    period_map = await _load_period_month_map(common_db_path=common_db_path, year=year)
    if not period_map:
        return {}

    return await _load_budget_data_month_values(
        budget_db_path=budget_db_path,
        version_id=version_id,
        runtime_refs=runtime_refs,
        period_map=period_map,
        product=product,
    )


async def _load_bound_runtime_metric_ref_codes(
    *,
    common_db_path: Path,
    indicator: str,
    product: str,
) -> list[str]:
    async with aiosqlite.connect(common_db_path) as cdb:
        await cdb.execute("PRAGMA foreign_keys = ON")
        sql = """
            SELECT DISTINCT b.data_acct_code
            FROM data_account_metric_binding b
            JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            WHERE b.is_active = 1
              AND (
                UPPER(b.data_acct_code) = ?
                OR UPPER(b.metric_node_code) = ?
                OR UPPER(COALESCE(n.functional_group_code, '')) = ?
                OR UPPER(COALESCE(n.metric_table_name, '')) = ?
                OR UPPER(COALESCE(n.local_metric_code, '')) = ?
              )
        """
        args: list[Any] = [indicator, indicator, indicator, indicator, indicator]
        if product:
            sql += " AND UPPER(b.scope_code) = ?"
            args.append(product)
        sql += " ORDER BY b.data_acct_code"
        cur = await cdb.execute(sql, args)
        return [_text(row[0]) for row in await cur.fetchall() if _text(row[0])]


async def _latest_budget_version_id(budget_db_path: Path) -> int | None:
    async with aiosqlite.connect(budget_db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
        row = await cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


async def _load_period_month_map(*, common_db_path: Path, year: int) -> dict[int, int]:
    async with aiosqlite.connect(common_db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT period_id, CAST(month AS INTEGER)
            FROM period
            WHERE year = ?
            """,
            (str(year),),
        )
        rows = await cur.fetchall()
    return {int(row[0]): int(row[1]) for row in rows if row[0] is not None and row[1] is not None}


async def _load_budget_data_month_values(
    *,
    budget_db_path: Path,
    version_id: int,
    runtime_refs: list[str],
    period_map: dict[int, int],
    product: str,
) -> dict[int, float]:
    placeholders = ",".join("?" for _ in runtime_refs)
    sql = f"""
        SELECT period_id, SUM(value)
        FROM budget_data
        WHERE version_id = ? AND budget_actual = 0
          AND data_acct_code IN ({placeholders})
    """
    args: list[Any] = [version_id, *runtime_refs]
    if product:
        sql += " AND product_code = ?"
        args.append(product)
    sql += " GROUP BY period_id"
    async with aiosqlite.connect(budget_db_path) as bdb:
        await bdb.execute("PRAGMA foreign_keys = ON")
        cur = await bdb.execute(sql, args)
        rows = await cur.fetchall()

    result: dict[int, float] = {}
    for period_id, amount in rows:
        month = period_map.get(int(period_id))
        if month:
            result[month] = round(float(amount or 0.0), 2)
    return result
