from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.auth_sessions import (
    AuthInvalidCredentials,
    authenticate_login,
    change_first_login_password,
    delete_auth_session,
    load_auth_session_context,
)


def _seed_auth_db(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_name TEXT NOT NULL UNIQUE,
              first_login_password TEXT NOT NULL,
              daily_login_password TEXT,
              permission_type INTEGER NOT NULL CHECK (permission_type IN (1, 2, 3)),
              first_login_flag INTEGER NOT NULL DEFAULT 1 CHECK (first_login_flag IN (0, 1)),
              create_time TEXT NOT NULL,
              update_time TEXT
            );
            CREATE TABLE user_sessions (
              session_id TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL REFERENCES users(id),
              must_change_password INTEGER NOT NULL DEFAULT 0 CHECK (must_change_password IN (0, 1)),
              create_time TEXT NOT NULL,
              expire_time TEXT NOT NULL,
              last_seen_time TEXT NOT NULL
            );
            INSERT INTO users(
              id, user_name, first_login_password, daily_login_password,
              permission_type, first_login_flag, create_time, update_time
            ) VALUES
              (1, 'first-user', 'first-pass', NULL, 2, 1, '2026-06-01T00:00:00Z', NULL),
              (2, 'daily-user', 'old-first', 'hash:daily-pass', 3, 0, '2026-06-01T00:00:00Z', NULL);
            INSERT INTO user_sessions(session_id, user_id, must_change_password, create_time, expire_time, last_seen_time)
            VALUES
              ('expired', 2, 0, '2026-06-01T00:00:00Z', '2026-06-01T01:00:00Z', '2026-06-01T00:30:00Z');
            """
        )


class AuthSessionsServiceTests(unittest.TestCase):
    def test_login_session_change_password_and_logout_flow(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _seed_auth_db(db_path)
                issued = iter(["session-first", "session-daily"])

                def verify(stored_hash: str | None, raw_password: str) -> bool:
                    return stored_hash == f"hash:{raw_password}"

                first_login = await authenticate_login(
                    common_db=db_path,
                    user_name="first-user",
                    password="first-pass",
                    verify_daily_password=verify,
                    session_id_factory=lambda: next(issued),
                    now="2026-06-03T00:00:00Z",
                    session_ttl_seconds=3600,
                )
                self.assertEqual(first_login.session_id, "session-first")
                self.assertTrue(first_login.need_change_password)
                self.assertEqual(first_login.permission_type, 2)

                first_ctx = await load_auth_session_context(
                    common_db=db_path,
                    session_id="session-first",
                    now="2026-06-03T00:10:00Z",
                )
                self.assertIsNotNone(first_ctx)
                self.assertEqual(first_ctx["must_change_password"], 1)
                with sqlite3.connect(db_path) as conn:
                    self.assertEqual(
                        conn.execute(
                            "SELECT last_seen_time FROM user_sessions WHERE session_id = 'session-first'"
                        ).fetchone()[0],
                        "2026-06-03T00:10:00Z",
                    )

                await change_first_login_password(
                    common_db=db_path,
                    user_id=1,
                    session_id="session-first",
                    hashed_password="hash:new-pass",
                    now="2026-06-03T00:20:00Z",
                )
                changed_ctx = await load_auth_session_context(
                    common_db=db_path,
                    session_id="session-first",
                    now="2026-06-03T00:21:00Z",
                )
                self.assertIsNotNone(changed_ctx)
                self.assertEqual(changed_ctx["must_change_password"], 0)

                with self.assertRaises(AuthInvalidCredentials):
                    await authenticate_login(
                        common_db=db_path,
                        user_name="daily-user",
                        password="wrong",
                        verify_daily_password=verify,
                        session_id_factory=lambda: next(issued),
                        now="2026-06-03T00:30:00Z",
                        session_ttl_seconds=3600,
                    )

                daily_login = await authenticate_login(
                    common_db=db_path,
                    user_name="daily-user",
                    password="daily-pass",
                    verify_daily_password=verify,
                    session_id_factory=lambda: next(issued),
                    now="2026-06-03T00:30:00Z",
                    session_ttl_seconds=3600,
                )
                self.assertFalse(daily_login.need_change_password)

                expired_ctx = await load_auth_session_context(
                    common_db=db_path,
                    session_id="expired",
                    now="2026-06-03T00:00:00Z",
                )
                self.assertIsNone(expired_ctx)

                await delete_auth_session(db_path, "session-daily")
                self.assertIsNone(
                    await load_auth_session_context(
                        common_db=db_path,
                        session_id="session-daily",
                        now="2026-06-03T00:40:00Z",
                    )
                )

                with sqlite3.connect(db_path) as conn:
                    row = conn.execute(
                        "SELECT daily_login_password, first_login_flag FROM users WHERE id = 1"
                    ).fetchone()
                    self.assertEqual(row, ("hash:new-pass", 0))
                    self.assertEqual(
                        conn.execute("SELECT COUNT(*) FROM user_sessions WHERE session_id = 'expired'").fetchone()[0],
                        0,
                    )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
