"""Status read model for the expense budget execution workflow."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.core.db_paths import common_db_path

EXPENSE_EXECUTION_STATUS_TABLES = (
    "expense_framework_budget_department",
    "expense_framework_product_department",
    "expense_framework_subject",
    "expense_actual_detail_raw",
)


def _uses_mysql_path(path: Path | str) -> bool:
    candidate = Path(path).expanduser().resolve(strict=False)
    data_dir = Path(settings.data_dir).expanduser().resolve(strict=False)
    try:
        candidate.relative_to(data_dir)
    except ValueError:
        return False
    return True


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _format_meta_rows(rows: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        str(_row_value(row, "sync_key", 0)): {
            "source_file": str(_row_value(row, "source_file", 1)),
            "source_mtime": (
                str(_row_value(row, "source_mtime", 2))
                if _row_value(row, "source_mtime", 2) is not None
                else None
            ),
            "synced_at": str(_row_value(row, "synced_at", 3)),
            "row_count": int(_row_value(row, "row_count", 4) or 0),
            "note": str(_row_value(row, "note", 5)) if _row_value(row, "note", 5) is not None else None,
        }
        for row in rows
    }


async def _read_expense_sync_meta(db_path: Path) -> dict[str, dict[str, Any]]:
    if _uses_mysql_path(db_path):
        rows = await get_pool().fetch_all(
            "SELECT sync_key, source_file, source_mtime, synced_at, row_count, note FROM expense_sync_meta"
        )
        return _format_meta_rows(rows)
    with sqlite3.connect(db_path) as db:
        cur = db.execute("SELECT sync_key, source_file, source_mtime, synced_at, row_count, note FROM expense_sync_meta")
        return _format_meta_rows(cur.fetchall())


async def _count_status_tables(db_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if _uses_mysql_path(db_path):
        for table_name in EXPENSE_EXECUTION_STATUS_TABLES:
            counts[table_name] = int(await get_pool().fetch_val(f"SELECT COUNT(*) FROM {table_name}") or 0)
        return counts
    with sqlite3.connect(db_path) as db:
        for table_name in EXPENSE_EXECUTION_STATUS_TABLES:
            row = db.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
            counts[table_name] = int(row[0] or 0)
        return counts


async def build_expense_budget_execution_status(db_path: Path | None = None) -> dict[str, Any]:
    resolved_db_path = db_path or common_db_path()
    meta = await _read_expense_sync_meta(resolved_db_path)
    return {
        "framework_import": meta.get("framework_import"),
        "master_apply": meta.get("master_apply"),
        "counts": await _count_status_tables(resolved_db_path),
    }
