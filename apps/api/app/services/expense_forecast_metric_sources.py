"""Read metric-bound budget data used by expense forecast rules."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


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
    return candidate.name == "common.db" or (candidate.name.startswith("budget_") and candidate.suffix == ".db")


def _budget_year_from_path(path: Path | str) -> int | None:
    stem = Path(path).stem
    if not stem.startswith("budget_"):
        return None
    suffix = stem.removeprefix("budget_")
    return int(suffix) if suffix.isdigit() else None


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


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
    if not indicator or (not _uses_mysql_path(budget_db_path) and not budget_db_path.exists()):
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
    if _uses_mysql_path(common_db_path):
        sql = """
            SELECT DISTINCT b.data_acct_code
            FROM data_account_metric_binding b
            JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
            WHERE b.is_active = 1
              AND (
                UPPER(b.data_acct_code) = %s
                OR UPPER(b.metric_node_code) = %s
                OR UPPER(COALESCE(n.functional_group_code, '')) = %s
                OR UPPER(COALESCE(n.metric_table_name, '')) = %s
                OR UPPER(COALESCE(n.local_metric_code, '')) = %s
              )
        """
        args: list[Any] = [indicator, indicator, indicator, indicator, indicator]
        if product:
            sql += " AND UPPER(b.scope_code) = %s"
            args.append(product)
        sql += " ORDER BY b.data_acct_code"
        rows = await get_pool().fetch_all(sql, tuple(args))
        return [_text(row["data_acct_code"]) for row in rows if _text(row.get("data_acct_code"))]
    with sqlite3.connect(common_db_path) as cdb:
        cdb.execute("PRAGMA foreign_keys = ON")
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
        args = [indicator, indicator, indicator, indicator, indicator]
        if product:
            sql += " AND UPPER(b.scope_code) = ?"
            args.append(product)
        sql += " ORDER BY b.data_acct_code"
        return [_text(row[0]) for row in cdb.execute(sql, args).fetchall() if _text(row[0])]


async def _latest_budget_version_id(budget_db_path: Path) -> int | None:
    if _uses_mysql_path(budget_db_path):
        budget_year = _budget_year_from_path(budget_db_path)
        if budget_year is None:
            row = await get_pool().fetch_one("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1")
        else:
            row = await get_pool().fetch_one(
                """
                SELECT version_id
                FROM version
                WHERE budget_year = %s
                ORDER BY version_id DESC
                LIMIT 1
                """,
                (budget_year,),
            )
        value = _row_value(row, "version_id", 0) if row else None
        return int(value) if value is not None else None
    with sqlite3.connect(budget_db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        row = db.execute("SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1").fetchone()
        return int(row[0]) if row and row[0] is not None else None


async def _load_period_month_map(*, common_db_path: Path, year: int) -> dict[int, int]:
    if _uses_mysql_path(common_db_path):
        rows = await get_pool().fetch_all(
            """
            SELECT period_id, CAST(REPLACE(month, 'M', '') AS UNSIGNED) AS month
            FROM period
            WHERE year IN (%s, %s)
            """,
            (str(year), f"Y{int(year)}"),
        )
    else:
        with sqlite3.connect(common_db_path) as db:
            db.execute("PRAGMA foreign_keys = ON")
            rows = db.execute(
                """
                SELECT period_id, CAST(REPLACE(month, 'M', '') AS INTEGER) AS month
                FROM period
                WHERE year IN (?, ?)
                """,
                (str(year), f"Y{int(year)}"),
            ).fetchall()
    return {
        int(_row_value(row, "period_id", 0)): int(_row_value(row, "month", 1))
        for row in rows
        if _row_value(row, "period_id", 0) is not None and _row_value(row, "month", 1) is not None
    }


async def _load_budget_data_month_values(
    *,
    budget_db_path: Path,
    version_id: int,
    runtime_refs: list[str],
    period_map: dict[int, int],
    product: str,
) -> dict[int, float]:
    if _uses_mysql_path(budget_db_path):
        return await _load_budget_data_month_values_mysql(
            budget_db_path=budget_db_path,
            version_id=version_id,
            runtime_refs=runtime_refs,
            period_map=period_map,
            product=product,
        )
    return _load_budget_data_month_values_sqlite(
        budget_db_path=budget_db_path,
        version_id=version_id,
        runtime_refs=runtime_refs,
        period_map=period_map,
        product=product,
    )


async def _load_budget_data_month_values_mysql(
    *,
    budget_db_path: Path,
    version_id: int,
    runtime_refs: list[str],
    period_map: dict[int, int],
    product: str,
) -> dict[int, float]:
    placeholders = ",".join("%s" for _ in runtime_refs)
    budget_year = _budget_year_from_path(budget_db_path)
    filters = ["version_id = %s", "budget_actual = 0", f"data_acct_code IN ({placeholders})"]
    args: list[Any] = [version_id, *runtime_refs]
    if budget_year is not None:
        filters.append("budget_year = %s")
        args.append(budget_year)
    if product:
        filters.append("product_code = %s")
        args.append(product)
    rows = await get_pool().fetch_all(
        f"""
        SELECT period_id, SUM(value) AS amount
        FROM budget_data
        WHERE {' AND '.join(filters)}
        GROUP BY period_id
        """,
        tuple(args),
    )
    return _month_values_from_rows(rows, period_map)


def _load_budget_data_month_values_sqlite(
    *,
    budget_db_path: Path,
    version_id: int,
    runtime_refs: list[str],
    period_map: dict[int, int],
    product: str,
) -> dict[int, float]:
    placeholders = ",".join("?" for _ in runtime_refs)
    sql = f"""
        SELECT period_id, SUM(value) AS amount
        FROM budget_data
        WHERE version_id = ? AND budget_actual = 0
          AND data_acct_code IN ({placeholders})
    """
    args: list[Any] = [version_id, *runtime_refs]
    if product:
        sql += " AND product_code = ?"
        args.append(product)
    sql += " GROUP BY period_id"
    with sqlite3.connect(budget_db_path) as bdb:
        bdb.execute("PRAGMA foreign_keys = ON")
        rows = bdb.execute(sql, args).fetchall()
    return _month_values_from_rows(rows, period_map)


def _month_values_from_rows(rows: list[Any], period_map: dict[int, int]) -> dict[int, float]:
    result: dict[int, float] = {}
    for row in rows:
        period_id = _row_value(row, "period_id", 0)
        amount = _row_value(row, "amount", 1)
        month = period_map.get(int(period_id))
        if month:
            result[month] = round(float(amount or 0.0), 2)
    return result
