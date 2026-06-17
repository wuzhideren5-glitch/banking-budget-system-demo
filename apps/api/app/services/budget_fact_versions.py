from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat

import app.core.aiosqlite_compat as aiosqlite
from app.db_bootstrap.budget_version import ensure_budget_version_schema, ensure_budget_version_schema_sync
from app.schemas import BudgetFactVersionOption


class BudgetFactVersionNotFound(Exception):
    def __init__(self, version_id: int):
        super().__init__(version_id)
        self.version_id = version_id


@dataclass(frozen=True)
class BudgetFactVersionIdentity:
    version_id: int
    version_name: str
    current_month: int


async def load_budget_fact_version_options(
    db: aiosqlite.Connection,
) -> list[BudgetFactVersionOption]:
    await ensure_budget_version_schema(db)
    cur = await db.execute(
        """
        SELECT version_id, version_name, version_date_time, current_month
        FROM version
        ORDER BY version_id DESC
        """
    )
    rows = await cur.fetchall()
    return [
        BudgetFactVersionOption(
            version_id=int(row[0]),
            version_name=str(row[1] or f"V{row[0]}"),
            version_date_time=str(row[2] or "") or None,
            current_month=int(row[3]),
        )
        for row in rows
    ]


async def load_budget_fact_version_options_from_path(
    budget_path: Path,
) -> list[BudgetFactVersionOption]:
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        return await load_budget_fact_version_options(db)


async def load_budget_fact_current_month_from_path(
    budget_path: Path,
    version_id: int,
) -> int:
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await ensure_budget_version_schema(db)
        cur = await db.execute(
            "SELECT current_month FROM version WHERE version_id = ?",
            (int(version_id),),
        )
        row = await cur.fetchone()
    if not row:
        raise BudgetFactVersionNotFound(version_id)
    return int(row[0])


def load_budget_fact_version_identity_sync(
    db: sqlite3.Connection,
    version_id: int,
) -> BudgetFactVersionIdentity:
    ensure_budget_version_schema_sync(db)
    cur = db.execute(
        """
        SELECT version_name, current_month
        FROM version
        WHERE version_id = ?
        """,
        (int(version_id),),
    )
    row = cur.fetchone()
    if not row:
        raise BudgetFactVersionNotFound(version_id)
    return BudgetFactVersionIdentity(
        version_id=int(version_id),
        version_name=str(row[0] or f"V{version_id}"),
        current_month=int(row[1]),
    )


async def budget_fact_version_exists(
    db: aiosqlite.Connection,
    version_id: int,
) -> bool:
    cur = await db.execute(
        "SELECT 1 FROM version WHERE version_id = ?",
        (int(version_id),),
    )
    return await cur.fetchone() is not None


async def ensure_budget_fact_version_exists(
    budget_path: Path,
    version_id: int,
) -> None:
    async with aiosqlite.connect(budget_path) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        if not await budget_fact_version_exists(db, version_id):
            raise BudgetFactVersionNotFound(version_id)
