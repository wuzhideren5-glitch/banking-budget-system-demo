"""MySQL schema introspection utilities.

Provides INFORMATION_SCHEMA-based helpers to replace SQLite PRAGMA/sqlite_master queries.
"""
from __future__ import annotations

from typing import Any

import aiomysql
import pymysql

from app.core.database import get_pool
from app.core.config import settings


async def get_table_columns(table_name: str) -> list[dict[str, Any]]:
    """Return column metadata for a table (replaces PRAGMA table_info).

    Returns list of dicts with keys: COLUMN_NAME, DATA_TYPE, IS_NULLABLE,
    COLUMN_DEFAULT, COLUMN_KEY, EXTRA, ORDINAL_POSITION.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                       COLUMN_KEY, EXTRA, ORDINAL_POSITION
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
                """,
                (settings.MYSQL_DATABASE, table_name),
            )
            return list(await cur.fetchall())


async def table_exists(table_name: str) -> bool:
    """Check if a table exists (replaces sqlite_master query)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """,
                (settings.MYSQL_DATABASE, table_name),
            )
            row = await cur.fetchone()
    return bool(row and row[0] > 0)


async def view_exists(view_name: str) -> bool:
    """Check if a view exists."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                """,
                (settings.MYSQL_DATABASE, view_name),
            )
            row = await cur.fetchone()
    return bool(row and row[0] > 0)


async def get_all_tables() -> list[str]:
    """Return all base table names in the database."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
                """,
                (settings.MYSQL_DATABASE,),
            )
            rows = await cur.fetchall()
    return [r["TABLE_NAME"] for r in rows]


async def get_all_views() -> list[str]:
    """Return all view names in the database."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME
                """,
                (settings.MYSQL_DATABASE,),
            )
            rows = await cur.fetchall()
    return [r["TABLE_NAME"] for r in rows]


async def get_triggers() -> list[str]:
    """Return all trigger names in the database."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """
                SELECT TRIGGER_NAME
                FROM INFORMATION_SCHEMA.TRIGGERS
                WHERE TRIGGER_SCHEMA = %s
                ORDER BY TRIGGER_NAME
                """,
                (settings.MYSQL_DATABASE,),
            )
            rows = await cur.fetchall()
    return [r["TRIGGER_NAME"] for r in rows]


async def column_has_type(table_name: str, column_name: str, expected_type: str) -> bool:
    """Check if a column has the expected MySQL type (case-insensitive)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
                """,
                (settings.MYSQL_DATABASE, table_name, column_name),
            )
            row = await cur.fetchone()
    if not row:
        return False
    return str(row[0] or "").upper() == expected_type.upper()


async def table_has_column(table_name: str, column_name: str) -> bool:
    """Check if a table has a specific column."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
                """,
                (settings.MYSQL_DATABASE, table_name, column_name),
            )
            row = await cur.fetchone()
    return bool(row and row[0] > 0)


# ---------------------------------------------------------------------------
# Synchronous pymysql helpers for startup bootstrap (_sync functions)
# ---------------------------------------------------------------------------


def _pymysql_columns(conn: pymysql.connections.Connection, table_name: str) -> list[dict]:
    """Return column info for a table using INFORMATION_SCHEMA.

    Returns list of dicts with keys: COLUMN_NAME, DATA_TYPE, etc.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT,
                   COLUMN_KEY, EXTRA, ORDINAL_POSITION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _pymysql_column_names(conn: pymysql.connections.Connection, table_name: str) -> list[str]:
    """Return just column names for a table (replaces PRAGMA table_info)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _pymysql_show_create(conn: pymysql.connections.Connection, table_name: str) -> str:
    """Return CREATE TABLE statement (replaces sqlite_master query)."""
    with conn.cursor() as cur:
        cur.execute(f"SHOW CREATE TABLE `{table_name}`")
        row = cur.fetchone()
        return str(row[1] or "") if row else ""


def _pymysql_foreign_keys(conn: pymysql.connections.Connection, table_name: str) -> list[str]:
    """Return referenced table names for a table's foreign keys."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT REFERENCED_TABLE_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (table_name,),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _pymysql_table_exists(conn: pymysql.connections.Connection, table_name: str) -> bool:
    """Check if a table exists."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        row = cur.fetchone()
    return bool(row and row[0] > 0)


def _pymysql_fetch_all(conn: pymysql.connections.Connection, sql: str, params=None) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _pymysql_fetch_one(conn: pymysql.connections.Connection, sql: str, params=None):
    """Execute a query and return first row as dict or None."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        if not row:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))


def _pymysql_fetch_val(conn: pymysql.connections.Connection, sql: str, params=None):
    """Execute a query and return first column of first row."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return row[0] if row else None


def _pymysql_execute(conn: pymysql.connections.Connection, sql: str, params=None) -> int:
    """Execute a write query and return affected rows."""
    with conn.cursor() as cur:
        cur.execute(sql, params or ())
        return cur.rowcount


def _quote_identifier_mysql(identifier: str) -> str:
    """Quote an identifier with MySQL backticks (replaces SQLite double-quote version)."""
    return '`' + identifier.replace('`', '``') + '`'


def _pymysql_executescript(conn: pymysql.connections.Connection, sql_script: str) -> None:
    """Execute a multi-statement SQL script by splitting on semicolons.

    Uses $$ delimiter splitting only when triggers/procedures are present.
    """
    if "$$" in sql_script:
        statements = [
            s.strip()
            for s in sql_script.replace("DELIMITER $$", "").replace("DELIMITER ;", "").split("$$")
            if s.strip()
        ]
    else:
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
    with conn.cursor() as cur:
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as e:
                    print(f"[db_introspection] WARNING: DDL error (skipped): {str(e)[:100]}")