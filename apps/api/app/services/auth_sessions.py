from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import aiosqlite


VerifyPassword = Callable[[str | None, str], bool]
SessionIdFactory = Callable[[], str]


class AuthSessionError(Exception):
    """Base error for login/session commands."""


class AuthInvalidCredentials(AuthSessionError):
    pass


def _parse_iso_utc(ts: str) -> datetime:
    text = str(ts or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _expire_time(now: str, session_ttl_seconds: int) -> str:
    return datetime.fromtimestamp(
        _parse_iso_utc(now).timestamp() + int(session_ttl_seconds),
        tz=timezone.utc,
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class AuthenticatedLogin:
    session_id: str
    user_name: str
    permission_type: int
    need_change_password: bool


async def authenticate_login(
    *,
    common_db: Path | str,
    user_name: str,
    password: str,
    verify_daily_password: VerifyPassword,
    session_id_factory: SessionIdFactory,
    now: str,
    session_ttl_seconds: int,
) -> AuthenticatedLogin:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT id, user_name, first_login_password, daily_login_password, permission_type, first_login_flag
            FROM users
            WHERE user_name = ?
            """,
            (user_name,),
        )
        row = await cur.fetchone()
        if not row:
            raise AuthInvalidCredentials("用户名或密码错误")

        user_id = int(row[0])
        first_login_password = str(row[2] or "")
        daily_login_password = row[3]
        permission_type = int(row[4])
        first_login_flag = int(row[5])
        need_change_password = first_login_flag == 1
        if need_change_password:
            if password != first_login_password:
                raise AuthInvalidCredentials("用户名或密码错误")
        elif not verify_daily_password(str(daily_login_password or ""), password):
            raise AuthInvalidCredentials("用户名或密码错误")

        session_id = session_id_factory()
        await db.execute(
            """
            INSERT INTO user_sessions(session_id, user_id, must_change_password, create_time, expire_time, last_seen_time)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user_id,
                1 if need_change_password else 0,
                now,
                _expire_time(now, session_ttl_seconds),
                now,
            ),
        )
        await db.commit()

    return AuthenticatedLogin(
        session_id=session_id,
        user_name=user_name,
        permission_type=permission_type,
        need_change_password=need_change_password,
    )


async def delete_auth_session(common_db: Path | str, session_id: str | None) -> None:
    if not session_id:
        return
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
        await db.commit()


async def change_first_login_password(
    *,
    common_db: Path | str,
    user_id: int,
    session_id: str,
    hashed_password: str,
    now: str,
) -> None:
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            UPDATE users
            SET daily_login_password = ?, first_login_flag = 0, update_time = ?
            WHERE id = ?
            """,
            (hashed_password, now, int(user_id)),
        )
        await db.execute(
            "UPDATE user_sessions SET must_change_password = 0, last_seen_time = ? WHERE session_id = ?",
            (now, session_id),
        )
        await db.commit()


async def load_auth_session_context(
    *,
    common_db: Path | str,
    session_id: str | None,
    now: str,
) -> dict[str, object] | None:
    if not session_id:
        return None
    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            """
            SELECT s.session_id, s.user_id, s.must_change_password, s.expire_time,
                   u.user_name, u.permission_type, u.first_login_flag
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_id = ?
            """,
            (session_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        expire_time = str(row[3])
        if _parse_iso_utc(expire_time) < _parse_iso_utc(now):
            await db.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            await db.commit()
            return None
        await db.execute(
            "UPDATE user_sessions SET last_seen_time = ? WHERE session_id = ?",
            (now, session_id),
        )
        await db.commit()
        return {
            "session_id": str(row[0]),
            "user_id": int(row[1]),
            "must_change_password": int(row[2]),
            "expire_time": expire_time,
            "user_name": str(row[4]),
            "permission_type": int(row[5]),
            "first_login_flag": int(row[6]),
        }
