"""Status read model for the expense budget execution workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import aiosqlite

from app.core.db_paths import common_db_path

EXPENSE_EXECUTION_STATUS_TABLES = (
    "expense_framework_budget_department",
    "expense_framework_product_department",
    "expense_framework_subject",
    "expense_actual_detail_raw",
)


async def _read_expense_sync_meta(db_path: Path) -> dict[str, dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cur = await db.execute(
            "SELECT sync_key, source_file, source_mtime, synced_at, row_count, note FROM expense_sync_meta"
        )
        rows = await cur.fetchall()
    return {
        str(row[0]): {
            "source_file": str(row[1]),
            "source_mtime": str(row[2]) if row[2] is not None else None,
            "synced_at": str(row[3]),
            "row_count": int(row[4] or 0),
            "note": str(row[5]) if row[5] is not None else None,
        }
        for row in rows
    }


async def _count_status_tables(db_path: Path) -> dict[str, int]:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        counts: dict[str, int] = {}
        for table_name in EXPENSE_EXECUTION_STATUS_TABLES:
            cur = await db.execute(f"SELECT COUNT(*) FROM {table_name}")
            counts[table_name] = int((await cur.fetchone())[0] or 0)
    return counts


async def build_expense_budget_execution_status(db_path: Path | None = None) -> dict[str, Any]:
    resolved_db_path = db_path or common_db_path()
    meta = await _read_expense_sync_meta(resolved_db_path)
    return {
        "framework_import": meta.get("framework_import"),
        "master_apply": meta.get("master_apply"),
        "counts": await _count_status_tables(resolved_db_path),
    }
