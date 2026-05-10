from __future__ import annotations

import re
from typing import Awaitable, Callable

import aiosqlite
from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.db_paths import common_db_path
from app.schemas import SystemDatabaseCreateRequest, SystemDatabaseRow, SystemPeriodYearDto


def build_system_catalog_router(
    *,
    settings: Settings,
    sync_databases_table_with_files: Callable[[], Awaitable[list[SystemDatabaseRow]]],
    budget_schema: str,
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    iso_now: Callable[[], str],
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/system/databases/sync", response_model=list[SystemDatabaseRow])
    async def sync_system_databases():
        return await sync_databases_table_with_files()

    @router.get("/api/system/period-years", response_model=list[SystemPeriodYearDto])
    async def list_system_period_years():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                """
                SELECT DISTINCT year
                FROM period
                ORDER BY year
                """
            )
            rows = await cur.fetchall()
        out: list[SystemPeriodYearDto] = []
        for (year_label,) in rows:
            m = re.search(r"(\d{4})", str(year_label or ""))
            if not m:
                continue
            out.append(SystemPeriodYearDto(year=int(m.group(1))))
        return out

    @router.get("/api/system/databases", response_model=list[SystemDatabaseRow])
    async def list_system_databases():
        async with aiosqlite.connect(common_db_path()) as db:
            await db.execute("PRAGMA foreign_keys = ON")
            cur = await db.execute(
                "SELECT id, data_file_name, year, create_time FROM databases ORDER BY year DESC, data_file_name"
            )
            rows = await cur.fetchall()
        return [
            SystemDatabaseRow(
                id=int(r[0]),
                data_file_name=str(r[1]),
                year=int(r[2]),
                create_time=str(r[3]),
                file_path=str(settings.data_dir / str(r[1])),
            )
            for r in rows
        ]

    @router.post("/api/system/databases", response_model=SystemDatabaseRow)
    async def create_system_database(req: SystemDatabaseCreateRequest):
        data_dir = settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"budget_{req.year}.db"
        db_path = data_dir / file_name
        if db_path.exists():
            raise HTTPException(status_code=400, detail=f"{file_name} 已存在，不能重复创建同年份数据库")

        period_months = await get_year_period_months(req.year)
        if not period_months:
            raise HTTPException(status_code=400, detail=f"period 中不存在年份 Y{req.year}，不能创建该年度库")

        now = iso_now()
        conn = aiosqlite.connect(db_path)
        async with conn as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            await bdb.executescript(budget_schema)
            await bdb.execute("DELETE FROM version")
            cur = await bdb.execute(
                "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
                (now, req.first_version_name, 1),
            )
            _ = cur.lastrowid
            await bdb.execute("DELETE FROM settings")
            await bdb.executemany(
                "INSERT INTO settings(setting_key, setting_value) VALUES (?, ?)",
                [
                    ("year", str(req.year)),
                    ("create_user", settings.local_user_name),
                    ("create_time", now),
                ],
            )
            await bdb.commit()

        async with aiosqlite.connect(common_db_path()) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            await cdb.execute(
                """
                INSERT INTO databases(data_file_name, year, create_time)
                VALUES (?, ?, ?)
                """,
                (file_name, req.year, now),
            )
            await cdb.commit()
            cur = await cdb.execute(
                "SELECT id, data_file_name, year, create_time FROM databases WHERE data_file_name = ?",
                (file_name,),
            )
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail="创建 databases 记录失败")
        return SystemDatabaseRow(
            id=int(row[0]),
            data_file_name=str(row[1]),
            year=int(row[2]),
            create_time=str(row[3]),
            file_path=str(settings.data_dir / str(row[1])),
        )

    @router.delete("/api/system/databases/{data_file_id}")
    async def delete_system_database(data_file_id: int):
        async with aiosqlite.connect(common_db_path()) as cdb:
            await cdb.execute("PRAGMA foreign_keys = ON")
            cur = await cdb.execute(
                "SELECT data_file_name FROM databases WHERE id = ?",
                (data_file_id,),
            )
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"data_file_id={data_file_id} 不存在")
            file_name = str(row[0])
            db_path = settings.data_dir / file_name
            if db_path.exists():
                db_path.unlink()
            await cdb.execute("DELETE FROM edit_show_version WHERE data_file_id = ?", (data_file_id,))
            await cdb.execute("DELETE FROM databases WHERE id = ?", (data_file_id,))
            await cdb.commit()
        return {"deleted": True, "data_file_id": data_file_id, "file_name": file_name}

    return router
