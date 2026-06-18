from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Awaitable, Callable

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.schemas import (
    ChartVersionItemDto,
    SystemVersionCreateRequest,
    SystemVersionPatchRequest,
    SystemVersionRow,
)


ResolveDataFileName = Callable[[int], Awaitable[str]]
ParseBudgetYear = Callable[[str], int | None]
PeriodMonthProvider = Callable[[int], Awaitable[dict[int, int]]]
MonthWindowPurger = Callable[[Any, int, int, dict[int, int]], Awaitable[int]]


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


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _row_to_system_version_any(row: Any) -> SystemVersionRow:
    return SystemVersionRow(
        version_id=int(_row_value(row, "version_id", 0)),
        version_name=str(_row_value(row, "version_name", 1)),
        version_date_time=str(_row_value(row, "version_date_time", 2)),
        current_month=int(_row_value(row, "current_month", 3)),
    )


def _dict_to_system_version(row: dict[str, object]) -> SystemVersionRow:
    return SystemVersionRow(
        version_id=int(row["version_id"]),
        version_name=str(row["version_name"]),
        version_date_time=str(row["version_date_time"]),
        current_month=int(row["current_month"]),
    )


def _budget_year_from_file_name(file_name: str) -> int | None:
    stem = Path(file_name).stem
    if not stem.startswith("budget_"):
        return None
    suffix = stem.removeprefix("budget_")
    return int(suffix) if suffix.isdigit() else None


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


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _sqlite_fetch_version_row(conn: sqlite3.Connection, version_id: int) -> SystemVersionRow:
    row = conn.execute(
        """
        SELECT version_id, version_name, version_date_time, current_month
        FROM version
        WHERE version_id = ?
        """,
        (int(version_id),),
    ).fetchone()
    if not row:
        raise SystemVersionNotFound(f"version_id={version_id} 不存在")
    return _row_to_system_version(row)


def _sqlite_list_system_versions(db_path: Path) -> list[SystemVersionRow]:
    with sqlite3.connect(db_path) as conn:
        ensure_budget_version_schema_sync(conn)
        rows = conn.execute(
            """
            SELECT version_id, version_name, version_date_time, current_month
            FROM version
            ORDER BY version_id DESC
            """
        ).fetchall()
    return [_row_to_system_version_any(row) for row in rows]


def _sqlite_load_chart_selection_rows(common_db: Path | str) -> list[Any]:
    with sqlite3.connect(common_db) as conn:
        selected_rows = conn.execute(
            """
            SELECT e.edit_show_sign, d.id, d.data_file_name, d.`year`, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        ).fetchall()
        if selected_rows:
            return selected_rows
        return conn.execute(
            """
            SELECT 1 AS edit_show_sign, id, data_file_name, `year`, NULL as version_id
            FROM `databases`
            ORDER BY `year` DESC, id DESC
            """
        ).fetchall()


def _sqlite_load_budget_version_rows(
    budget_path: Path,
    selected_version_id: int | None,
) -> list[Any]:
    if not budget_path.exists():
        return []
    with sqlite3.connect(budget_path) as conn:
        if selected_version_id is not None:
            return conn.execute(
                """
                SELECT version_id, version_name, current_month
                FROM version
                WHERE version_id = ?
                ORDER BY version_id
                """,
                (selected_version_id,),
            ).fetchall()
        return conn.execute(
            """
            SELECT version_id, version_name, current_month
            FROM version
            ORDER BY version_id
            """
        ).fetchall()


def _sqlite_try_latest_version_id(budget_path: Path) -> int | None:
    if not budget_path.exists():
        return None
    with sqlite3.connect(budget_path) as conn:
        if not _sqlite_table_exists(conn, "version"):
            return None
        row = conn.execute(
            """
            SELECT version_id
            FROM version
            ORDER BY version_id DESC
            LIMIT 1
            """
        ).fetchone()
    return int(_row_value(row, "version_id", 0)) if row else None


def _sqlite_delete_budget_data_for_period_ids(
    conn: sqlite3.Connection,
    *,
    version_id: int,
    budget_actual: int,
    period_ids: list[int],
) -> int:
    if not period_ids:
        return 0
    placeholders = ",".join(["?"] * len(period_ids))
    cur = conn.execute(
        f"""
        DELETE FROM budget_data
        WHERE version_id = ?
          AND budget_actual = ?
          AND period_id IN ({placeholders})
        """,
        (int(version_id), int(budget_actual), *period_ids),
    )
    return max(0, int(cur.rowcount or 0))


def _sqlite_purge_disallowed_budget_data_for_version(
    conn: sqlite3.Connection,
    version_id: int,
    current_month: int,
    period_month_map: dict[int, int],
) -> int:
    if not period_month_map or not _sqlite_table_exists(conn, "budget_data"):
        return 0

    current_month = max(1, min(13, int(current_month)))
    if current_month == 13:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return _sqlite_delete_budget_data_for_period_ids(
            conn,
            version_id=version_id,
            budget_actual=0,
            period_ids=period_ids,
        )
    if current_month == 1:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return _sqlite_delete_budget_data_for_period_ids(
            conn,
            version_id=version_id,
            budget_actual=1,
            period_ids=period_ids,
        )

    deleted = 0
    budget_period_ids = [
        pid for pid, month in period_month_map.items() if 1 <= month < current_month
    ]
    actual_period_ids = [
        pid for pid, month in period_month_map.items() if current_month <= month <= 12
    ]
    deleted += _sqlite_delete_budget_data_for_period_ids(
        conn,
        version_id=version_id,
        budget_actual=0,
        period_ids=budget_period_ids,
    )
    deleted += _sqlite_delete_budget_data_for_period_ids(
        conn,
        version_id=version_id,
        budget_actual=1,
        period_ids=actual_period_ids,
    )
    return deleted


def _sqlite_create_system_version(
    db_path: Path,
    request: SystemVersionCreateRequest,
    period_month_map: dict[int, int],
    now: str,
) -> SystemVersionRow:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_budget_version_schema_sync(conn)

        cur = conn.execute(
            "INSERT INTO version(version_date_time, version_name, current_month) VALUES (?, ?, ?)",
            (now, request.version_name, request.current_month),
        )
        new_version_id = int(cur.lastrowid)

        current_month = max(1, min(13, int(request.current_month)))
        year_period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]

        if request.parent_version_id is not None:
            parent_id = int(request.parent_version_id)
            if not conn.execute("SELECT 1 FROM version WHERE version_id = ?", (parent_id,)).fetchone():
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
                    conn.execute(
                        insert_shared + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *year_period_ids),
                    )
            elif current_month == 1:
                if year_period_ids:
                    placeholders = ",".join(["?"] * len(year_period_ids))
                    conn.execute(
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
                    conn.execute(
                        insert_shared + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *actual_period_ids),
                    )
                if budget_period_ids:
                    placeholders = ",".join(["?"] * len(budget_period_ids))
                    conn.execute(
                        insert_shared + f" AND budget_actual = 0 AND period_id IN ({placeholders})",
                        (new_version_id, now, now, parent_id, *budget_period_ids),
                    )

        _sqlite_purge_disallowed_budget_data_for_version(
            conn,
            new_version_id,
            request.current_month,
            period_month_map,
        )
        try:
            return _sqlite_fetch_version_row(conn, new_version_id)
        except SystemVersionNotFound as exc:
            raise SystemVersionOperationFailed("创建版本失败") from exc


def _sqlite_patch_system_version(
    db_path: Path,
    version_id: int,
    request: SystemVersionPatchRequest,
) -> SystemVersionRow:
    with sqlite3.connect(db_path) as conn:
        ensure_budget_version_schema_sync(conn)
        if not conn.execute(
            "SELECT 1 FROM version WHERE version_id = ?",
            (int(version_id),),
        ).fetchone():
            raise SystemVersionNotFound(f"version_id={version_id} 不存在")
        conn.execute(
            "UPDATE version SET version_name = ? WHERE version_id = ?",
            (request.version_name, int(version_id)),
        )
        return _sqlite_fetch_version_row(conn, int(version_id))


def _sqlite_delete_system_version(
    *,
    common_db: Path | str,
    db_path: Path,
    data_file_id: int,
    version_id: int,
) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        if not conn.execute("SELECT 1 FROM version WHERE version_id = ?", (int(version_id),)).fetchone():
            raise SystemVersionNotFound(f"version_id={version_id} 不存在")
        budget_data_deleted = 0
        if _sqlite_table_exists(conn, "budget_data"):
            cur = conn.execute("DELETE FROM budget_data WHERE version_id = ?", (int(version_id),))
            budget_data_deleted = max(0, int(cur.rowcount or 0))
        conn.execute("DELETE FROM budget_summary WHERE version_id = ?", (int(version_id),))
        conn.execute("DELETE FROM version WHERE version_id = ?", (int(version_id),))

    with sqlite3.connect(common_db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "DELETE FROM edit_show_version WHERE data_file_id = ? AND version_id = ?",
            (int(data_file_id), int(version_id)),
        )
    return budget_data_deleted


async def _mysql_delete_budget_data_for_period_ids(
    cur: Any,
    *,
    budget_year: int,
    version_id: int,
    budget_actual: int,
    period_ids: list[int],
) -> int:
    if not period_ids:
        return 0
    placeholders = ",".join(["%s"] * len(period_ids))
    await cur.execute(
        f"""
        DELETE FROM budget_data
        WHERE budget_year = %s
          AND version_id = %s
          AND budget_actual = %s
          AND period_id IN ({placeholders})
        """,
        (int(budget_year), int(version_id), int(budget_actual), *period_ids),
    )
    return max(0, int(cur.rowcount or 0))


async def _mysql_purge_disallowed_budget_data_for_version(
    cur: Any,
    *,
    budget_year: int,
    version_id: int,
    current_month: int,
    period_month_map: dict[int, int],
) -> int:
    if not period_month_map:
        return 0

    current_month = max(1, min(13, int(current_month)))
    if current_month == 13:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return await _mysql_delete_budget_data_for_period_ids(
            cur,
            budget_year=budget_year,
            version_id=version_id,
            budget_actual=0,
            period_ids=period_ids,
        )
    if current_month == 1:
        period_ids = [pid for pid, month in period_month_map.items() if 1 <= month <= 12]
        return await _mysql_delete_budget_data_for_period_ids(
            cur,
            budget_year=budget_year,
            version_id=version_id,
            budget_actual=1,
            period_ids=period_ids,
        )

    deleted = 0
    budget_period_ids = [
        pid for pid, month in period_month_map.items() if 1 <= month < current_month
    ]
    actual_period_ids = [
        pid for pid, month in period_month_map.items() if current_month <= month <= 12
    ]
    deleted += await _mysql_delete_budget_data_for_period_ids(
        cur,
        budget_year=budget_year,
        version_id=version_id,
        budget_actual=0,
        period_ids=budget_period_ids,
    )
    deleted += await _mysql_delete_budget_data_for_period_ids(
        cur,
        budget_year=budget_year,
        version_id=version_id,
        budget_actual=1,
        period_ids=actual_period_ids,
    )
    return deleted


async def _mysql_create_system_version(
    *,
    budget_year: int,
    request: SystemVersionCreateRequest,
    period_month_map: dict[int, int],
    now: str,
) -> SystemVersionRow:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO version(budget_year, version_date_time, version_name, current_month)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (int(budget_year), now, request.version_name, int(request.current_month)),
                )
                new_version_id = int(cur.lastrowid)

                current_month = max(1, min(13, int(request.current_month)))
                year_period_ids = [
                    pid for pid, month in period_month_map.items() if 1 <= month <= 12
                ]

                if request.parent_version_id is not None:
                    parent_id = int(request.parent_version_id)
                    await cur.execute(
                        """
                        SELECT 1
                        FROM version
                        WHERE budget_year = %s AND version_id = %s
                        """,
                        (int(budget_year), parent_id),
                    )
                    if not await cur.fetchone():
                        raise SystemVersionBadRequest(f"父版本 {parent_id} 不存在")

                    insert_shared = """
                        INSERT INTO budget_data(
                          budget_year, data_acct_code, product_code, period_id, budget_actual, version_id,
                          value, formula_value, manual_value, value_source, need_calc, create_time, update_time
                        )
                        SELECT budget_year, data_acct_code, product_code, period_id, budget_actual, %s,
                               value, formula_value, manual_value, value_source, need_calc, %s, %s
                        FROM budget_data
                        WHERE budget_year = %s
                          AND version_id = %s
                        """
                    if current_month == 13:
                        if year_period_ids:
                            placeholders = ",".join(["%s"] * len(year_period_ids))
                            await cur.execute(
                                insert_shared
                                + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                                (
                                    new_version_id,
                                    now,
                                    now,
                                    int(budget_year),
                                    parent_id,
                                    *year_period_ids,
                                ),
                            )
                    elif current_month == 1:
                        if year_period_ids:
                            placeholders = ",".join(["%s"] * len(year_period_ids))
                            await cur.execute(
                                insert_shared
                                + f" AND budget_actual = 0 AND period_id IN ({placeholders})",
                                (
                                    new_version_id,
                                    now,
                                    now,
                                    int(budget_year),
                                    parent_id,
                                    *year_period_ids,
                                ),
                            )
                    else:
                        actual_period_ids = [
                            pid for pid, month in period_month_map.items() if 1 <= month < current_month
                        ]
                        budget_period_ids = [
                            pid for pid, month in period_month_map.items() if current_month <= month <= 12
                        ]
                        if actual_period_ids:
                            placeholders = ",".join(["%s"] * len(actual_period_ids))
                            await cur.execute(
                                insert_shared
                                + f" AND budget_actual = 1 AND period_id IN ({placeholders})",
                                (
                                    new_version_id,
                                    now,
                                    now,
                                    int(budget_year),
                                    parent_id,
                                    *actual_period_ids,
                                ),
                            )
                        if budget_period_ids:
                            placeholders = ",".join(["%s"] * len(budget_period_ids))
                            await cur.execute(
                                insert_shared
                                + f" AND budget_actual = 0 AND period_id IN ({placeholders})",
                                (
                                    new_version_id,
                                    now,
                                    now,
                                    int(budget_year),
                                    parent_id,
                                    *budget_period_ids,
                                ),
                            )

                await _mysql_purge_disallowed_budget_data_for_version(
                    cur,
                    budget_year=int(budget_year),
                    version_id=new_version_id,
                    current_month=request.current_month,
                    period_month_map=period_month_map,
                )
                await cur.execute(
                    """
                    SELECT version_id, version_name, version_date_time, current_month
                    FROM version
                    WHERE budget_year = %s AND version_id = %s
                    """,
                    (int(budget_year), new_version_id),
                )
                row = await cur.fetchone()
                if not row:
                    raise SystemVersionOperationFailed("创建版本失败")
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return _row_to_system_version_any(row)


async def _mysql_delete_system_version(
    *,
    budget_year: int,
    data_file_id: int,
    version_id: int,
) -> int:
    async with get_pool().acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT 1
                    FROM version
                    WHERE budget_year = %s AND version_id = %s
                    """,
                    (int(budget_year), int(version_id)),
                )
                if not await cur.fetchone():
                    raise SystemVersionNotFound(f"version_id={version_id} 不存在")

                await cur.execute(
                    "DELETE FROM budget_data WHERE budget_year = %s AND version_id = %s",
                    (int(budget_year), int(version_id)),
                )
                budget_data_deleted = max(0, int(cur.rowcount or 0))
                await cur.execute(
                    "DELETE FROM budget_summary WHERE budget_year = %s AND version_id = %s",
                    (int(budget_year), int(version_id)),
                )
                await cur.execute(
                    "DELETE FROM version WHERE budget_year = %s AND version_id = %s",
                    (int(budget_year), int(version_id)),
                )
                await cur.execute(
                    "DELETE FROM edit_show_version WHERE data_file_id = %s AND version_id = %s",
                    (int(data_file_id), int(version_id)),
                )
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
    return budget_data_deleted


async def list_system_versions(
    *,
    data_dir: Path,
    data_file_id: int,
    resolve_data_file_name: ResolveDataFileName,
) -> list[SystemVersionRow]:
    file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    budget_year = _budget_year_from_file_name(file_name)
    if budget_year is None:
        raise SystemVersionBadRequest("数据库文件名不符合 budget_YYYY.db")
    if not _uses_mysql_path(db_path):
        try:
            return await asyncio.to_thread(_sqlite_list_system_versions, db_path)
        except RuntimeError as exc:
            raise SystemVersionSchemaError(str(exc)) from exc
    rows = await get_pool().fetch_all(
        """
        SELECT version_id, version_name, version_date_time, current_month
        FROM version
        WHERE budget_year = %s
        ORDER BY version_id DESC
        """,
        (budget_year,),
    )
    return [_dict_to_system_version(row) for row in rows]


async def load_chart_version_options(
    *,
    common_db: Path | str,
    data_dir: Path,
) -> list[ChartVersionItemDto]:
    if _uses_mysql_path(common_db):
        selected_rows = await get_pool().fetch_all(
            """
            SELECT e.edit_show_sign, d.id, d.data_file_name, d.`year`, e.version_id
            FROM edit_show_version e
            JOIN `databases` d ON d.id = e.data_file_id
            WHERE e.edit_show_sign BETWEEN 1 AND 5
            ORDER BY e.edit_show_sign
            """
        )
        if not selected_rows:
            selected_rows = await get_pool().fetch_all(
                """
                SELECT 1 AS edit_show_sign, id, data_file_name, `year`, NULL as version_id
                FROM `databases`
                ORDER BY `year` DESC, id DESC
                """
            )
    else:
        selected_rows = await asyncio.to_thread(_sqlite_load_chart_selection_rows, common_db)

    options: list[ChartVersionItemDto] = []
    for db_row in selected_rows:
        show_level = int(_row_value(db_row, "edit_show_sign", 0) or 0)
        data_file_id = int(_row_value(db_row, "id", 1))
        data_file_name = str(_row_value(db_row, "data_file_name", 2))
        year = int(_row_value(db_row, "year", 3))
        selected_version_raw = _row_value(db_row, "version_id", 4)
        selected_version_id = int(selected_version_raw) if selected_version_raw is not None else None
        budget_path = data_dir / data_file_name
        if _uses_mysql_path(budget_path):
            if selected_version_id is not None:
                version_rows = await get_pool().fetch_all(
                    """
                    SELECT version_id, version_name, current_month
                    FROM version
                    WHERE budget_year = %s AND version_id = %s
                    ORDER BY version_id
                    """,
                    (year, selected_version_id),
                )
            else:
                version_rows = await get_pool().fetch_all(
                    """
                    SELECT version_id, version_name, current_month
                    FROM version
                    WHERE budget_year = %s
                    ORDER BY version_id
                    """,
                    (year,),
                )
        else:
            version_rows = await asyncio.to_thread(
                _sqlite_load_budget_version_rows,
                budget_path,
                selected_version_id,
            )
        for vr in version_rows:
            version_name = str(_row_value(vr, "version_name", 1))
            if show_level >= 1:
                version_name = f"L{show_level} {version_name}"
            options.append(
                ChartVersionItemDto(
                    show_level=show_level,
                    data_file_id=data_file_id,
                    data_file_name=data_file_name,
                    year=year,
                    version_id=int(_row_value(vr, "version_id", 0)),
                    version_name=version_name,
                    current_month=int(_row_value(vr, "current_month", 2)),
                )
            )
    return options


async def try_latest_version_id_in_path(budget_path: Path) -> int | None:
    budget_year = _budget_year_from_file_name(budget_path.name)
    if _uses_mysql_path(budget_path):
        if budget_year is None:
            return None
        row = await get_pool().fetch_one(
            """
            SELECT version_id
            FROM version
            WHERE budget_year = %s
            ORDER BY version_id DESC
            LIMIT 1
            """,
            (budget_year,),
        )
        return int(row["version_id"]) if row else None
    return await asyncio.to_thread(_sqlite_try_latest_version_id, budget_path)


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

    if _uses_mysql_path(db_path):
        return await _mysql_create_system_version(
            budget_year=year,
            request=request,
            period_month_map=period_month_map,
            now=now,
        )

    try:
        return await asyncio.to_thread(
            _sqlite_create_system_version,
            db_path,
            request,
            period_month_map,
            now,
        )
    except RuntimeError as exc:
        raise SystemVersionSchemaError(str(exc)) from exc


async def patch_system_version(
    *,
    data_dir: Path,
    data_file_id: int,
    version_id: int,
    request: SystemVersionPatchRequest,
    resolve_data_file_name: ResolveDataFileName,
) -> SystemVersionRow:
    file_name, db_path = await _resolve_budget_db_path(
        data_dir=data_dir,
        data_file_id=data_file_id,
        resolve_data_file_name=resolve_data_file_name,
    )
    budget_year = _budget_year_from_file_name(file_name)
    if budget_year is None:
        raise SystemVersionBadRequest("数据库文件名不符合 budget_YYYY.db")
    if not _uses_mysql_path(db_path):
        try:
            return await asyncio.to_thread(
                _sqlite_patch_system_version,
                db_path,
                int(version_id),
                request,
            )
        except RuntimeError as exc:
            raise SystemVersionSchemaError(str(exc)) from exc
    version_row = await get_pool().fetch_one(
        """
        SELECT version_id
        FROM version
        WHERE budget_year = %s AND version_id = %s
        """,
        (budget_year, int(version_id)),
    )
    if not version_row:
        raise SystemVersionNotFound(f"version_id={version_id} 不存在")
    await get_pool().execute(
        """
        UPDATE version
        SET version_name = %s
        WHERE budget_year = %s AND version_id = %s
        """,
        (request.version_name, budget_year, int(version_id)),
    )
    updated = await get_pool().fetch_one(
        """
        SELECT version_id, version_name, version_date_time, current_month
        FROM version
        WHERE budget_year = %s AND version_id = %s
        """,
        (budget_year, int(version_id)),
    )
    if not updated:
        raise SystemVersionOperationFailed("更新版本失败")
    return _dict_to_system_version(updated)


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
    budget_year = _budget_year_from_file_name(file_name)
    if budget_year is None:
        raise SystemVersionBadRequest("数据库文件名不符合 budget_YYYY.db")
    if _uses_mysql_path(db_path):
        budget_data_deleted = await _mysql_delete_system_version(
            budget_year=budget_year,
            data_file_id=int(data_file_id),
            version_id=int(version_id),
        )
    else:
        budget_data_deleted = await asyncio.to_thread(
            _sqlite_delete_system_version,
            common_db=common_db,
            db_path=db_path,
            data_file_id=int(data_file_id),
            version_id=int(version_id),
        )

    return {
        "deleted": True,
        "data_file_id": int(data_file_id),
        "version_id": int(version_id),
        "budget_data_deleted": budget_data_deleted,
        "file_name": file_name,
    }
