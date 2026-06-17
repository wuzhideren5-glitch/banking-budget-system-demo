from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.schemas import (
    SystemUserCreateRequest,
    SystemUserFirstLoginFlagRequest,
    SystemUserPasswordResetRequest,
    SystemUserUpdateRequest,
)
from app.services.system_users import (
    SystemUserDuplicateName,
    SystemUserNoUpdateFields,
    SystemUserNotFound,
    create_system_user,
    delete_system_user,
    list_system_users,
    reset_system_user_first_password,
    set_system_user_first_login_flag,
    system_user_exists,
    update_system_user,
)


def _seed_users_db(db_path: Path) -> None:
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
              update_time TEXT NOT NULL
            );
            INSERT INTO users(
              id, user_name, first_login_password, daily_login_password,
              permission_type, first_login_flag, create_time, update_time
            ) VALUES
              (1, 'admin', 'first-a', 'daily-a', 1, 0, '2026-06-01T00:00:00Z', '2026-06-01T00:00:00Z');
            """
        )


class SystemUsersServiceTests(unittest.TestCase):
    def test_user_commands_keep_user_table_rules_in_one_service(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _seed_users_db(db_path)

                initial = await list_system_users(db_path)
                self.assertEqual([user.user_name for user in initial], ["admin"])

                created = await create_system_user(
                    db_path,
                    SystemUserCreateRequest(
                        user_name=" analyst ",
                        first_login_password="first-b",
                        permission_type=3,
                    ),
                    "2026-06-03T00:00:00Z",
                )
                self.assertEqual(created.user_name, "analyst")
                self.assertEqual(created.first_login_flag, 1)
                self.assertTrue(await system_user_exists(db_path, created.id))

                with self.assertRaises(SystemUserDuplicateName):
                    await create_system_user(
                        db_path,
                        SystemUserCreateRequest(
                            user_name="analyst",
                            first_login_password="another",
                            permission_type=2,
                        ),
                        "2026-06-03T00:01:00Z",
                    )

                updated = await update_system_user(
                    db_path,
                    created.id,
                    SystemUserUpdateRequest(user_name="finance-user", permission_type=2),
                    "2026-06-03T00:02:00Z",
                )
                self.assertEqual(updated.user_name, "finance-user")
                self.assertEqual(updated.permission_type, 2)

                with self.assertRaises(SystemUserNoUpdateFields):
                    await update_system_user(
                        db_path,
                        created.id,
                        SystemUserUpdateRequest(),
                        "2026-06-03T00:03:00Z",
                    )

                reset = await reset_system_user_first_password(
                    db_path,
                    created.id,
                    SystemUserPasswordResetRequest(first_login_password="new-first"),
                    "2026-06-03T00:04:00Z",
                )
                self.assertEqual(reset.first_login_flag, 1)

                flagged = await set_system_user_first_login_flag(
                    db_path,
                    created.id,
                    SystemUserFirstLoginFlagRequest(first_login_flag=0),
                    "2026-06-03T00:05:00Z",
                )
                self.assertEqual(flagged.first_login_flag, 0)

                await delete_system_user(db_path, created.id)
                self.assertFalse(await system_user_exists(db_path, created.id))
                with self.assertRaises(SystemUserNotFound):
                    await delete_system_user(db_path, created.id)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
