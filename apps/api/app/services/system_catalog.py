from __future__ import annotations

from datetime import datetime, timezone
import re
from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite
from fastapi import HTTPException

from app.schemas import SystemDatabaseCreateRequest, SystemDatabaseRow, SystemPeriodYearDto


def parse_year_from_budget_filename(name: str) -> int | None:
    match = re.match(r"budget_(\d{4})\.db$", name)
    if not match:
        return None
    return int(match.group(1))


def format_file_ctime(path: Path, *, fallback_now: Callable[[], str] | None = None) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_ctime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        if fallback_now is not None:
            return fallback_now()
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def list_system_period_years(common_db: Path | str) -> list[SystemPeriodYearDto]:
    async with aiosqlite.connect(common_db) as db:
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
        match = re.search(r"(\d{4})", str(year_label or ""))
        if not match:
            continue
        out.append(SystemPeriodYearDto(year=int(match.group(1))))
    return out


async def list_system_databases(common_db: Path | str, data_dir: Path) -> list[SystemDatabaseRow]:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT id, data_file_name, year, create_time FROM databases ORDER BY year DESC, data_file_name"
        )
        rows = await cur.fetchall()

    return [
        SystemDatabaseRow(
            id=int(row[0]),
            data_file_name=str(row[1]),
            year=int(row[2]),
            create_time=str(row[3]),
            file_path=str(data_dir / str(row[1])),
        )
        for row in rows
    ]


async def sync_system_databases_table_with_files(
    common_db: Path | str,
    data_dir: Path,
    *,
    fallback_now: Callable[[], str] | None = None,
) -> list[SystemDatabaseRow]:
    data_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [
            path
            for path in data_dir.glob("budget_*.db")
            if path.is_file() and parse_year_from_budget_filename(path.name) is not None
        ]
    )
    seen_names = {path.name for path in files}

    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT id, data_file_name FROM databases")
        db_rows = await cur.fetchall()
        db_name_to_id = {str(row[1]): int(row[0]) for row in db_rows}

        for file_name, data_file_id in db_name_to_id.items():
            if file_name not in seen_names:
                await db.execute("DELETE FROM edit_show_version WHERE data_file_id = ?", (data_file_id,))
                await db.execute("DELETE FROM databases WHERE id = ?", (data_file_id,))

        for budget_file in files:
            file_name = budget_file.name
            parsed_year = parse_year_from_budget_filename(file_name)
            if parsed_year is None:
                continue
            create_time = format_file_ctime(budget_file, fallback_now=fallback_now)
            try:
                async with aiosqlite.connect(budget_file) as budget_db:
                    cur_settings = await budget_db.execute(
                        "SELECT setting_key, setting_value FROM settings WHERE setting_key = 'create_time'"
                    )
                    settings_rows = await cur_settings.fetchall()
                    settings_map = {str(row[0]): str(row[1]) for row in settings_rows}
                    if settings_map.get("create_time"):
                        create_time = settings_map["create_time"]
            except Exception:
                pass

            await db.execute(
                """
                INSERT INTO databases(data_file_name, year, create_time)
                VALUES (?, ?, ?)
                ON CONFLICT(data_file_name) DO UPDATE SET
                  year = excluded.year,
                  create_time = excluded.create_time
                """,
                (file_name, int(parsed_year), create_time),
            )

        await db.commit()

    return await list_system_databases(common_db, data_dir)


async def resolve_system_database_file_name(common_db: Path | str, data_file_id: int) -> str:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT data_file_name FROM databases WHERE id = ?",
            (int(data_file_id),),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"data_file_id={data_file_id} 不存在")
    return str(row[0])


async def create_system_database(
    *,
    common_db: Path | str,
    data_dir: Path,
    local_user_name: str,
    request: SystemDatabaseCreateRequest,
    budget_schema: str,
    get_year_period_months: Callable[[int], Awaitable[dict[int, int]]],
    iso_now: Callable[[], str],
) -> SystemDatabaseRow:
    data_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"budget_{request.year}.db"
    db_path = data_dir / file_name
    if db_path.exists():
        raise HTTPException(status_code=400, detail=f"{file_name} 已存在，不能重复创建同年份数据库")

    period_months = await get_year_period_months(request.year)
    if not period_months:
        raise HTTPException(status_code=400, detail=f"period 中不存在年份 Y{request.year}，不能创建该年度库")

    now = iso_now()
    async with aiosqlite.connect(db_path) as budget_db:
        await budget_db.execute("PRAGMA foreign_keys = ON")
        await budget_db.executescript(budget_schema)
        await budget_db.execute("DELETE FROM version")
        await budget_db.execute(
            "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
            (now, request.first_version_name, 1),
        )
        await budget_db.execute("DELETE FROM settings")
        await budget_db.executemany(
            "INSERT INTO settings(setting_key, setting_value) VALUES (?, ?)",
            [
                ("year", str(request.year)),
                ("create_user", local_user_name),
                ("create_time", now),
            ],
        )
        await budget_db.commit()

    async with aiosqlite.connect(common_db) as common:
        await common.execute("PRAGMA foreign_keys = ON")
        await common.execute(
            """
            INSERT INTO databases(data_file_name, year, create_time)
            VALUES (?, ?, ?)
            """,
            (file_name, request.year, now),
        )
        await common.commit()
        cur = await common.execute(
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
        file_path=str(data_dir / str(row[1])),
    )


async def delete_system_database(common_db: Path | str, data_dir: Path, data_file_id: int) -> dict[str, object]:
    file_name = await resolve_system_database_file_name(common_db, data_file_id)
    async with aiosqlite.connect(common_db) as common:
        await common.execute("PRAGMA foreign_keys = ON")
        db_path = data_dir / file_name
        if db_path.exists():
            db_path.unlink()
        await common.execute("DELETE FROM edit_show_version WHERE data_file_id = ?", (data_file_id,))
        await common.execute("DELETE FROM databases WHERE id = ?", (data_file_id,))
        await common.commit()

    return {"deleted": True, "data_file_id": data_file_id, "file_name": file_name}
