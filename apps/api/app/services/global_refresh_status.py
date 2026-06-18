"""Global refresh watermark storage for annual and compare read models."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

from app.core.config import settings
from app.core.database import get_pool
from app.schemas import GlobalRefreshAnnualStatus, GlobalRefreshStatusResponse


BUDGET_GLOBAL_REFRESH_KEY = "global_refresh_time_a"
COMPARE_GLOBAL_REFRESH_KEY = "global_refresh_time_b"


SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS compare_settings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  setting_key VARCHAR(255) NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

SQLITE_SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  setting_key TEXT NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
)
"""


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _uses_mysql_path(path: Path | str) -> bool:
    candidate = Path(path).expanduser().resolve(strict=False)
    data_dir = Path(settings.data_dir).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return True


def _budget_year_from_path(db_path: Path) -> int | None:
    match = re.search(r"budget_(\d{4})\.db$", db_path.name)
    return int(match.group(1)) if match else None


def _is_compare_path(db_path: Path) -> bool:
    return db_path.name == "compare.db"


async def _mysql_table_exists(table_name: str) -> bool:
    value = await get_pool().fetch_val(
        """
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return bool(value)


async def ensure_settings_table(db_path: Path) -> None:
    if _uses_mysql_path(db_path):
        if _is_compare_path(db_path) and not await _mysql_table_exists("compare_settings"):
            await get_pool().execute(SETTINGS_TABLE_SQL)
        return
    with sqlite3.connect(db_path) as db:
        db.execute(SQLITE_SETTINGS_TABLE_SQL)
        db.commit()


async def _get_sqlite_setting_value(db_path: Path, key: str) -> str | None:
    with sqlite3.connect(db_path) as db:
        cur = db.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ? LIMIT 1",
            (key,),
        )
        row = cur.fetchone()
    value = _row_value(row, "setting_value", 0) if row else None
    return str(value) if value is not None else None


async def _set_sqlite_setting_value(db_path: Path, key: str, value: str) -> None:
    with sqlite3.connect(db_path) as db:
        db.execute(SQLITE_SETTINGS_TABLE_SQL)
        db.execute(
            """
            INSERT INTO settings(setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
              setting_value = excluded.setting_value
            """,
            (key, value),
        )
        db.commit()


async def _latest_sqlite_budget_summary_update_time(db_path: Path) -> str | None:
    try:
        with sqlite3.connect(db_path) as db:
            cur = db.execute("SELECT MAX(update_time) FROM budget_summary WHERE update_time IS NOT NULL")
            row = cur.fetchone()
    except Exception:
        return None
    value = _row_value(row, "MAX(update_time)", 0) if row else None
    return str(value) if value else None


async def get_setting_value(db_path: Path, key: str) -> str | None:
    await ensure_settings_table(db_path)
    if not _uses_mysql_path(db_path):
        return await _get_sqlite_setting_value(db_path, key)
    if _is_compare_path(db_path):
        row = await get_pool().fetch_one(
            "SELECT setting_value FROM compare_settings WHERE setting_key = %s LIMIT 1",
            (key,),
        )
    else:
        budget_year = _budget_year_from_path(db_path)
        if budget_year is None:
            raise ValueError(f"Cannot infer budget year from database path: {db_path}")
        row = await get_pool().fetch_one(
            "SELECT setting_value FROM settings WHERE budget_year = %s AND setting_key = %s LIMIT 1",
            (budget_year, key),
        )
    return str(row["setting_value"]) if row and row.get("setting_value") is not None else None


async def set_setting_value(db_path: Path, key: str, value: str) -> None:
    await ensure_settings_table(db_path)
    if not _uses_mysql_path(db_path):
        await _set_sqlite_setting_value(db_path, key, value)
        return
    if _is_compare_path(db_path):
        await get_pool().execute(
            """
            INSERT INTO compare_settings(setting_key, setting_value)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE setting_value = %s
            """,
            (key, value, value),
        )
    else:
        budget_year = _budget_year_from_path(db_path)
        if budget_year is None:
            raise ValueError(f"Cannot infer budget year from database path: {db_path}")
        await get_pool().execute(
            """
            INSERT INTO settings(budget_year, setting_key, setting_value)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE setting_value = %s
            """,
            (budget_year, key, value, value),
        )


async def get_budget_refresh_time(budget_path: Path) -> str | None:
    return await get_setting_value(budget_path, BUDGET_GLOBAL_REFRESH_KEY)


async def set_budget_refresh_time(budget_path: Path, timestamp: str) -> None:
    await set_setting_value(budget_path, BUDGET_GLOBAL_REFRESH_KEY, timestamp)


async def get_compare_refresh_time(compare_path: Path) -> str | None:
    return await get_setting_value(compare_path, COMPARE_GLOBAL_REFRESH_KEY)


async def set_compare_refresh_time(compare_path: Path, timestamp: str) -> None:
    await set_setting_value(compare_path, COMPARE_GLOBAL_REFRESH_KEY, timestamp)


async def last_budget_or_compare_calc_time(
    *,
    budget_path: Path,
    compare_path: Path,
) -> str | None:
    if compare_path.exists():
        compare_refresh_time = await get_compare_refresh_time(compare_path)
        if compare_refresh_time:
            return compare_refresh_time

    budget_year = _budget_year_from_path(budget_path)
    if budget_year is None:
        raise ValueError(f"Cannot infer budget year from database path: {budget_path}")
    if not _uses_mysql_path(budget_path):
        return await _latest_sqlite_budget_summary_update_time(budget_path)
    value = await get_pool().fetch_val(
        "SELECT MAX(update_time) FROM budget_summary WHERE budget_year = %s AND update_time IS NOT NULL",
        (budget_year,),
    )
    if value:
        return str(value)
    return None


async def collect_global_refresh_status(
    *,
    budget_paths: Iterable[Path],
    compare_path: Path,
    parse_year_from_budget_filename: Callable[[str], int | None],
    next_planned_refresh_time: str | None,
) -> GlobalRefreshStatusResponse:
    annual_items: list[GlobalRefreshAnnualStatus] = []
    for budget_path in budget_paths:
        parsed_year = parse_year_from_budget_filename(budget_path.name)
        if parsed_year is None:
            continue
        annual_items.append(
            GlobalRefreshAnnualStatus(
                data_file_name=budget_path.name,
                year=int(parsed_year),
                refresh_time_a=await get_budget_refresh_time(budget_path),
            )
        )
    annual_items.sort(key=lambda item: (-item.year, item.data_file_name))
    return GlobalRefreshStatusResponse(
        annual_items=annual_items,
        compare_refresh_time_b=await get_compare_refresh_time(compare_path),
        next_planned_refresh_time_c=next_planned_refresh_time,
    )
