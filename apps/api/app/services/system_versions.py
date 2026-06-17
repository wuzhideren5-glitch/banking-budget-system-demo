from __future__ import annotations

from pathlib import Path
from typing import Awaitable, Callable

import aiosqlite

from app.budget_data_writer import delete_budget_data_for_version
from app.db_bootstrap.budget_version import ensure_budget_version_schema
from app.schemas import (
    ChartVersionItemDto,
    SystemVersionCreateRequest,
    SystemVersionPatchRequest,
    SystemVersionRow,
)


ResolveDataFileName = Callable[[int], Awaitable[str]]
ParseBudgetYear = Callable[[str], int | None]
PeriodMonthProvider = Callable[[int], Awaitable[dict[int, int]]]
MonthWindowPurger = Callable[[aiosqlite.Connection, int, int, dict[int, int]], Awaitable[int]]


class SystemVersionError(Exception):
    """Base error for annual system-version commands."""


class SystemVersionNotFound(SystemVersionError):
    pass


class SystemVersionBadRequest(SystemVersionError):
    pass


class SystemVersionSchemaError(SystemVersionError):
    pass


class SystemVersionOperationFailed(SystemVersionError):
    pass


def _row_to_system_version(row: tuple[object, ...]) -> SystemVersionRow:
    return SystemVersionRow(
        version_id=int(row[0]),
        version_name=str(row[1]),
        version_date_time=str(row[2]),
        current_month=int(row[3]),
    )


async def _resolve_budget_db_path(
    *,
    data_dir: Path,
    data_file_id: int,
    resolve_data_file_name: ResolveDataFileName,
) -> tuple[str, Path]:
    file_name = await resolve_data_file_name(int(data_file_id))
    db_path = data_dir / file_name
    if not db_path.exists():
        raise SystemVersionNotFound(f"数据库文件不存在: {file_name}")
    return file_name, db_path


async def _fetch_version_row(db: aiosqlite.Connection, version_id: int) -> SystemVersionRow:
    cur = await db.execute(
        """
        SELECT version_id, version_name, version_date_time, current_month
        FROM version
        WHERE version_id = ?
        """,
        (int(version_id),),
    )
    row = await cur.fetchone()
    if not row:
        raise SystemVersionNotFound(f"version_id={version_id} 不存在")
    return _row_to_system_version(row)


async def list_system_versions(
    *,
    data_dir: Path,
    data_file_id: int,
    resolve_data_file_name: ResolveDataFileName,
) -> list[SystemVersionRow]:
    _file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            await ensure_budget_version_schema(db)
        except RuntimeError as exc:
            raise SystemVersionSchemaError(str(exc)) from exc
        cur = await db.execute(
            "SELECT version_id, version_name, version_date_time, current_month FROM version ORDER BY version_id DESC"
        )
        rows = await cur.fetchall()
    return [_row_to_system_version(row) for row in rows]


async def load_chart_version_options(
    *,
    common_db: Path | str,
    data_dir: Path,
) -> list[ChartVersionItemDto]:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT e.edit_show_sign, d.id, d.data_file_name, d.year, e.version_id
            FROM edit_show_version e
            JOIN databases d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        )
        selected_rows = await cur.fetchall()
        if not selected_rows:
            cur = await db.execute(
                """
                SELECT 1 AS edit_show_sign, id, data_file_name, year, NULL as version_id
                FROM databases
                ORDER BY year DESC, id DESC
                """
            )
            selected_rows = await cur.fetchall()

    options: list[ChartVersionItemDto] = []
    for db_row in selected_rows:
        show_level = int(db_row[0] or 0)
        data_file_id = int(db_row[1])
        data_file_name = str(db_row[2])
        year = int(db_row[3])
        selected_version_id = int(db_row[4]) if db_row[4] is not None else None
        budget_path = data_dir / data_file_name
        if not budget_path.exists():
            continue
        async with aiosqlite.connect(budget_path) as bdb:
            await bdb.execute("PRAGMA foreign_keys = ON")
            try:
                await ensure_budget_version_schema(bdb)
            except RuntimeError as exc:
                raise SystemVersionSchemaError(str(exc)) from exc
            if selected_version_id is not None:
                cur_versions = await bdb.execute(
                    """
                    SELECT version_id, version_name, current_month
                    FROM version
                    WHERE version_id = ?
                    ORDER BY version_id
                    """,
                    (selected_version_id,),
                )
            else:
                cur_versions = await bdb.execute(
                    """
                    SELECT version_id, version_name, current_month
                    FROM version
                    ORDER BY version_id
                    """
                )
            version_rows = await cur_versions.fetchall()
        for vr in version_rows:
            version_name = str(vr[1])
            if show_level >= 1:
                version_name = f"L{show_level} {version_name}"
            options.append(
                ChartVersionItemDto(
                    show_level=show_level,
                    data_file_id=data_file_id,
                    data_file_name=data_file_name,
                    year=year,
                    version_id=int(vr[0]),
                    version_name=version_name,
                    current_month=int(vr[2]),
                )
            )
    return options


async def try_latest_version_id_in_path(budget_path: Path) -> int | None:
    if not budget_path.exists():
        return None
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='version'"
        )
        if not await cur.fetchone():
            return None
        cur = await db.execute(
            "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1"
        )
        row = await cur.fetchone()
        if not row:
            return None
        return int(row[0])


async def create_system_version(
    *,
    data_dir: Path,
    data_file_id: int,
    request: SystemVersionCreateRequest,
    resolve_data_file_name: ResolveDataFileName,
    parse_year_from_budget_filename: ParseBudgetYear,
    get_year_period_months: PeriodMonthProvider,
    purge_disallowed_budget_data_for_version: MonthWindowPurger,
    now: str,
) -> SystemVersionRow:
    file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    year = parse_year_from_budget_filename(file_name)
    if year is None:
        raise SystemVersionBadRequest("数据库文件名不符合 budget_YYYY.db")
    period_month_map = await get_year_period_months(year)
    if not period_month_map:
        raise SystemVersionBadRequest(f"period 中不存在年份 Y{year}")

    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            await ensure_budget_version_schema(db)
        except RuntimeError as exc:
            raise SystemVersionSchemaError(str(exc)) from exc

        cur = await db.execute(
            "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
            (now, request.version_name, request.current_month),
        )
        new_version_id = int(cur.lastrowid)

        current_month = max(1, min(13, int(request.current_month)))
        year_period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]

        if request.parent_version_id is not None:
            parent_id = int(request.parent_version_id)
            cur = await db.execute("SELECT 1 FROM version WHERE version_id = ?", (parent_id,))
            if not await cur.fetchone():
                raise SystemVersionBadRequest(f"父版本 {parent_id} 不存在")

            insert_shared = """
                INSERT INTO budget_data(
                  data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc, create_time, update_time
                )
                SELECT data_acct_code, product_code, period_id, budget_actual, ?,
                       value, formula_value, manual_value, value_source, need_calc, ?, ?
                FROM budget_data
                WHERE version_id = ?
                """
            if current_month == 13:
                if year_period_ids:
                    placeholders = ",".join(["?"] * len(year_period_ids))
                    await db.execute(
                        insert_shared + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *year_period_ids),
                    )
            elif current_month == 1:
                if year_period_ids:
                    placeholders = ",".join(["?"] * len(year_period_ids))
                    await db.execute(
                        insert_shared + f" AND budget_actual = 0 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *year_period_ids),
                    )
            else:
                actual_period_ids = [
                    pid for pid, month in period_month_map.items() if 1 <= month < current_month
                ]
                budget_period_ids = [
                    pid for pid, month in period_month_map.items() if current_month <= month <= 12
                ]
                if actual_period_ids:
                    placeholders = ",".join(["?"] * len(actual_period_ids))
                    await db.execute(
                        insert_shared + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *actual_period_ids),
                    )
                if budget_period_ids:
                    placeholders = ",".join(["?"] * len(budget_period_ids))
                    await db.execute(
                        insert_shared + f" AND budget_actual = 0 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *budget_period_ids),
                    )

        await purge_disallowed_budget_data_for_version(
            db,
            new_version_id,
            request.current_month,
            period_month_map,
        )
        await db.commit()

        try:
            return await _fetch_version_row(db, new_version_id)
        except SystemVersionNotFound as exc:
            raise SystemVersionOperationFailed("创建版本失败") from exc


async def patch_system_version(
    *,
    data_dir: Path,
    data_file_id: int,
    version_id: int,
    request: SystemVersionPatchRequest,
    resolve_data_file_name: ResolveDataFileName,
) -> SystemVersionRow:
    _file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT 1 FROM version WHERE version_id = ?", (int(version_id),))
        if not await cur.fetchone():
            raise SystemVersionNotFound(f"version_id={version_id} 不存在")
        await db.execute(
            "UPDATE version SET version_name = ? WHERE version_id = ?",
            (request.version_name, int(version_id)),
        )
        await db.commit()
        try:
            await ensure_budget_version_schema(db)
        except RuntimeError as exc:
            raise SystemVersionSchemaError(str(exc)) from exc
        return await _fetch_version_row(db, int(version_id))


async def delete_system_version(
    *,
    common_db: Path | str,
    data_dir: Path,
    data_file_id: int,
    version_id: int,
    resolve_data_file_name: ResolveDataFileName,
) -> dict[str, object]:
    file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT 1 FROM version WHERE version_id = ?", (int(version_id),))
        if not await cur.fetchone():
            raise SystemVersionNotFound(f"version_id={version_id} 不存在")
        budget_data_deleted = await delete_budget_data_for_version(db, version_id=int(version_id))
        await db.execute("DELETE FROM budget_summary WHERE version_id = ?", (int(version_id),))
        await db.execute("DELETE FROM version WHERE version_id = ?", (int(version_id),))
        await db.commit()

    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "DELETE FROM edit_show_version WHERE data_file_id = ? AND version_id = ?",
            (int(data_file_id), int(version_id)),
        )
        await db.commit()

    return {
        "deleted": True,
        "data_file_id": int(data_file_id),
        "version_id": int(version_id),
        "budget_data_deleted": budget_data_deleted,
        "file_name": file_name,
    }
