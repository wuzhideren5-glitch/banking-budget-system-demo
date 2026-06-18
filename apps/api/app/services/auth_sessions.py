from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Callable

from app.core.config import settings
from app.core.database import get_pool

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
    if _uses_mysql_path(common_db):
        row = await get_pool().fetch_one(
            """
            SELECT id, user_name, first_login_password, daily_login_password, permission_type, first_login_flag
            FROM users
            WHERE user_name = %s
            """,
            (user_name,),
        )
        if not row:
            raise AuthInvalidCredentials("用户名或密码错误")

        user_id = int(_row_value(row, "id", 0))
        first_login_password = str(_row_value(row, "first_login_password", 2) or "")
        daily_login_password = _row_value(row, "daily_login_password", 3)
        permission_type = int(_row_value(row, "permission_type", 4))
        first_login_flag = int(_row_value(row, "first_login_flag", 5))
        need_change_password = first_login_flag == 1
        if need_change_password:
            if password != first_login_password:
                raise AuthInvalidCredentials("用户名或密码错误")
        elif not verify_daily_password(str(daily_login_password or ""), password):
            raise AuthInvalidCredentials("用户名或密码错误")

        session_id = session_id_factory()
        await get_pool().execute(
            """
            INSERT INTO user_sessions(session_id, user_id, must_change_password, create_time, expire_time, last_seen_time)
            VALUES (%s, %s, %s, %s, %s, %s)
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
        return AuthenticatedLogin(
            session_id=session_id,
            user_name=user_name,
            permission_type=permission_type,
            need_change_password=need_change_password,
        )

    with sqlite3.connect(common_db) as db:
        db.execute("PRAGMA foreign_keys = ON")
        cur = db.execute(
                """
                SELECT id, user_name, first_login_password, daily_login_password, permission_type, first_login_flag
                FROM users
                WHERE user_name = ?
                """,
                (user_name,),
            )
        row = cur.fetchone()
        if not row:
            raise AuthInvalidCredentials("用户名或密码错误")

        user_id = int(_row_value(row, "id", 0))
        first_login_password = str(_row_value(row, "first_login_password", 2) or "")
        daily_login_password = _row_value(row, "daily_login_password", 3)
        permission_type = int(_row_value(row, "permission_type", 4))
        first_login_flag = int(_row_value(row, "first_login_flag", 5))
        need_change_password = first_login_flag == 1
        if need_change_password:
            if password != first_login_password:
                raise AuthInvalidCredentials("用户名或密码错误")
        elif not verify_daily_password(str(daily_login_password or ""), password):
            raise AuthInvalidCredentials("用户名或密码错误")

        session_id = session_id_factory()
        db.execute(
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
        db.commit()

    return AuthenticatedLogin(
        session_id=session_id,
        user_name=user_name,
        permission_type=permission_type,
        need_change_password=need_change_password,
    )


async def delete_auth_session(common_db: Path | str, session_id: str | None) -> None:
    if not session_id:
        return
    if _uses_mysql_path(common_db):
        await get_pool().execute("DELETE FROM user_sessions WHERE session_id = %s", (session_id,))
        return
    with sqlite3.connect(common_db) as db:
        db.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
        db.commit()


async def change_first_login_password(
    *,
    common_db: Path | str,
    user_id: int,
    session_id: str,
    hashed_password: str,
    now: str,
) -> None:
    if _uses_mysql_path(common_db):
        async with get_pool().acquire() as conn:
            try:
                await conn.begin()
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE users
                        SET daily_login_password = %s, first_login_flag = 0, update_time = %s
                        WHERE id = %s
                        """,
                        (hashed_password, now, int(user_id)),
                    )
                    await cur.execute(
                        "UPDATE user_sessions SET must_change_password = 0, last_seen_time = %s WHERE session_id = %s",
                        (now, session_id),
                    )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise
        return

    with sqlite3.connect(common_db) as db:
        db.execute("PRAGMA foreign_keys = ON")
        try:
            db.execute(
                """
                UPDATE users
                SET daily_login_password = ?, first_login_flag = 0, update_time = ?
                WHERE id = ?
                """,
                (hashed_password, now, int(user_id)),
            )
            db.execute(
                "UPDATE user_sessions SET must_change_password = 0, last_seen_time = ? WHERE session_id = ?",
                (now, session_id),
            )
            db.commit()
        except Exception:
            db.rollback()
            raise


async def load_auth_session_context(
    *,
    common_db: Path | str,
    session_id: str | None,
    now: str,
) -> dict[str, object] | None:
    if not session_id:
        return None
    if _uses_mysql_path(common_db):
        row = await get_pool().fetch_one(
            """
            SELECT s.session_id, s.user_id, s.must_change_password, s.expire_time,
                   u.user_name, u.permission_type, u.first_login_flag
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_id = %s
            """,
            (session_id,),
        )
        if not row:
            return None
        expire_time = str(_row_value(row, "expire_time", 3))
        if _parse_iso_utc(expire_time) < _parse_iso_utc(now):
            await get_pool().execute("DELETE FROM user_sessions WHERE session_id = %s", (session_id,))
            return None
        await get_pool().execute(
            "UPDATE user_sessions SET last_seen_time = %s WHERE session_id = %s",
            (now, session_id),
        )
        return {
            "session_id": str(_row_value(row, "session_id", 0)),
            "user_id": int(_row_value(row, "user_id", 1)),
            "must_change_password": int(_row_value(row, "must_change_password", 2)),
            "expire_time": expire_time,
            "user_name": str(_row_value(row, "user_name", 4)),
            "permission_type": int(_row_value(row, "permission_type", 5)),
            "first_login_flag": int(_row_value(row, "first_login_flag", 6)),
        }

    with sqlite3.connect(common_db) as db:
        db.execute("PRAGMA foreign_keys = ON")
        cur = db.execute(
            """
            SELECT s.session_id, s.user_id, s.must_change_password, s.expire_time,
                   u.user_name, u.permission_type, u.first_login_flag
            FROM user_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.session_id = ?
            """,
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        expire_time = str(_row_value(row, "expire_time", 3))
        if _parse_iso_utc(expire_time) < _parse_iso_utc(now):
            db.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
            db.commit()
            return None
        db.execute(
            "UPDATE user_sessions SET last_seen_time = ? WHERE session_id = ?",
            (now, session_id),
        )
        db.commit()
        return {
            "session_id": str(_row_value(row, "session_id", 0)),
            "user_id": int(_row_value(row, "user_id", 1)),
            "must_change_password": int(_row_value(row, "must_change_password", 2)),
            "expire_time": expire_time,
            "user_name": str(_row_value(row, "user_name", 4)),
            "permission_type": int(_row_value(row, "permission_type", 5)),
            "first_login_flag": int(_row_value(row, "first_login_flag", 6)),
        }
