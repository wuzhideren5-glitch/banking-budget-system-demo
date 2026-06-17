"""Monkey-patch pymysql.Connection to support sqlite3-compatible API.

This module does two things:

1. **Patches ``pymysql.connections.Connection``** with ``execute()`` and
   ``executescript()`` methods that mimic the ``sqlite3.Connection`` API,
   including automatic SQL translation (``?``→``%s``, ``PRAGMA``→MySQL
   metadata queries, ``INSERT OR IGNORE``→``INSERT IGNORE``, etc.).

2. **Patches the stdlib ``sqlite3`` module** so that ``sqlite3.connect(path)``
   returns a real ``pymysql`` connection to MySQL, and ``sqlite3.Row`` is
   aliased to ``dict``.  This lets all synchronous code that uses
   ``import sqlite3`` work unchanged once this module is imported.

Usage — just import it anywhere before sqlite3 is used::

    import sqlite3
    import app.core.pymysql_compat  # noqa: F401 — activates the patch

    conn = sqlite3.connect("any/path.db")  # actually connects to MySQL
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (uid,))
    row = cur.fetchone()
"""
from __future__ import annotations

import re
import sqlite3 as _real_sqlite3

import pymysql

# ---------------------------------------------------------------------------
# Patch sqlite3 module — alias exception classes and Connection
# ---------------------------------------------------------------------------
_real_sqlite3.Connection = pymysql.connections.Connection  # type: ignore
_real_sqlite3.OperationalError = pymysql.err.OperationalError  # type: ignore
_real_sqlite3.ProgrammingError = pymysql.err.ProgrammingError  # type: ignore
_real_sqlite3.IntegrityError = pymysql.err.IntegrityError  # type: ignore
_real_sqlite3.Error = pymysql.err.Error  # type: ignore
_real_sqlite3.Row = dict  # type: ignore


# ---------------------------------------------------------------------------
# Regex patterns for SQL translation
# ---------------------------------------------------------------------------
_PRAGMA_TI_RE = re.compile(
    r"PRAGMA\s+table_info\s*\(\s*[\"'\x60]?(\w+)[\"'\x60]?\s*\)",
    re.IGNORECASE,
)
_PRAGMA_FK_RE = re.compile(
    r"PRAGMA\s+foreign_key_list\s*\(\s*[\"'\x60]?(\w+)[\"'\x60]?\s*\)",
    re.IGNORECASE,
)
_PRAGMA_FK_ON_RE = re.compile(
    r"^\s*PRAGMA\s+foreign_keys\s*=", re.IGNORECASE
)
_PRAGMA_INDEX_LIST_RE = re.compile(
    r"PRAGMA\s+index_list\s*\(\s*[\"'\x60]?(\w+)[\"'\x60]?\s*\)",
    re.IGNORECASE,
)

_INSERT_OR_IGNORE_RE = re.compile(
    r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE
)
_INSERT_OR_REPLACE_RE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO", re.IGNORECASE
)

_ON_CONFLICT_RE = re.compile(
    r"ON\s+CONFLICT\s*\([^)]+\)\s*DO\s+UPDATE\s+SET",
    re.IGNORECASE,
)
_EXCLUDED_RE = re.compile(r"excluded\.(\w+)", re.IGNORECASE)

_SQLITE_MASTER_RE = re.compile(r"sqlite_master", re.IGNORECASE)

_AUTOINCREMENT_RE = re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE)

_DATETIME_NOW_RE = re.compile(r"datetime\s*\(\s*'now'\s*\)", re.IGNORECASE)
_DATE_NOW_RE = re.compile(r"date\s*\(\s*'now'\s*\)", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    """Translate SQLite-specific queries to MySQL equivalents.

    Handles:
    * ``PRAGMA foreign_keys = ON`` → ``SELECT 1`` (no-op)
    * ``PRAGMA table_info(tbl)`` → ``INFORMATION_SCHEMA.COLUMNS`` query
    * ``PRAGMA foreign_key_list(tbl)`` → ``INFORMATION_SCHEMA.KEY_COLUMN_USAGE``
    * ``PRAGMA index_list(tbl)`` → ``INFORMATION_SCHEMA.STATISTICS``
    * ``INSERT OR IGNORE INTO`` → ``INSERT IGNORE INTO``
    * ``INSERT OR REPLACE INTO`` → ``REPLACE INTO``
    * ``ON CONFLICT(col) DO UPDATE SET`` → ``ON DUPLICATE KEY UPDATE``
    * ``excluded.col`` → ``VALUES(col)``
    * ``sqlite_master`` → ``INFORMATION_SCHEMA.TABLES``
    * ``AUTOINCREMENT`` → ``AUTO_INCREMENT``
    * ``datetime('now')`` → ``NOW()``
    * ``date('now')`` → ``CURDATE()``
    * ``?`` → ``%s`` (parameter placeholder)
    """
    stripped = sql.lstrip()

    # --- PRAGMA foreign_keys = ON → no-op ---
    if _PRAGMA_FK_ON_RE.match(stripped):
        return "SELECT 1"

    # --- SELECT sql FROM sqlite_master → safe fallback ---
    # SQLite's sqlite_master.sql stores the CREATE TABLE statement. MySQL has no
    # equivalent column. Callers that need DDL text use SHOW CREATE TABLE directly.
    # This fallback returns the table name so existence checks don't crash.
    _sql_master_re = re.compile(
        r"SELECT\s+sql\s+FROM\s+sqlite_master",
        re.IGNORECASE,
    )
    if _sql_master_re.search(sql):
        return (
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'"
        )

    # --- PRAGMA table_info(table) → INFORMATION_SCHEMA.COLUMNS ---
    m = _PRAGMA_TI_RE.search(sql)
    if m:
        tn = m.group(1)
        return (
            "SELECT 0 AS cid, COLUMN_NAME AS name, DATA_TYPE AS type, "
            "IF(IS_NULLABLE='YES',1,0) AS notnull, "
            "COLUMN_DEFAULT AS dflt_value, "
            "IF(COLUMN_KEY='PRI',1,0) AS pk "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{tn}' "
            "ORDER BY ORDINAL_POSITION"
        )

    # --- PRAGMA foreign_key_list(table) ---
    m = _PRAGMA_FK_RE.search(sql)
    if m:
        tn = m.group(1)
        return (
            "SELECT 0 AS id, 0 AS seq, '' AS `table`, "
            "'' AS `from`, REFERENCED_TABLE_NAME AS `to` "
            "FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{tn}' "
            "AND REFERENCED_TABLE_NAME IS NOT NULL"
        )

    # --- PRAGMA index_list(table) ---
    m = _PRAGMA_INDEX_LIST_RE.search(sql)
    if m:
        tn = m.group(1)
        return (
            "SELECT 0 AS seq, INDEX_NAME AS name, 1 AS `unique`, "
            "'origin' AS origin, '' AS partial "
            "FROM INFORMATION_SCHEMA.STATISTICS "
            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = '{tn}' "
            "GROUP BY INDEX_NAME, SEQ_IN_INDEX "
            "ORDER BY INDEX_NAME"
        )

    # --- INSERT OR IGNORE / REPLACE ---
    sql = _INSERT_OR_IGNORE_RE.sub("INSERT IGNORE INTO", sql)
    sql = _INSERT_OR_REPLACE_RE.sub("REPLACE INTO", sql)

    # --- ON CONFLICT(...) DO UPDATE SET → ON DUPLICATE KEY UPDATE ---
    sql = _ON_CONFLICT_RE.sub("ON DUPLICATE KEY UPDATE", sql)
    # excluded.col → VALUES(col)
    sql = _EXCLUDED_RE.sub(r"VALUES(\1)", sql)

    # --- sqlite_master → INFORMATION_SCHEMA.TABLES ---
    sql = _SQLITE_MASTER_RE.sub("INFORMATION_SCHEMA.TABLES", sql)
    # Fix: "type = 'table'" → "TABLE_TYPE = 'BASE TABLE'"
    sql = re.sub(
        r"INFORMATION_SCHEMA\.TABLES\s+WHERE\s+type\s*=\s*'table'",
        "INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE'",
        sql,
        flags=re.IGNORECASE,
    )
    sql = re.sub(
        r"INFORMATION_SCHEMA\.TABLES\s+WHERE\s+type\s*=\s*'view'",
        "INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA = DATABASE()",
        sql,
        flags=re.IGNORECASE,
    )
    # "name = 'foo'" on INFORMATION_SCHEMA.TABLES → "TABLE_NAME = 'foo'"
    sql = re.sub(
        r"(INFORMATION_SCHEMA\.TABLES.*?)\bname\s*=",
        r"\1TABLE_NAME =",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    sql = re.sub(
        r"(INFORMATION_SCHEMA\.TABLES.*?)\btbl_name\s*=",
        r"\1TABLE_NAME =",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # --- AUTOINCREMENT → AUTO_INCREMENT ---
    sql = _AUTOINCREMENT_RE.sub("AUTO_INCREMENT", sql)

    # --- datetime('now') → NOW() ---
    sql = _DATETIME_NOW_RE.sub("NOW()", sql)

    # --- date('now') → CURDATE() ---
    sql = _DATE_NOW_RE.sub("CURDATE()", sql)

    # --- ? → %s (parameter placeholder) ---
    sql = sql.replace("?", "%s")

    return sql


# ---------------------------------------------------------------------------
# Patch pymysql.Connection with sqlite3-compatible methods
# ---------------------------------------------------------------------------

def _execute(self: pymysql.connections.Connection, sql: str, parameters=()):
    """Mimic sqlite3.Connection.execute(). Translates SQLite SQL to MySQL."""
    sql = _translate_sql(sql)
    cursor = self.cursor()
    if parameters:
        cursor.execute(sql, parameters)
    else:
        cursor.execute(sql)
    return cursor


def _executescript(self: pymysql.connections.Connection, sql_script: str) -> None:
    """Mimic sqlite3.Connection.executescript()."""
    if "$$" in sql_script:
        statements = [
            s.strip()
            for s in sql_script.replace("DELIMITER $$", "").replace("DELIMITER ;", "").split("$$")
            if s.strip()
        ]
    else:
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
    with self.cursor() as cur:
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                translated = _translate_sql(stmt)
                try:
                    cur.execute(translated)
                except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as e:
                    print(f"[pymysql_compat] WARN: {str(e)[:100]}")


pymysql.connections.Connection.execute = _execute  # type: ignore
pymysql.connections.Connection.executescript = _executescript  # type: ignore


# ---------------------------------------------------------------------------
# Patch sqlite3.connect — route to MySQL
# ---------------------------------------------------------------------------

def _sqlite3_connect(path=None, **kwargs):
    """Drop-in replacement for sqlite3.connect — routes to MySQL.

    The *path* argument is ignored.  All connection parameters come from
    ``app.core.config.settings``.
    """
    import app.core.config as _cfg
    return pymysql.connect(
        host=_cfg.settings.MYSQL_HOST,
        port=_cfg.settings.MYSQL_PORT,
        user=_cfg.settings.MYSQL_USER,
        password=_cfg.settings.MYSQL_PASSWORD,
        database=_cfg.settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
    )


_real_sqlite3.connect = _sqlite3_connect  # type: ignore
