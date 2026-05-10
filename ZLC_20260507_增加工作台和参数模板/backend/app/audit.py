from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from app.config import settings
from app.db_paths import common_db_path


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def write_operation_log(
    *,
    action_type: str,
    action_desc: str,
    target_table: str | None,
    affected_rows: int | None = None,
    before_data: Any = None,
    after_data: Any = None,
) -> None:
    path = common_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            """
            INSERT INTO operation_log (
              user_id, action_type, action_desc, target_table,
              affected_rows, before_data, after_data, ip_address, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                settings.local_user_id,
                action_type,
                action_desc,
                target_table,
                affected_rows,
                json.dumps(before_data, ensure_ascii=False) if before_data is not None else None,
                json.dumps(after_data, ensure_ascii=False) if after_data is not None else None,
                None,
                _iso_now(),
            ),
        )
        await db.commit()
