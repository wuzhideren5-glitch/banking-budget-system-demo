from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from typing import Awaitable, Callable

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.schemas import VersionSnapshotItem, VersionSnapshotResponse


VersionNameResolver = Callable[[str, int], Awaitable[tuple[str, int]]]


def _row_value(row: Any, key: str, index: int) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
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
    return candidate.name == "common.db" or candidate.name == "compare.db" or (
        candidate.name.startswith("budget_") and candidate.suffix == ".db"
    )


def _budget_year_from_file_name(data_file_name: str) -> int | None:
    stem = Path(data_file_name).stem
    if stem.startswith("budget_"):
        suffix = stem.removeprefix("budget_")
        if suffix.isdigit():
            return int(suffix)
    return None


def _sqlite_load_editable_version_context(common_db: Path | str) -> Any:
    with sqlite3.connect(common_db) as conn:
        return conn.execute(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        ).fetchone()


def _sqlite_load_version_name_and_current_month(
    budget_path: Path,
    version_id: int,
) -> Any:
    if not budget_path.exists():
        return None
    with sqlite3.connect(budget_path) as conn:
        return conn.execute(
            """
            SELECT version_name, current_month
            FROM version
            WHERE version_id = ?
            """,
            (int(version_id),),
        ).fetchone()


def _sqlite_load_latest_version(budget_path: Path) -> Any:
    with sqlite3.connect(budget_path) as conn:
        return conn.execute(
            """
            SELECT version_id, version_name, version_date_time
            FROM version
            ORDER BY version_id DESC
            LIMIT 1
            """
        ).fetchone()


def _sqlite_load_snapshot_rows(common_db: Path | str) -> tuple[Any, list[Any]]:
    with sqlite3.connect(common_db) as conn:
        edit_row = conn.execute(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        ).fetchone()
        show_rows = conn.execute(
            """
            SELECT e.edit_show_sign, d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        ).fetchall()
    return edit_row, show_rows


async def load_editable_version_context(common_db: Path | str, data_dir: Path) -> tuple[Path, int, int]:
    if _uses_mysql_path(common_db):
        row = await get_pool().fetch_one(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        )
    else:
        row = await asyncio.to_thread(_sqlite_load_editable_version_context, common_db)
    if not row:
        raise HTTPException(status_code=500, detail="缺少当前可编辑版本配置(edit_show_version=0)")
    data_file_name = str(_row_value(row, "data_file_name", 0))
    year = int(_row_value(row, "year", 1))
    version_id = int(_row_value(row, "version_id", 2))
    return data_dir / data_file_name, year, version_id


async def load_version_name_and_current_month_from_file(
    data_dir: Path,
    data_file_name: str,
    version_id: int,
) -> tuple[str, int]:
    budget_year = _budget_year_from_file_name(data_file_name)
    if budget_year is None:
        return (f"V{version_id}", 1)
    budget_path = data_dir / data_file_name
    if _uses_mysql_path(budget_path):
        row = await get_pool().fetch_one(
            """
            SELECT version_name, current_month
            FROM version
            WHERE budget_year = %s AND version_id = %s
            """,
            (budget_year, int(version_id)),
        )
    else:
        row = await asyncio.to_thread(
            _sqlite_load_version_name_and_current_month,
            budget_path,
            int(version_id),
        )
    version_name = _row_value(row, "version_name", 0)
    if not row or version_name is None:
        return (f"V{version_id}", 1)
    return (str(version_name), int(_row_value(row, "current_month", 1) or 1))


async def load_latest_version_in_path(budget_path: Path) -> tuple[int, str, str]:
    budget_year = _budget_year_from_file_name(budget_path.name)
    if budget_year is None:
        raise HTTPException(status_code=500, detail="无法从年度库文件名解析预算年度")
    if _uses_mysql_path(budget_path):
        row = await get_pool().fetch_one(
            """
            SELECT version_id, version_name, version_date_time
            FROM version
            WHERE budget_year = %s
            ORDER BY version_id DESC
            LIMIT 1
            """,
            (budget_year,),
        )
    else:
        row = await asyncio.to_thread(_sqlite_load_latest_version, budget_path)
    if not row:
        raise HTTPException(status_code=500, detail="年度库缺少 version 记录")
    return (
        int(_row_value(row, "version_id", 0)),
        str(_row_value(row, "version_name", 1)),
        str(_row_value(row, "version_date_time", 2)),
    )


async def build_version_snapshot(
    common_db: Path | str,
    fetch_version_name_and_current_month: VersionNameResolver,
) -> VersionSnapshotResponse:
    if _uses_mysql_path(common_db):
        edit_row = await get_pool().fetch_one(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        )
        show_rows = await get_pool().fetch_all(
            """
            SELECT e.edit_show_sign, d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        )
    else:
        edit_row, show_rows = await asyncio.to_thread(_sqlite_load_snapshot_rows, common_db)

    items: list[VersionSnapshotItem] = []
    if edit_row:
        file_name = str(_row_value(edit_row, "data_file_name", 0))
        year = int(_row_value(edit_row, "year", 1))
        version_id = int(_row_value(edit_row, "version_id", 2))
        version_name, current_month = await fetch_version_name_and_current_month(file_name, version_id)
        items.append(
            VersionSnapshotItem(
                label="可编辑版本",
                budget_year=year,
                version_id=version_id,
                version_name=version_name,
                current_month=current_month,
            )
        )
    for row in show_rows:
        level = int(_row_value(row, "edit_show_sign", 0))
        file_name = str(_row_value(row, "data_file_name", 1))
        year = int(_row_value(row, "year", 2))
        version_id = int(_row_value(row, "version_id", 3))
        version_name, current_month = await fetch_version_name_and_current_month(file_name, version_id)
        items.append(
            VersionSnapshotItem(
                label=f"展示版本第{level}级",
                budget_year=year,
                version_id=version_id,
                version_name=version_name,
                current_month=current_month,
            )
        )
    return VersionSnapshotResponse(items=items)
