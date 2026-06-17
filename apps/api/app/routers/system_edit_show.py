from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.db_paths import common_db_path
from app.schemas import (
    EditShowVersionSaveRequest,
    EditShowVersionSelection,
    EditShowVersionState,
    EditVersionSelection,
)


def build_system_edit_show_router() -> APIRouter:
    router = APIRouter()

    async def _assert_database_version_exists(data_file_id: int, version_id: int) -> None:
        if data_file_id <= 0 or version_id <= 0:
            raise HTTPException(status_code=400, detail="data_file_id 和 version_id 必须为正整数")
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT data_file_name FROM databases WHERE id = ?",
                (data_file_id,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=400, detail=f"数据库 data_file_id={data_file_id} 不存在")
        data_file_name = str(row[0])
        budget_path = settings.data_dir / data_file_name
        if not budget_path.exists():
            raise HTTPException(status_code=400, detail=f"数据库文件不存在：{data_file_name}")
        async with aiosqlite.connect(budget_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            cur = await bdb.execute(
                "SELECT 1 FROM version WHERE version_id = ?",
                (version_id,),
            )
            if not await cur.fetchone():
                raise HTTPException(
                    status_code=400,
                    detail=f"{data_file_name} 中不存在 version_id={version_id}",
                )

    @router.get("/api/system/edit-show-version", response_model=EditShowVersionState)
    async def get_edit_show_version():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                SELECT edit_show_sign, data_file_id, version_id
                FROM edit_show_version
                ORDER BY edit_show_sign ASC
                """
            )
            rows = await cur.fetchall()
        edit: EditVersionSelection | None = None
        shows: list[EditShowVersionSelection] = []
        for sign, data_file_id, version_id in rows:
            s = int(sign)
            if s == 0:
                edit = EditVersionSelection(data_file_id=int(data_file_id), version_id=int(version_id))
            elif 1 <= s <= 5:
                shows.append(
                    EditShowVersionSelection(
                        level=s,
                        data_file_id=int(data_file_id),
                        version_id=int(version_id),
                    )
                )
        shows.sort(key=lambda x: x.level)
        return EditShowVersionState(edit=edit, shows=shows)

    @router.put("/api/system/edit-show-version", response_model=EditShowVersionState)
    async def save_edit_show_version(req: EditShowVersionSaveRequest):
        seen_levels: set[int] = set()
        normalized_shows: list[EditShowVersionSelection] = []
        for item in sorted(req.shows, key=lambda x: x.level):
            if item.level in seen_levels:
                raise HTTPException(status_code=400, detail=f"show level={item.level} 重复")
            seen_levels.add(item.level)
            normalized_shows.append(item)
        if req.edit is not None:
            await _assert_database_version_exists(req.edit.data_file_id, req.edit.version_id)
        for item in normalized_shows:
            await _assert_database_version_exists(item.data_file_id, item.version_id)
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("DELETE FROM edit_show_version")
            if req.edit is not None:
                await db.execute(
                    "INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign) VALUES (?, ?, 0)",
                    (req.edit.data_file_id, req.edit.version_id),
                )
            for item in normalized_shows:
                await db.execute(
                    "INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign) VALUES (?, ?, ?)",
                    (item.data_file_id, item.version_id, item.level),
                )
            await db.commit()
        return await get_edit_show_version()

    return router
