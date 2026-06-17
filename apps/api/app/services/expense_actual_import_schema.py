"""Schema readiness adapter for expense actual import tables."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from app.db_bootstrap.expense import ensure_expense_actual_import_schema


async def ensure_expense_actual_import_schema_ready(db_path: str | Path) -> None:
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            await ensure_expense_actual_import_schema(db)
        except sqlite3.OperationalError as exc:
            raise RuntimeError("费用执行明细导入表发现旧物理合同，系统不再自动迁移") from exc
        await db.commit()
