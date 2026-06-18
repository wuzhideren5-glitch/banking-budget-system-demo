from __future__ import annotations

from datetime import datetime, timezone
import re
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Awaitable, Callable

from fastapi import HTTPException

from app.core.config import settings
from app.core.database import get_pool
from app.schemas import SystemDatabaseCreateRequest, SystemDatabaseRow, SystemPeriodYearDto


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
    return candidate.name == "common.db"


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


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


def _budget_file_create_time(path: Path, *, fallback_now: Callable[[], str] | None = None) -> str:
    create_time = format_file_ctime(path, fallback_now=fallback_now)
    try:
        with sqlite3.connect(path) as db:
            rows = db.execute(
                "SELECT setting_key, setting_value FROM settings WHERE setting_key = 'create_time'"
            ).fetchall()
            settings_map = {str(row[0]): str(row[1]) for row in rows}
            if settings_map.get("create_time"):
                create_time = settings_map["create_time"]
    except Exception:
        pass
    return create_time


async def list_system_period_years(common_db: Path | str) -> list[SystemPeriodYearDto]:
    if _uses_mysql_path(common_db):
        rows = await get_pool().fetch_all(
            """
            SELECT DISTINCT `year`
            FROM period
            ORDER BY `year`
            """
        )
    else:
        with sqlite3.connect(common_db) as db:
            rows = db.execute(
                """
                SELECT DISTINCT `year`
                FROM period
                ORDER BY `year`
                """
            ).fetchall()

    out: list[SystemPeriodYearDto] = []
    for row in rows:
        match = re.search(r"(\d{4})", str(_row_value(row, "year", 0) or ""))
        if not match:
            continue
        out.append(SystemPeriodYearDto(year=int(match.group(1))))
    return out


async def list_system_databases(common_db: Path | str, data_dir: Path) -> list[SystemDatabaseRow]:
    if _uses_mysql_path(common_db):
        rows = await get_pool().fetch_all(
            """
            SELECT id, data_file_name, `year`, create_time
            FROM `databases`
            ORDER BY `year` DESC, data_file_name
            """
        )
    else:
        with sqlite3.connect(common_db) as db:
            rows = db.execute(
                """
                SELECT id, data_file_name, `year`, create_time
                FROM `databases`
                ORDER BY `year` DESC, data_file_name
                """
            ).fetchall()

    return [
        SystemDatabaseRow(
            id=int(_row_value(row, "id", 0)),
            data_file_name=str(_row_value(row, "data_file_name", 1)),
            year=int(_row_value(row, "year", 2)),
            create_time=str(_row_value(row, "create_time", 3)),
            file_path=str(data_dir / str(_row_value(row, "data_file_name", 1))),
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

    if _uses_mysql_path(common_db):
        db_rows = await get_pool().fetch_all("SELECT id, data_file_name FROM `databases`")
        db_name_to_id = {
            str(_row_value(row, "data_file_name", 1)): int(_row_value(row, "id", 0))
            for row in db_rows
        }
        async with get_pool().acquire() as db:
            try:
                await db.begin()
                async with db.cursor() as cur:
                    for file_name, data_file_id in db_name_to_id.items():
                        if file_name not in seen_names:
                            await cur.execute(
                                "DELETE FROM edit_show_version WHERE data_file_id = %s",
                                (data_file_id,),
                            )
                            await cur.execute("DELETE FROM `databases` WHERE id = %s", (data_file_id,))

                    for budget_file in files:
                        file_name = budget_file.name
                        parsed_year = parse_year_from_budget_filename(file_name)
                        if parsed_year is None:
                            continue
                        create_time = _budget_file_create_time(budget_file, fallback_now=fallback_now)
                        await cur.execute(
                            """
                            INSERT INTO `databases`(data_file_name, year, create_time)
                            VALUES (%s, %s, %s)
                            ON DUPLICATE KEY UPDATE
                              year = VALUES(year),
                              create_time = VALUES(create_time)
                            """,
                            (file_name, int(parsed_year), create_time),
                        )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    else:
        with sqlite3.connect(common_db) as db:
            db.execute("PRAGMA foreign_keys = ON")
            db_rows = db.execute("SELECT id, data_file_name FROM `databases`").fetchall()
            db_name_to_id = {str(row[1]): int(row[0]) for row in db_rows}

            for file_name, data_file_id in db_name_to_id.items():
                if file_name not in seen_names:
                    db.execute("DELETE FROM edit_show_version WHERE data_file_id = ?", (data_file_id,))
                    db.execute("DELETE FROM `databases` WHERE id = ?", (data_file_id,))

            for budget_file in files:
                file_name = budget_file.name
                parsed_year = parse_year_from_budget_filename(file_name)
                if parsed_year is None:
                    continue
                create_time = _budget_file_create_time(budget_file, fallback_now=fallback_now)

                db.execute(
                    """
                    INSERT INTO `databases`(data_file_name, year, create_time)
                    VALUES (?, ?, ?)
                    ON CONFLICT(data_file_name) DO UPDATE SET
                      year = excluded.year,
                      create_time = excluded.create_time
                    """,
                    (file_name, int(parsed_year), create_time),
                )

            db.commit()

    return await list_system_databases(common_db, data_dir)


async def resolve_system_database_file_name(common_db: Path | str, data_file_id: int) -> str:
    if _uses_mysql_path(common_db):
        row = await get_pool().fetch_one(
            "SELECT data_file_name FROM `databases` WHERE id = %s",
            (int(data_file_id),),
        )
    else:
        with sqlite3.connect(common_db) as db:
            row = db.execute(
                "SELECT data_file_name FROM `databases` WHERE id = ?",
                (int(data_file_id),),
            ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"data_file_id={data_file_id} 不存在")
    return str(_row_value(row, "data_file_name", 0))


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
    with sqlite3.connect(db_path) as budget_db:
        budget_db.execute("PRAGMA foreign_keys = ON")
        budget_db.executescript(budget_schema)
        budget_db.execute("DELETE FROM version")
        budget_db.execute(
            "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
            (now, request.first_version_name, 1),
        )
        budget_db.execute("DELETE FROM settings")
        budget_db.executemany(
            "INSERT INTO settings(setting_key, setting_value) VALUES (?, ?)",
            [
                ("year", str(request.year)),
                ("create_user", local_user_name),
                ("create_time", now),
            ],
        )
        budget_db.commit()

    if _uses_mysql_path(common_db):
        await get_pool().execute(
            """
            INSERT INTO `databases`(data_file_name, year, create_time)
            VALUES (%s, %s, %s)
            """,
            (file_name, request.year, now),
        )
        row = await get_pool().fetch_one(
            "SELECT id, data_file_name, year, create_time FROM `databases` WHERE data_file_name = %s",
            (file_name,),
        )
    else:
        with sqlite3.connect(common_db) as common:
            common.execute("PRAGMA foreign_keys = ON")
            common.execute(
                """
                INSERT INTO `databases`(data_file_name, year, create_time)
                VALUES (?, ?, ?)
                """,
                (file_name, request.year, now),
            )
            common.commit()
            row = common.execute(
                "SELECT id, data_file_name, year, create_time FROM `databases` WHERE data_file_name = ?",
                (file_name,),
            ).fetchone()

    if not row:
        raise HTTPException(status_code=500, detail="创建 databases 记录失败")
    return SystemDatabaseRow(
        id=int(_row_value(row, "id", 0)),
        data_file_name=str(_row_value(row, "data_file_name", 1)),
        year=int(_row_value(row, "year", 2)),
        create_time=str(_row_value(row, "create_time", 3)),
        file_path=str(data_dir / str(_row_value(row, "data_file_name", 1))),
    )


async def delete_system_database(common_db: Path | str, data_dir: Path, data_file_id: int) -> dict[str, object]:
    file_name = await resolve_system_database_file_name(common_db, data_file_id)
    db_path = data_dir / file_name
    if db_path.exists():
        db_path.unlink()
    if _uses_mysql_path(common_db):
        async with get_pool().acquire() as common:
            try:
                await common.begin()
                async with common.cursor() as cur:
                    await cur.execute("DELETE FROM edit_show_version WHERE data_file_id = %s", (data_file_id,))
                    await cur.execute("DELETE FROM `databases` WHERE id = %s", (data_file_id,))
                await common.commit()
            except Exception:
                await common.rollback()
                raise
    else:
        with sqlite3.connect(common_db) as common:
            common.execute("PRAGMA foreign_keys = ON")
            common.execute("DELETE FROM edit_show_version WHERE data_file_id = ?", (data_file_id,))
            common.execute("DELETE FROM `databases` WHERE id = ?", (data_file_id,))
            common.commit()

    return {"deleted": True, "data_file_id": data_file_id, "file_name": file_name}
