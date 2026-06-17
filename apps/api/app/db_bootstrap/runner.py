"""Startup database registry tasks that are not schema definitions."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync_current_budget_registry(
    common_path: Path,
    budget_path: Path,
    budget_year: int,
) -> None:
    """Ensure the active budget DB is visible in the common DB registry."""
    common_conn = sqlite3.connect(common_path)
    budget_conn = sqlite3.connect(budget_path)
    try:
        now = _iso_now()
        data_file_name = budget_path.name
        common_conn.execute(
            """
            INSERT OR IGNORE INTO databases(data_file_name, year, create_time)
            VALUES (?, ?, ?)
            """,
            (data_file_name, int(budget_year), now),
        )
        cur = common_conn.execute(
            "SELECT id FROM databases WHERE data_file_name = ?",
            (data_file_name,),
        )
        row = cur.fetchone()
        if row is not None:
            data_file_id = int(row[0])
            cur = common_conn.execute(
                "SELECT COUNT(*) FROM edit_show_version WHERE edit_show_sign BETWEEN 1 AND 5"
            )
            show_count = int(cur.fetchone()[0] or 0)
            if show_count == 0:
                cur = budget_conn.execute(
                    "SELECT version_id FROM version ORDER BY version_id DESC LIMIT 1"
                )
                vrow = cur.fetchone()
                if vrow is not None:
                    common_conn.execute(
                        """
                        INSERT INTO edit_show_version(data_file_id, version_id, edit_show_sign)
                        VALUES (?, ?, 1)
                        """,
                        (data_file_id, int(vrow[0])),
                    )
        common_conn.commit()
    finally:
        common_conn.close()
        budget_conn.close()
