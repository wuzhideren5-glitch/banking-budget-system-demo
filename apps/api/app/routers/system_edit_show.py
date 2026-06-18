from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.database import get_pool
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
        row = await get_pool().fetch_one(
            "SELECT data_file_name, year FROM `databases` WHERE id = %s",
            (data_file_id,),
        )
        if not row:
            raise HTTPException(status_code=400, detail=f"数据库 data_file_id={data_file_id} 不存在")
        data_file_name = str(row["data_file_name"])
        budget_year = int(row["year"])
        version_row = await get_pool().fetch_one(
            "SELECT 1 FROM version WHERE budget_year = %s AND version_id = %s",
            (budget_year, version_id),
        )
        if not version_row:
            raise HTTPException(
                status_code=400,
                detail=f"{data_file_name} 中不存在 version_id={version_id}",
            )

    @router.get("/api/system/edit-show-version", response_model=EditShowVersionState)
    async def get_edit_show_version():
        rows = await get_pool().fetch_all(
            """
            SELECT edit_show_sign, data_file_id, version_id
            FROM edit_show_version
            ORDER BY edit_show_sign ASC
            """
        )
        edit: EditVersionSelection | None = None
        shows: list[EditShowVersionSelection] = []
        for row in rows:
            s = int(row["edit_show_sign"])
            if s == 0:
                edit = EditVersionSelection(
                    data_file_id=int(row["data_file_id"]),
                    version_id=int(row["version_id"]),
                )
            elif 1 <= s <= 5:
                shows.append(
                    EditShowVersionSelection(
                        level=s,
                        data_file_id=int(row["data_file_id"]),
                        version_id=int(row["version_id"]),
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
        async with get_pool().acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor() as cur:
                    desired_rows: list[tuple[int, int, int]] = []
                    if req.edit is not None:
                        desired_rows.append((0, req.edit.data_file_id, req.edit.version_id))
                    for item in normalized_shows:
                        desired_rows.append((item.level, item.data_file_id, item.version_id))

                    if desired_rows:
                        placeholders = ",".join(["%s"] * len(desired_rows))
                        await cur.execute(
                            f"DELETE FROM edit_show_version WHERE edit_show_sign NOT IN ({placeholders})",
                            tuple(sign for sign, _data_file_id, _version_id in desired_rows),
                        )
                    else:
                        await cur.execute("DELETE FROM edit_show_version")

                    for sign, data_file_id, version_id in desired_rows:
                        await cur.execute(
                            "SELECT id FROM edit_show_version WHERE edit_show_sign = %s LIMIT 1",
                            (sign,),
                        )
                        existing = await cur.fetchone()
                        if existing is None:
                            await cur.execute(
                                """
                                INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign)
                                VALUES (%s, %s, %s)
                                """,
                                (data_file_id, version_id, sign),
                            )
                            continue
                        await cur.execute(
                            """
                            UPDATE edit_show_version
                            SET data_file_id = %s, version_id = %s
                            WHERE edit_show_sign = %s
                            """,
                            (data_file_id, version_id, sign),
                        )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return await get_edit_show_version()

    return router
