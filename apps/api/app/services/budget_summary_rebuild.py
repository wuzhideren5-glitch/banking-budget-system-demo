"""Budget summary read-model rebuild service."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.db_bootstrap.derived_read_models import ensure_budget_read_model_schema
from app.core.db_paths import budget_db_path, common_db_path
from app.metric_tree_paths import build_metric_path
from app.core.months import parse_month_index
from app.services.org_product_runtime_catalog import org_product_runtime_products_cte


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fixed_levels(path: list[str], max_levels: int) -> list[str | None]:
    levels: list[str | None] = [None] * max_levels
    for idx, token in enumerate(path[:max_levels]):
        levels[idx] = token
    return levels


def _uses_mysql_path(path: Path | str, *, names: set[str] | None = None, budget: bool = False) -> bool:
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
    if budget:
        return re.fullmatch(r"budget_\d{4}\.db", candidate.name) is not None
    return names is not None and candidate.name in names


def _uses_mysql_common_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, names={"common.db"})


def _uses_mysql_budget_path(path: Path | str) -> bool:
    return _uses_mysql_path(path, budget=True)


def _budget_year_from_path(path: Path | str) -> int:
    match = re.fullmatch(r"budget_(\d{4})\.db", Path(path).name)
    return int(match.group(1)) if match else int(settings.budget_year)


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


async def _budget_table_columns_for_path(budget_path: Path, table_name: str) -> set[str]:
    if _uses_mysql_budget_path(budget_path):
        rows = await get_pool().fetch_all(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        return {str(_row_value(row, "COLUMN_NAME", 0)) for row in rows}
    with sqlite3.connect(budget_path) as db:
        return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()}


async def _fetch_one_for_path(path: Path, sql: str, params: tuple[Any, ...] = (), *, budget_year: int | None = None) -> Any | None:
    if _uses_mysql_budget_path(path) or _uses_mysql_common_path(path):
        return await get_pool().fetch_one(sql, params)
    with sqlite3.connect(path) as db:
        return db.execute(sql, params).fetchone()


async def _fetch_all_for_path(path: Path, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    if _uses_mysql_budget_path(path) or _uses_mysql_common_path(path):
        return await get_pool().fetch_all(sql, params)
    with sqlite3.connect(path) as db:
        return db.execute(sql, params).fetchall()


async def _execute_for_path(path: Path, sql: str, params: tuple[Any, ...] = ()) -> int:
    if _uses_mysql_budget_path(path):
        return await get_pool().execute(sql, params)
    with sqlite3.connect(path) as db:
        cur = db.execute(sql, params)
        db.commit()
        return max(0, int(cur.rowcount or 0))


async def _execute_many_for_path(path: Path, sql: str, rows: list[tuple[Any, ...]]) -> int:
    if _uses_mysql_budget_path(path):
        return await get_pool().execute_many(sql, rows)
    with sqlite3.connect(path) as db:
        cur = db.executemany(sql, rows)
        db.commit()
        return max(0, int(cur.rowcount or 0))


def _ensure_sqlite_budget_contract(budget_path: Path) -> None:
    with sqlite3.connect(budget_path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        ensure_budget_version_schema_sync(db)
        ensure_budget_read_model_schema(db)


async def rebuild_budget_summary_for_version(
    version_id: int,
    budget_path: Path | None = None,
) -> int:
    common_path = common_db_path()
    resolved_budget_path = budget_path if budget_path is not None else budget_db_path(settings.budget_year)

    budget_year = _budget_year_from_path(resolved_budget_path)
    mysql_budget = _uses_mysql_budget_path(resolved_budget_path)
    mysql_common = _uses_mysql_common_path(common_path)
    if not mysql_budget:
        _ensure_sqlite_budget_contract(resolved_budget_path)

    vrow = await _fetch_one_for_path(
        resolved_budget_path,
        """
        SELECT version_name, current_month
        FROM version
        WHERE version_id = %s AND budget_year = %s
        """ if mysql_budget else "SELECT version_name, current_month FROM version WHERE version_id = ?",
        (version_id, budget_year) if mysql_budget else (version_id,),
    )
    if not vrow:
        raise HTTPException(status_code=400, detail=f"版本 {version_id} 不存在")
    version_name = str(_row_value(vrow, "version_name", 0))
    current_month = int(_row_value(vrow, "current_month", 1))

    data_account_rows = await _fetch_all_for_path(
        common_path,
        """
        SELECT data_acct_code, data_acct_name, value_type
        FROM data_account
        """
    )
    data_account_map = {
        str(_row_value(r, "data_acct_code", 0)): {
            "name": str(_row_value(r, "data_acct_name", 1)),
            "value_type": str(_row_value(r, "value_type", 2)),
        }
        for r in data_account_rows
    }

    product_rows = await _fetch_all_for_path(
        common_path,
        f"""
        {org_product_runtime_products_cte(dialect="mysql" if mysql_common else "sqlite")}
        SELECT product_code, product_name
        FROM org_product_runtime_products
        WHERE product_code <> '' AND product_name <> ''
        """
    )
    product_name_map = {
        str(_row_value(r, "product_code", 0)): str(_row_value(r, "product_name", 1))
        for r in product_rows
    }

    period_rows = await _fetch_all_for_path(
        common_path,
        "SELECT period_id, year, month, quarter FROM period",
    )
    period_map = {
        int(_row_value(r, "period_id", 0)): {
            "year": str(_row_value(r, "year", 1)),
            "month": str(_row_value(r, "month", 2)),
            "quarter": str(_row_value(r, "quarter", 3)),
        }
        for r in period_rows
    }

    metric_node_rows = await _fetch_all_for_path(
        common_path,
        """
        SELECT node_code, node_name, parent_code, level, sort_order
        FROM data_account_metric_node
        WHERE is_active = 1
        """,
    )
    metric_node_map = {
        str(_row_value(r, "node_code", 0)).strip().upper(): {
            "name": str(_row_value(r, "node_name", 1) or "").strip(),
            "parent": str(_row_value(r, "parent_code", 2)).strip().upper()
            if _row_value(r, "parent_code", 2) is not None
            else None,
            "level": int(_row_value(r, "level", 3) or 0),
            "sort_order": int(_row_value(r, "sort_order", 4) or 0),
        }
        for r in metric_node_rows
    }

    metric_binding_rows = await _fetch_all_for_path(
        common_path,
        """
        SELECT b.metric_node_code, b.data_acct_code, b.scope_code,
               COALESCE(n.sort_order, 999999) AS node_sort_order,
               COALESCE(b.sort_order, 999999) AS binding_sort_order,
               COALESCE(n.level, 999999) AS node_level
        FROM data_account_metric_binding b
        LEFT JOIN data_account_metric_node n ON n.node_code = b.metric_node_code
        WHERE b.is_active = 1
          AND COALESCE(n.is_active, 1) = 1
        ORDER BY node_sort_order, binding_sort_order, node_level,
                 b.metric_node_code, b.scope_code, b.data_acct_code
        """,
    )
    metric_paths_by_data_scope: dict[tuple[str, str], list[list[str]]] = {}
    seen_metric_bindings: set[tuple[str, str, str]] = set()
    for row in metric_binding_rows:
        metric_code = str(_row_value(row, "metric_node_code", 0) or "").strip().upper()
        data_code = str(_row_value(row, "data_acct_code", 1) or "").strip().upper()
        scope_code = str(_row_value(row, "scope_code", 2) or "").strip().upper()
        if not metric_code or not data_code:
            continue
        binding_key = (data_code, scope_code, metric_code)
        if binding_key in seen_metric_bindings:
            continue
        seen_metric_bindings.add(binding_key)
        metric_path = [
            part for part in build_metric_path(metric_code, metric_node_map)
            if not part.startswith("00 ")
        ]
        metric_paths_by_data_scope.setdefault((data_code, scope_code), []).append(metric_path)

    budget_data_cols = await _budget_table_columns_for_path(resolved_budget_path, "budget_data")
    if "value_source" not in budget_data_cols:
        raise RuntimeError("budget_data 缺少当前 value_source 字段，不能按旧事实表重建预算汇总")
    budget_rows = await _fetch_all_for_path(
        resolved_budget_path,
        """
        SELECT data_acct_code, product_code, period_id, budget_actual, value,
               value_source
        FROM budget_data
        WHERE version_id = %s AND budget_year = %s
        """ if mysql_budget else
        """
        SELECT data_acct_code, product_code, period_id, budget_actual, value,
               value_source
        FROM budget_data
        WHERE version_id = ?
        """,
        (version_id, budget_year) if mysql_budget else (version_id,),
    )

    rows_to_insert: list[tuple[Any, ...]] = []
    update_time = _iso_now()
    for row in budget_rows:
        data_code = str(_row_value(row, "data_acct_code", 0))
        row_product_code = str(_row_value(row, "product_code", 1)) if _row_value(row, "product_code", 1) else ""
        period_id = int(_row_value(row, "period_id", 2))
        budget_actual = int(_row_value(row, "budget_actual", 3))
        value = float(_row_value(row, "value", 4) or 0.0)
        value_source = str(_row_value(row, "value_source", 5)).strip().lower()
        acct = data_account_map.get(data_code)
        period = period_map.get(period_id)
        if not acct or not period:
            continue
        month_idx = parse_month_index(period["month"])
        expected_budget_actual = 1 if month_idx < current_month else 0
        if budget_actual != expected_budget_actual:
            continue

        product_code = row_product_code or acct.get("product_code") or ""
        product_name = product_name_map.get(product_code, "") if product_code else ""
        product_code_name = (
            f"{product_code} {product_name}".strip() if product_code else None
        )
        data_code_name = f"{data_code} {acct['name']}".strip()

        metric_scope_candidates = []
        if product_code:
            metric_scope_candidates.append(product_code.strip().upper())
        metric_scope_candidates.append("CORP")
        metric_paths: list[list[str]] = []
        for metric_scope in metric_scope_candidates:
            metric_paths = metric_paths_by_data_scope.get((data_code.strip().upper(), metric_scope), [])
            if metric_paths:
                break
        if not metric_paths:
            metric_paths = [[]]

        dept_levels = _fixed_levels([], 3)
        for metric_path in metric_paths:
            metric_levels = _fixed_levels(metric_path, 5)
            base_row = (
                metric_levels[0],
                metric_levels[1],
                metric_levels[2],
                metric_levels[3],
                metric_levels[4],
                dept_levels[0],
                dept_levels[1],
                dept_levels[2],
                data_code_name,
                product_code_name,
                period["year"],
                period["month"],
                period["quarter"],
                budget_actual,
                version_id,
                version_name,
                value,
                acct["value_type"],
                value_source,
                update_time,
            )
            rows_to_insert.append((budget_year, *base_row) if mysql_budget else base_row)

    await _execute_for_path(
        resolved_budget_path,
        "DELETE FROM budget_summary WHERE budget_year = %s AND version_id = %s"
        if mysql_budget
        else "DELETE FROM budget_summary WHERE version_id = ?",
        (budget_year, version_id) if mysql_budget else (version_id,),
    )
    if rows_to_insert:
        await _execute_many_for_path(
            resolved_budget_path,
            """
            INSERT INTO budget_summary (
              budget_year, metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
              dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
              year, month, quarter, budget_actual, version_id, version_name,
              value, value_type, value_source, update_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """ if mysql_budget else
            """
            INSERT INTO budget_summary (
              metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
              dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
              year, month, quarter, budget_actual, version_id, version_name,
              value, value_type, value_source, update_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_to_insert,
        )
    return len(rows_to_insert)
