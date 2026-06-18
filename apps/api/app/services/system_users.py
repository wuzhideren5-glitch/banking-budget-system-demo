from __future__ import annotations

from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.schemas import (
    SystemUserCreateRequest,
    SystemUserFirstLoginFlagRequest,
    SystemUserPasswordResetRequest,
    SystemUserRow,
    SystemUserUpdateRequest,
)


class SystemUserError(Exception):
    """Base error for current system-user commands."""


class SystemUserNotFound(SystemUserError):
    pass


class SystemUserDuplicateName(SystemUserError):
    pass


class SystemUserNoUpdateFields(SystemUserError):
    pass


def _is_integrity_error(exc: Exception) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    exc_type = f"{type(exc).__module__}.{type(exc).__name__}".lower()
    return "integrityerror" in exc_type or "unique constraint failed" in str(exc).lower()


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


_USER_ROW_SQL = """
SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
FROM users
WHERE id = ?
"""


_USER_ROW_MYSQL_SQL = """
SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
FROM users
WHERE id = %s
"""


def _row_to_system_user(row: Any) -> SystemUserRow:
    return SystemUserRow(
        id=int(_row_value(row, "id", 0)),
        user_name=str(_row_value(row, "user_name", 1)),
        permission_type=int(_row_value(row, "permission_type", 2)),
        first_login_flag=int(_row_value(row, "first_login_flag", 3)),
        create_time=str(_row_value(row, "create_time", 4)),
        update_time=(
            str(_row_value(row, "update_time", 5))
            if _row_value(row, "update_time", 5) is not None
            else None
        ),
    )


def _sqlite_fetch_user_row(db: sqlite3.Connection, user_id: int) -> SystemUserRow:
    row = db.execute(_USER_ROW_SQL, (int(user_id),)).fetchone()
    if not row:
        raise SystemUserNotFound(f"user_id={user_id} 不存在")
    return _row_to_system_user(row)


async def _mysql_fetch_user_row(user_id: int) -> SystemUserRow:
    row = await get_pool().fetch_one(_USER_ROW_MYSQL_SQL, (int(user_id),))
    if not row:
        raise SystemUserNotFound(f"user_id={user_id} 不存在")
    return _row_to_system_user(row)


async def list_system_users(common_db: Path | str) -> list[SystemUserRow]:
    if _uses_mysql_path(common_db):
        rows = await get_pool().fetch_all(
            """
            SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
            FROM users
            ORDER BY id
            """
        )
        return [_row_to_system_user(row) for row in rows]

    with sqlite3.connect(common_db) as db:
        rows = db.execute(
            """
            SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
            FROM users
            ORDER BY id
            """
        ).fetchall()
    return [_row_to_system_user(row) for row in rows]


async def create_system_user(
    common_db: Path | str,
    req: SystemUserCreateRequest,
    now: str,
) -> SystemUserRow:
    if _uses_mysql_path(common_db):
        try:
            async with get_pool().acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO users(
                          user_name, first_login_password, daily_login_password,
                          permission_type, first_login_flag, create_time, update_time
                        ) VALUES (%s, %s, %s, %s, 1, %s, %s)
                        """,
                        (
                            req.user_name.strip(),
                            req.first_login_password,
                            None,
                            req.permission_type,
                            now,
                            now,
                        ),
                    )
                    new_user_id = int(cur.lastrowid)
        except Exception as exc:
            if not _is_integrity_error(exc):
                raise
            raise SystemUserDuplicateName("用户名已存在") from exc
        return await _mysql_fetch_user_row(new_user_id)

    with sqlite3.connect(common_db) as db:
        try:
            cur = db.execute(
                """
                INSERT INTO users(
                  user_name, first_login_password, daily_login_password,
                  permission_type, first_login_flag, create_time, update_time
                ) VALUES (?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    req.user_name.strip(),
                    req.first_login_password,
                    None,
                    req.permission_type,
                    now,
                    now,
                ),
            )
            db.commit()
        except Exception as exc:
            if not _is_integrity_error(exc):
                raise
            raise SystemUserDuplicateName("用户名已存在") from exc
        return _sqlite_fetch_user_row(db, int(cur.lastrowid))


async def update_system_user(
    common_db: Path | str,
    user_id: int,
    req: SystemUserUpdateRequest,
    now: str,
) -> SystemUserRow:
    set_parts: list[str] = []
    args: list[object] = []
    if req.user_name is not None:
        set_parts.append("user_name = ?")
        args.append(req.user_name.strip())
    if req.permission_type is not None:
        set_parts.append("permission_type = ?")
        args.append(req.permission_type)
    if not set_parts:
        raise SystemUserNoUpdateFields("没有可更新字段")

    if _uses_mysql_path(common_db):
        mysql_set_parts = [part.replace("?", "%s") for part in set_parts]
        mysql_args = [*args, now, int(user_id)]
        try:
            affected = await get_pool().execute(
                f"UPDATE users SET {', '.join(mysql_set_parts)}, update_time = %s WHERE id = %s",
                tuple(mysql_args),
            )
            if affected == 0:
                raise SystemUserNotFound(f"user_id={user_id} 不存在")
        except Exception as exc:
            if isinstance(exc, SystemUserNotFound) or not _is_integrity_error(exc):
                raise
            raise SystemUserDuplicateName("用户名已存在") from exc
        return await _mysql_fetch_user_row(int(user_id))

    set_parts.append("update_time = ?")
    args.append(now)
    args.append(int(user_id))

    with sqlite3.connect(common_db) as db:
        try:
            cur = db.execute(
                f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?",
                tuple(args),
            )
            if cur.rowcount == 0:
                raise SystemUserNotFound(f"user_id={user_id} 不存在")
            db.commit()
        except Exception as exc:
            if isinstance(exc, SystemUserNotFound) or not _is_integrity_error(exc):
                raise
            raise SystemUserDuplicateName("用户名已存在") from exc
        return _sqlite_fetch_user_row(db, int(user_id))


async def delete_system_user(common_db: Path | str, user_id: int) -> None:
    if _uses_mysql_path(common_db):
        affected = await get_pool().execute("DELETE FROM users WHERE id = %s", (int(user_id),))
        if affected == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        return

    with sqlite3.connect(common_db) as db:
        cur = db.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        db.commit()


async def system_user_exists(common_db: Path | str, user_id: int) -> bool:
    if _uses_mysql_path(common_db):
        row = await get_pool().fetch_one("SELECT id FROM users WHERE id = %s", (int(user_id),))
        return bool(row)

    with sqlite3.connect(common_db) as db:
        row = db.execute("SELECT id FROM users WHERE id = ?", (int(user_id),)).fetchone()
        return bool(row)


async def reset_system_user_first_password(
    common_db: Path | str,
    user_id: int,
    req: SystemUserPasswordResetRequest,
    now: str,
) -> SystemUserRow:
    if _uses_mysql_path(common_db):
        affected = await get_pool().execute(
            """
            UPDATE users
            SET first_login_password = %s, daily_login_password = %s, first_login_flag = 1, update_time = %s
            WHERE id = %s
            """,
            (req.first_login_password, None, now, int(user_id)),
        )
        if affected == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        return await _mysql_fetch_user_row(int(user_id))

    with sqlite3.connect(common_db) as db:
        cur = db.execute(
            """
            UPDATE users
            SET first_login_password = ?, daily_login_password = ?, first_login_flag = 1, update_time = ?
            WHERE id = ?
            """,
            (req.first_login_password, None, now, int(user_id)),
        )
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        db.commit()
        return _sqlite_fetch_user_row(db, int(user_id))


async def set_system_user_first_login_flag(
    common_db: Path | str,
    user_id: int,
    req: SystemUserFirstLoginFlagRequest,
    now: str,
) -> SystemUserRow:
    if _uses_mysql_path(common_db):
        affected = await get_pool().execute(
            """
            UPDATE users
            SET first_login_flag = %s, update_time = %s
            WHERE id = %s
            """,
            (req.first_login_flag, now, int(user_id)),
        )
        if affected == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        return await _mysql_fetch_user_row(int(user_id))

    with sqlite3.connect(common_db) as db:
        cur = db.execute(
            """
            UPDATE users
            SET first_login_flag = ?, update_time = ?
            WHERE id = ?
            """,
            (req.first_login_flag, now, int(user_id)),
        )
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        db.commit()
        return _sqlite_fetch_user_row(db, int(user_id))
