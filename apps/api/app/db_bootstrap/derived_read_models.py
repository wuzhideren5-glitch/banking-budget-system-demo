"""Bootstrap current derived read-model table contracts."""
from __future__ import annotations

import sqlite3
from typing import Any


METRIC_LEVEL_COLUMNS = {f"metric_level{idx}" for idx in range(1, 6)}
VALUE_SOURCE_COLUMN = "value_source"
RETIRED_LEVEL_COLUMNS = {
    *(f"report_level{idx}" for idx in range(1, 6)),
    *(f"display_level{idx}" for idx in range(1, 6)),
}

BUDGET_PIVOT_AGGREGATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS budget_pivot_aggregate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  grain TEXT NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  version_id INTEGER NOT NULL,
  version_name TEXT,
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  value_source TEXT NOT NULL DEFAULT 'manual',
  update_time TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_budget_pivot_aggregate_grain
ON budget_pivot_aggregate(grain);
CREATE INDEX IF NOT EXISTS idx_budget_pivot_aggregate_version
ON budget_pivot_aggregate(version_id, grain);
"""

COMPARE_PIVOT_AGGREGATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS compare_pivot_aggregate (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  grain TEXT NOT NULL CHECK (grain IN ('year', 'quarter', 'month')),
  show_level INTEGER NOT NULL CHECK (show_level BETWEEN 1 AND 5),
  data_file_id INTEGER NOT NULL,
  source_year INTEGER NOT NULL,
  source_version_id INTEGER NOT NULL,
  source_version_name TEXT,
  metric_level1 TEXT,
  metric_level2 TEXT,
  metric_level3 TEXT,
  metric_level4 TEXT,
  metric_level5 TEXT,
  dept_level1 TEXT,
  dept_level2 TEXT,
  dept_level3 TEXT,
  data_code_name TEXT NOT NULL,
  product_code_name TEXT,
  year TEXT NOT NULL,
  month TEXT NOT NULL,
  quarter TEXT NOT NULL,
  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
  value REAL NOT NULL DEFAULT 0,
  value_type TEXT NOT NULL,
  value_source TEXT NOT NULL DEFAULT 'manual',
  sync_time TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_compare_pivot_aggregate_grain
ON compare_pivot_aggregate(grain);
CREATE INDEX IF NOT EXISTS idx_compare_pivot_aggregate_level
ON compare_pivot_aggregate(show_level, grain);
"""


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")}


def _column_not_null(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    for row in conn.execute(f"PRAGMA table_info({table_name})"):
        if str(row[1]) == column_name:
            return int(row[3] or 0) == 1
    return False


def _validate_metric_level_columns(table_name: str, columns: set[str]) -> None:
    retired = sorted(RETIRED_LEVEL_COLUMNS & columns)
    if retired:
        raise RuntimeError(
            f"{table_name} 包含已退休的读模型层级字段，必须清理旧表结构："
            + ", ".join(retired)
        )
    missing = sorted(METRIC_LEVEL_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            f"{table_name} 缺少当前 metric_level 读模型字段，系统不再自动迁移："
            + ", ".join(missing)
        )


def _require_metric_level_columns(conn: sqlite3.Connection, table_name: str) -> None:
    if not _table_exists(conn, table_name):
        return
    _validate_metric_level_columns(table_name, _columns(conn, table_name))


def _require_value_source_column(conn: sqlite3.Connection, table_name: str) -> None:
    if not _table_exists(conn, table_name):
        return
    if VALUE_SOURCE_COLUMN not in _columns(conn, table_name):
        raise RuntimeError(
            f"{table_name} 缺少当前 value_source 读模型字段，系统不再自动迁移"
        )
    if not _column_not_null(conn, table_name, VALUE_SOURCE_COLUMN):
        raise RuntimeError(
            f"{table_name} 的 value_source 不是当前 NOT NULL 合同，系统不再自动迁移"
        )


def ensure_budget_read_model_schema(conn: sqlite3.Connection) -> None:
    """Ensure annual budget read models expose the current fields."""
    if _table_exists(conn, "budget_summary"):
        _require_metric_level_columns(conn, "budget_summary")
        _require_value_source_column(conn, "budget_summary")
    conn.executescript(BUDGET_PIVOT_AGGREGATE_SCHEMA)
    _require_metric_level_columns(conn, "budget_pivot_aggregate")
    _require_value_source_column(conn, "budget_pivot_aggregate")


def ensure_compare_read_model_schema(conn: sqlite3.Connection) -> None:
    """Ensure compare read models expose the current fields."""
    if _table_exists(conn, "compare_budget_summary"):
        _require_metric_level_columns(conn, "compare_budget_summary")
        _require_value_source_column(conn, "compare_budget_summary")
    conn.executescript(COMPARE_PIVOT_AGGREGATE_SCHEMA)
    _require_metric_level_columns(conn, "compare_pivot_aggregate")
    _require_value_source_column(conn, "compare_pivot_aggregate")


async def _async_table_exists(conn: Any, table_name: str) -> bool:
    cur = await conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    return await cur.fetchone() is not None


async def _async_columns(conn: Any, table_name: str) -> set[str]:
    cur = await conn.execute(f"PRAGMA table_info({table_name})")
    return {str(row[1]) for row in await cur.fetchall()}


async def _async_column_not_null(conn: Any, table_name: str, column_name: str) -> bool:
    cur = await conn.execute(f"PRAGMA table_info({table_name})")
    for row in await cur.fetchall():
        if str(row[1]) == column_name:
            return int(row[3] or 0) == 1
    return False


async def require_metric_level_columns_async(conn: Any, table_name: str) -> None:
    if not await _async_table_exists(conn, table_name):
        return
    _validate_metric_level_columns(table_name, await _async_columns(conn, table_name))


async def require_value_source_column_async(conn: Any, table_name: str) -> None:
    if not await _async_table_exists(conn, table_name):
        return
    if VALUE_SOURCE_COLUMN not in await _async_columns(conn, table_name):
        raise RuntimeError(
            f"{table_name} 缺少当前 value_source 读模型字段，系统不再自动迁移"
        )
    if not await _async_column_not_null(conn, table_name, VALUE_SOURCE_COLUMN):
        raise RuntimeError(
            f"{table_name} 的 value_source 不是当前 NOT NULL 合同，系统不再自动迁移"
        )


async def ensure_budget_summary_read_model_schema_async(conn: Any) -> None:
    if await _async_table_exists(conn, "budget_summary"):
        await require_metric_level_columns_async(conn, "budget_summary")
        await require_value_source_column_async(conn, "budget_summary")


async def ensure_compare_summary_read_model_schema_async(conn: Any) -> None:
    if await _async_table_exists(conn, "compare_budget_summary"):
        await require_metric_level_columns_async(conn, "compare_budget_summary")
        await require_value_source_column_async(conn, "compare_budget_summary")


async def ensure_budget_pivot_aggregate_schema_async(conn: Any) -> None:
    await conn.executescript(BUDGET_PIVOT_AGGREGATE_SCHEMA)
    await require_metric_level_columns_async(conn, "budget_pivot_aggregate")
    await require_value_source_column_async(conn, "budget_pivot_aggregate")


async def ensure_compare_pivot_aggregate_schema_async(conn: Any) -> None:
    await conn.executescript(COMPARE_PIVOT_AGGREGATE_SCHEMA)
    await require_metric_level_columns_async(conn, "compare_pivot_aggregate")
    await require_value_source_column_async(conn, "compare_pivot_aggregate")


async def ensure_budget_read_model_schema_async(conn: Any) -> None:
    await ensure_budget_summary_read_model_schema_async(conn)
    await ensure_budget_pivot_aggregate_schema_async(conn)


async def ensure_compare_read_model_schema_async(conn: Any) -> None:
    await ensure_compare_summary_read_model_schema_async(conn)
    await ensure_compare_pivot_aggregate_schema_async(conn)
