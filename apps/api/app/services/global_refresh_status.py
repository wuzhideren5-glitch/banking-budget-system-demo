"""Global refresh watermark storage for annual and compare read models."""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

import aiosqlite

from app.schemas import GlobalRefreshAnnualStatus, GlobalRefreshStatusResponse


BUDGET_GLOBAL_REFRESH_KEY = "global_refresh_time_a"
COMPARE_GLOBAL_REFRESH_KEY = "global_refresh_time_b"


SETTINGS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  setting_key TEXT NOT NULL UNIQUE,
  setting_value TEXT NOT NULL
)
"""


async def ensure_settings_table(db_path: Path) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(SETTINGS_TABLE_SQL)
        await db.commit()


async def get_setting_value(db_path: Path, key: str) -> str | None:
    await ensure_settings_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT setting_value FROM settings WHERE setting_key = ? LIMIT 1",
            (key,),
        )
        row = await cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


async def set_setting_value(db_path: Path, key: str, value: str) -> None:
    await ensure_settings_table(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO settings(setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET setting_value = excluded.setting_value
            """,
            (key, value),
        )
        await db.commit()


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

    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT MAX(update_time) FROM budget_summary WHERE update_time IS NOT NULL"
        )
        row = await cur.fetchone()
    if row and row[0]:
        return str(row[0])
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
