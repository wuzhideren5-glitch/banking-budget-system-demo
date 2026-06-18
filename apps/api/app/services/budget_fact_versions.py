from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat

from app.core.config import settings
from app.core.database import get_pool
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


def _budget_year_from_file_name(file_name: str) -> int | None:
    stem = Path(file_name).stem
    if not stem.startswith("budget_"):
        return None
    suffix = stem.removeprefix("budget_")
    return int(suffix) if suffix.isdigit() else None


def _uses_mysql_path(path: Path) -> bool:
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
    return candidate.name.startswith("budget_") and candidate.suffix == ".db"


def _row_value(row: Any, key: str, index: int) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    try:
        return row[key]
    except (TypeError, KeyError, IndexError):
        return row[index]


def _row_to_version_option(row: Any) -> BudgetFactVersionOption:
    version_id = int(_row_value(row, "version_id", 0))
    return BudgetFactVersionOption(
        version_id=version_id,
        version_name=str(_row_value(row, "version_name", 1) or f"V{version_id}"),
        version_date_time=str(_row_value(row, "version_date_time", 2) or "") or None,
        current_month=int(_row_value(row, "current_month", 3)),
    )


async def load_budget_fact_version_options(
    db: Any,
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
    return [_row_to_version_option(row) for row in rows]


async def load_budget_fact_version_options_from_path(
    budget_path: Path,
) -> list[BudgetFactVersionOption]:
    budget_year = _budget_year_from_file_name(budget_path.name)
    if _uses_mysql_path(budget_path):
        if budget_year is None:
            return []
        rows = await get_pool().fetch_all(
            """
            SELECT version_id, version_name, version_date_time, current_month
            FROM version
            WHERE budget_year = %s
            ORDER BY version_id DESC
            """,
            (budget_year,),
        )
        return [_row_to_version_option(row) for row in rows]

    with sqlite3.connect(budget_path) as db:
        ensure_budget_version_schema_sync(db)
        rows = db.execute(
            """
            SELECT version_id, version_name, version_date_time, current_month
            FROM version
            ORDER BY version_id DESC
            """
        ).fetchall()
    return [_row_to_version_option(row) for row in rows]


async def load_budget_fact_current_month_from_path(
    budget_path: Path,
    version_id: int,
) -> int:
    budget_year = _budget_year_from_file_name(budget_path.name)
    if _uses_mysql_path(budget_path):
        if budget_year is None:
            raise BudgetFactVersionNotFound(version_id)
        row = await get_pool().fetch_one(
            "SELECT current_month FROM version WHERE budget_year = %s AND version_id = %s",
            (budget_year, int(version_id)),
        )
    else:
        with sqlite3.connect(budget_path) as db:
            ensure_budget_version_schema_sync(db)
            row = db.execute(
                "SELECT current_month FROM version WHERE version_id = ?",
                (int(version_id),),
            ).fetchone()
    if not row:
        raise BudgetFactVersionNotFound(version_id)
    return int(_row_value(row, "current_month", 0))


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
    db: Any,
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
    try:
        await load_budget_fact_current_month_from_path(budget_path, version_id)
    except BudgetFactVersionNotFound:
        raise
