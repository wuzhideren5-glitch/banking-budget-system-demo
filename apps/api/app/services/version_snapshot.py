from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite
from fastapi import HTTPException

from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.schemas import VersionSnapshotItem, VersionSnapshotResponse


VersionNameResolver = Callable[[str, int], Awaitable[tuple[str, int]]]


async def load_editable_version_context(common_db: Path | str, data_dir: Path) -> tuple[Path, int, int]:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN databases d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="缺少当前可编辑版本配置(edit_show_version=0)")
    data_file_name = str(row[0])
    year = int(row[1])
    version_id = int(row[2])
    return data_dir / data_file_name, year, version_id


async def load_version_name_and_current_month_from_file(
    data_dir: Path,
    data_file_name: str,
    version_id: int,
) -> tuple[str, int]:
    budget_path = data_dir / data_file_name
    if not budget_path.exists():
        return (f"V{version_id}", 1)
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_version_schema(db)
        cur = await db.execute(
            "SELECT version_name, current_month FROM version WHERE version_id = ?",
            (int(version_id),),
        )
        row = await cur.fetchone()
    if not row or row[0] is None:
        return (f"V{version_id}", 1)
    return (str(row[0]), int(row[1] or 1))


async def load_latest_version_in_path(budget_path: Path) -> tuple[int, str, str]:
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT version_id, version_name, version_date_time
            FROM version ORDER BY version_id DESC LIMIT 1
            """
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="年度库缺少 version 记录")
    return int(row[0]), str(row[1]), str(row[2])


async def build_version_snapshot(
    common_db: Path | str,
    fetch_version_name_and_current_month: VersionNameResolver,
) -> VersionSnapshotResponse:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur_edit = await db.execute(
            """
            SELECT d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN databases d ON d.id = e.data_file_id
            WHERE e.edit_show_sign = 0
            LIMIT 1
            """
        )
        edit_row = await cur_edit.fetchone()
        cur_show = await db.execute(
            """
            SELECT e.edit_show_sign, d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN databases d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        )
        show_rows = await cur_show.fetchall()

    items: list[VersionSnapshotItem] = []
    if edit_row:
        file_name = str(edit_row[0])
        year = int(edit_row[1])
        version_id = int(edit_row[2])
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
        level = int(row[0])
        file_name = str(row[1])
        year = int(row[2])
        version_id = int(row[3])
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
