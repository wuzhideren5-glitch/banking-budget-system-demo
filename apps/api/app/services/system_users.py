from __future__ import annotations

from pathlib import Path

import app.core.aiosqlite_compat as aiosqlite
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


_USER_ROW_SQL = """
SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
FROM users
WHERE id = ?
"""


def _row_to_system_user(row: tuple[object, ...]) -> SystemUserRow:
    return SystemUserRow(
        id=int(row[0]),
        user_name=str(row[1]),
        permission_type=int(row[2]),
        first_login_flag=int(row[3]),
        create_time=str(row[4]),
        update_time=str(row[5]) if row[5] is not None else None,
    )


async def _fetch_user_row(db: aiosqlite.Connection, user_id: int) -> SystemUserRow:
    cur = await db.execute(_USER_ROW_SQL, (int(user_id),))
    row = await cur.fetchone()
    if not row:
        raise SystemUserNotFound(f"user_id={user_id} 不存在")
    return _row_to_system_user(row)


async def list_system_users(common_db: Path | str) -> list[SystemUserRow]:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, user_name, permission_type, first_login_flag, create_time, update_time
            FROM users
            ORDER BY id
            """
        )
        rows = await cur.fetchall()
    return [_row_to_system_user(row) for row in rows]


async def create_system_user(
    common_db: Path | str,
    req: SystemUserCreateRequest,
    now: str,
) -> SystemUserRow:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            cur = await db.execute(
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
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise SystemUserDuplicateName("用户名已存在") from exc
        return await _fetch_user_row(db, int(cur.lastrowid))


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

    set_parts.append("update_time = ?")
    args.append(now)
    args.append(int(user_id))

    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            cur = await db.execute(
                f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?",
                tuple(args),
            )
            if cur.rowcount == 0:
                raise SystemUserNotFound(f"user_id={user_id} 不存在")
            await db.commit()
        except aiosqlite.IntegrityError as exc:
            raise SystemUserDuplicateName("用户名已存在") from exc
        return await _fetch_user_row(db, int(user_id))


async def delete_system_user(common_db: Path | str, user_id: int) -> None:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("DELETE FROM users WHERE id = ?", (int(user_id),))
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        await db.commit()


async def system_user_exists(common_db: Path | str, user_id: int) -> bool:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute("SELECT id FROM users WHERE id = ?", (int(user_id),))
        return bool(await cur.fetchone())


async def reset_system_user_first_password(
    common_db: Path | str,
    user_id: int,
    req: SystemUserPasswordResetRequest,
    now: str,
) -> SystemUserRow:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            UPDATE users
            SET first_login_password = ?, daily_login_password = ?, first_login_flag = 1, update_time = ?
            WHERE id = ?
            """,
            (req.first_login_password, None, now, int(user_id)),
        )
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        await db.commit()
        return await _fetch_user_row(db, int(user_id))


async def set_system_user_first_login_flag(
    common_db: Path | str,
    user_id: int,
    req: SystemUserFirstLoginFlagRequest,
    now: str,
) -> SystemUserRow:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            UPDATE users
            SET first_login_flag = ?, update_time = ?
            WHERE id = ?
            """,
            (req.first_login_flag, now, int(user_id)),
        )
        if cur.rowcount == 0:
            raise SystemUserNotFound(f"user_id={user_id} 不存在")
        await db.commit()
        return await _fetch_user_row(db, int(user_id))
