"""Schema readiness adapter for expense forecast private tables."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import aiosqlite

from app.db_bootstrap.expense import ensure_expense_forecast_schema


async def ensure_expense_forecast_schema_ready(db_path: str | Path) -> None:
    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            await ensure_expense_forecast_schema(db)
        except sqlite3.OperationalError as exc:
            raise RuntimeError("费用预测私有表发现旧 driver 合同，系统不再自动迁移") from exc
        await db.commit()
