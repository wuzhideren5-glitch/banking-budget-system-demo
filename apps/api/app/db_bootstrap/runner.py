"""Startup database registry tasks that are not schema definitions."""
from __future__ import annotations

import pymysql
from datetime import datetime, timezone
from typing import Callable


ConnectFactory = Callable[[], pymysql.Connection]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync_current_budget_registry(
    connect: ConnectFactory,
    budget_year: int,
) -> None:
    """Ensure the active budget DB is visible in the registry (single MySQL database)."""
    conn = connect()
    try:
        now = _iso_now()
        data_file_name = f"budget_{budget_year}.db"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT IGNORE INTO databases(data_file_name, year, create_time)
                VALUES (%s, %s, %s)
                """,
                (data_file_name, int(budget_year), now),
            )
            cur.execute(
                "SELECT id FROM databases WHERE data_file_name = %s",
                (data_file_name,),
            )
            row = cur.fetchone()
            if row is not None:
                data_file_id = int(row[0])
                cur.execute(
                    "SELECT COUNT(*) AS cnt FROM edit_show_version WHERE edit_show_sign BETWEEN 1 AND 5"
                )
                show_count = int(cur.fetchone()[0] or 0)
                if show_count == 0:
                    cur.execute(
                        "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1"
                    )
                    vrow = cur.fetchone()
                    if vrow is not None:
                        cur.execute(
                            """
                            INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign)
                            VALUES (%s, %s, 1)
                            """,
                            (data_file_id, int(vrow[0])),
                        )
        conn.commit()
    finally:
        conn.close()
