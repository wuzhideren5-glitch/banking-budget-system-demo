from __future__ import annotations

from typing import Awaitable, Callable

import aiosqlite
from fastapi import APIRouter

from app.db_paths import common_db_path
from app.schemas import VersionSnapshotItem, VersionSnapshotResponse


def build_version_snapshot_router(
    fetch_version_name_and_current_month: Callable[[str, int], Awaitable[tuple[str, int]]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/version-snapshot", response_model=VersionSnapshotResponse)
    async def version_snapshot():
        async with aiosqlite.connect(common_db_path()) as db:
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
            vn, cm = await fetch_version_name_and_current_month(file_name, version_id)
            items.append(
                VersionSnapshotItem(
                    label="可编辑版本",
                    budget_year=year,
                    version_id=version_id,
                    version_name=vn,
                    current_month=cm,
                )
            )
        for row in show_rows:
            level = int(row[0])
            file_name = str(row[1])
            year = int(row[2])
            version_id = int(row[3])
            vn, cm = await fetch_version_name_and_current_month(file_name, version_id)
            items.append(
                VersionSnapshotItem(
                    label=f"展示版本第{level}级",
                    budget_year=year,
                    version_id=version_id,
                    version_name=vn,
                    current_month=cm,
                )
            )
        return VersionSnapshotResponse(items=items)

    return router
