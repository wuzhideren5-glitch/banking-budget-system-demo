"""Schema readiness adapter for expense actual import tables."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.database import get_pool
from app.db_bootstrap.expense import (
    BI_AI_SUBJECT_MAPPING_REQUIRED_COLUMNS,
    BI_MAPPING_REQUIRED_COLUMNS,
    EXPENSE_ACTUAL_IMPORT_REQUIRED_COLUMNS,
    ensure_expense_actual_import_schema_sync,
)


REQUIRED_TABLES: dict[str, set[str]] = {
    **{table_name: set(columns) for table_name, columns in EXPENSE_ACTUAL_IMPORT_REQUIRED_COLUMNS.items()},
    **{table_name: set(columns) for table_name, columns in BI_MAPPING_REQUIRED_COLUMNS.items()},
    "bi_ai_subject_mapping": set(BI_AI_SUBJECT_MAPPING_REQUIRED_COLUMNS),
}


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


async def _table_columns_mysql(table_name: str) -> set[str]:
    rows = await get_pool().fetch_all(
        """
        SELECT COLUMN_NAME
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return {str(_row_value(row, "COLUMN_NAME", 0)) for row in rows}


async def _assert_current_mysql_contract() -> None:
    for table_name, required_columns in REQUIRED_TABLES.items():
        columns = await _table_columns_mysql(table_name)
        if not columns:
            raise RuntimeError(f"费用执行明细导入表 {table_name} 不存在，系统不再自动迁移")
        missing = sorted(required_columns - columns)
        if missing:
            raise RuntimeError(
                f"费用执行明细导入表 {table_name} 缺少当前字段，系统不再自动迁移："
                + ", ".join(missing)
            )


async def ensure_expense_actual_import_schema_ready(db_path: str | Path) -> None:
    path = Path(db_path)
    if _uses_mysql_path(path):
        await _assert_current_mysql_contract()
        return

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        try:
            ensure_expense_actual_import_schema_sync(db)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("费用执行明细导入表发现旧物理合同，系统不再自动迁移") from exc
        db.commit()
