"""Current annual budget version schema contract checks."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat
from typing import Protocol


class AsyncSqlExecutor(Protocol):
    async def execute(self, sql: str, parameters: object = ...) -> object: ...


BUDGET_VERSION_REQUIRED_COLUMNS = {
    "version_id",
    "version_date_time",
    "version_name",
    "current_month",
}


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns_sync(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    }


async def _table_columns(db: AsyncSqlExecutor, table_name: str) -> set[str]:
    cur = await db.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    rows = await cur.fetchall()  # type: ignore[attr-defined]
    return {str(row[1]) for row in rows}


def ensure_budget_version_schema_sync(conn: sqlite3.Connection) -> None:
    """Reject annual DBs whose version table is not on the current contract."""
    columns = _table_columns_sync(conn, "version")
    if not columns:
        raise RuntimeError("年度版本表 version 不存在，系统不再自动迁移")
    missing = sorted(BUDGET_VERSION_REQUIRED_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            "年度版本表 version 缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )
    invalid_versions = [
        str(row[0])
        for row in conn.execute(
            """
            SELECT version_id
            FROM version
            WHERE current_month IS NULL OR current_month NOT BETWEEN 1 AND 13
            ORDER BY version_id
            LIMIT 10
            """
        )
    ]
    if invalid_versions:
        raise RuntimeError(
            "年度版本表 version 发现无效 current_month，系统不再自动修正："
            + ", ".join(invalid_versions)
        )


async def ensure_budget_version_schema(db: AsyncSqlExecutor) -> None:
    """Async adapter for routes that read annual budget versions."""
    columns = await _table_columns(db, "version")
    if not columns:
        raise RuntimeError("年度版本表 version 不存在，系统不再自动迁移")
    missing = sorted(BUDGET_VERSION_REQUIRED_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            "年度版本表 version 缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )
    cur = await db.execute(
        """
        SELECT version_id
        FROM version
        WHERE current_month IS NULL OR current_month NOT BETWEEN 1 AND 13
        ORDER BY version_id
        LIMIT 10
        """
    )
    rows = await cur.fetchall()  # type: ignore[attr-defined]
    invalid_versions = [str(row[0]) for row in rows]
    if invalid_versions:
        raise RuntimeError(
            "年度版本表 version 发现无效 current_month，系统不再自动修正："
            + ", ".join(invalid_versions)
        )

