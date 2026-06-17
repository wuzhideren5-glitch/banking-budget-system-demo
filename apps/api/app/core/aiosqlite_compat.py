"""aiosqlite compatibility layer backed by MySQL async pool.

Drop-in replacement for ``import aiosqlite``.  All SQLite-specific SQL
is translated to MySQL at runtime, and queries are routed through the
global :class:`~app.core.database.DatabasePool`.

Usage (no code changes needed beyond the import)::

    import app.core.aiosqlite_compat as aiosqlite

    async with aiosqlite.connect(common_db) as db:
        await db.execute("PRAGMA foreign_keys = ON")        # no-op
        cur = await db.execute("SELECT * FROM users WHERE id = ?", (uid,))
        row = await cur.fetchone()
        await db.commit()                                    # no-op (autocommit)

Key design points
-----------------
* ``connect(path)`` ignores *path* — every connection comes from the
  shared MySQL pool via ``get_pool().acquire()``.
* Rows are returned as :class:`_DualRow` (a ``dict`` subclass) so both
  ``row["column_name"]`` and ``row[0]`` work, matching aiosqlite's
  behaviour when ``row_factory = aiosqlite.Row`` is set.
* ``row_factory`` is accepted but ignored (we always return dict-like
  rows).
* ``db.commit()`` is a no-op because the pool runs with
  ``autocommit = True``.
* ``PRAGMA foreign_keys = ON`` is translated to ``SELECT 1`` (no-op).
* ``?`` placeholders are translated to ``%s``.
* ``INSERT OR IGNORE INTO`` → ``INSERT IGNORE INTO``.
* ``ON CONFLICT(...) DO UPDATE SET`` → ``ON DUPLICATE KEY UPDATE``.
* ``sqlite_master`` → ``INFORMATION_SCHEMA.TABLES``.
"""

from __future__ import annotations

import re
from typing import Any, AsyncIterator

import aiomysql
import pymysql

from app.core.database import get_pool

# ---------------------------------------------------------------------------
# Public aliases — match the aiosqlite module interface
# ---------------------------------------------------------------------------

Error = pymysql.Error
OperationalError = pymysql.err.OperationalError
ProgrammingError = pymysql.err.ProgrammingError
IntegrityError = pymysql.err.IntegrityError

Row = dict  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Dual-access row — supports both row["col"] and row[0]
# ---------------------------------------------------------------------------

class _DualRow(dict):
    """A ``dict`` that also supports integer index access like ``sqlite3.Row``."""

    __slots__ = ()

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        if isinstance(key, int):
            vals = list(self.values())
            return vals[key] if 0 <= key < len(vals) else default
        return super().get(key, default)


# ---------------------------------------------------------------------------
# SQL translation
# ---------------------------------------------------------------------------

_PRAGMA_FK_RE = re.compile(
    r"^\s*PRAGMA\s+foreign_keys\s*=", re.IGNORECASE
)
_PRAGMA_TI_RE = re.compile(
    r"^\s*PRAGMA\s+table_info\s*\(\s*[\"'`\x60]?(\w+)[\"'`\x60]?\s*\)",
    re.IGNORECASE,
)
_PRAGMA_FK_LIST_RE = re.compile(
    r"^\s*PRAGMA\s+foreign_key_list\s*\(\s*[\"'`\x60]?(\w+)[\"'`\x60]?\s*\)",
    re.IGNORECASE,
)
_PRAGMA_INDEX_LIST_RE = re.compile(
    r"^\s*PRAGMA\s+index_list\s*\(\s*[\"'`\x60]?(\w+)[\"'`\x60]?\s*\)",
    re.IGNORECASE,
)

_ON_CONFLICT_RE = re.compile(
    r"ON\s+CONFLICT\s*\([^)]+\)\s*DO\s+UPDATE\s+SET",
    re.IGNORECASE,
)
_EXCLUDED_RE = re.compile(r"excluded\.(\w+)", re.IGNORECASE)

_INSERT_OR_IGNORE_RE = re.compile(
    r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE
)
_INSERT_OR_REPLACE_RE = re.compile(
    r"INSERT\s+OR\s+REPLACE\s+INTO", re.IGNORECASE
)

_SQLITE_MASTER_RE = re.compile(r"sqlite_master", re.IGNORECASE)

_AUTOINCREMENT_RE = re.compile(r"\bAUTOINCREMENT\b", re.IGNORECASE)

_DATETIME_NOW_RE = re.compile(r"datetime\s*\(\s*'now'\s*\)", re.IGNORECASE)
_DATE_NOW_RE = re.compile(r"date\s*\(\s*'now'\s*\)", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    """Translate SQLite-specific SQL fragments to MySQL equivalents."""
    stripped = sql.lstrip()

    # --- PRAGMA foreign_keys = ON → no-op ---
    if _PRAGMA_FK_RE.match(stripped):
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
    m = _PRAGMA_TI_RE.match(stripped)
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
    m = _PRAGMA_FK_LIST_RE.match(stripped)
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
    m = _PRAGMA_INDEX_LIST_RE.match(stripped)
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

    # --- MySQL doesn't allow TEXT columns in DEFAULT or in UNIQUE/INDEX without
    # key length. Convert ALL TEXT columns to VARCHAR(255).
    # Case-sensitive (uppercase only) to avoid matching 'text' in string literals.
    # \bTEXT\b doesn't match LONGTEXT/MEDIUMTEXT/TINYTEXT (word boundary protection).
    sql = re.sub(r"\bTEXT\b", "VARCHAR(255)", sql)

    # --- MySQL doesn't support CREATE INDEX IF NOT EXISTS — strip IF NOT EXISTS.
    # Duplicate index errors (1061) are handled in execute() / executescript().
    sql = re.sub(
        r"CREATE\s+(UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS",
        r"CREATE \1INDEX",
        sql,
        flags=re.IGNORECASE,
    )

    # --- MySQL doesn't allow CURRENT_TIMESTAMP as DEFAULT for VARCHAR columns.
    # Use expression default (NOW()) instead.
    sql = re.sub(
        r"DEFAULT\s+CURRENT_TIMESTAMP\b",
        r"DEFAULT (NOW())",
        sql,
        flags=re.IGNORECASE,
    )

    # --- ? → %s (parameter placeholder) ---
    sql = sql.replace("?", "%s")

    return sql


# ---------------------------------------------------------------------------
# Cursor wrapper
# ---------------------------------------------------------------------------

class _CompatCursor:
    """Async cursor wrapper that mimics aiosqlite.Cursor."""

    __slots__ = ("_cur", "_conn")

    def __init__(self, conn: aiomysql.Connection):
        self._cur: aiomysql.Cursor | None = None
        self._conn = conn

    async def execute(self, sql: str, parameters: tuple | list = ()) -> "_CompatCursor":
        sql = _translate_sql(sql)
        self._cur = await self._conn.cursor(aiomysql.DictCursor)
        try:
            if parameters:
                await self._cur.execute(sql, parameters)
            else:
                await self._cur.execute(sql)
        except pymysql.err.OperationalError as e:
            # 1061 = duplicate key name, 1060 = duplicate column name
            if e.args and e.args[0] in (1061, 1060):
                pass
            else:
                raise
        return self

    async def executemany(self, sql: str, seq_of_parameters: list[tuple] | list[list]) -> "_CompatCursor":
        sql = _translate_sql(sql)
        self._cur = await self._conn.cursor()
        await self._cur.executemany(sql, seq_of_parameters)
        return self

    async def fetchone(self) -> _DualRow | None:
        if self._cur is None:
            return None
        row = await self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return _DualRow(row)
        # Tuple cursor — wrap with column names
        desc = self._cur.description
        if desc:
            keys = [d[0] for d in desc]
            return _DualRow(zip(keys, row))
        return _DualRow(enumerate(row))

    async def fetchall(self) -> list[_DualRow]:
        if self._cur is None:
            return []
        rows = await self._cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return [_DualRow(r) for r in rows]
        # Tuple cursor — wrap
        desc = self._cur.description
        keys = [d[0] for d in desc] if desc else []
        if keys:
            return [_DualRow(zip(keys, r)) for r in rows]
        return [_DualRow(enumerate(r)) for r in rows]

    async def fetchmany(self, size: int | None = None) -> list[_DualRow]:
        if self._cur is None:
            return []
        if size is not None:
            rows = await self._cur.fetchmany(size)
        else:
            rows = await self._cur.fetchmany()
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return [_DualRow(r) for r in rows]
        desc = self._cur.description
        keys = [d[0] for d in desc] if desc else []
        if keys:
            return [_DualRow(zip(keys, r)) for r in rows]
        return [_DualRow(enumerate(r)) for r in rows]

    @property
    def lastrowid(self) -> int | None:
        if self._cur is not None:
            return self._cur.lastrowid
        return None

    @property
    def rowcount(self) -> int:
        if self._cur is not None:
            return self._cur.rowcount
        return -1

    @property
    def description(self):
        if self._cur is not None:
            return self._cur.description
        return None

    @property
    def arraysize(self) -> int:
        if self._cur is not None:
            return self._cur.arraysize
        return 1

    @arraysize.setter
    def arraysize(self, value: int) -> None:
        if self._cur is not None:
            self._cur.arraysize = value

    async def close(self) -> None:
        if self._cur is not None:
            await self._cur.close()
            self._cur = None


# ---------------------------------------------------------------------------
# Connection wrapper
# ---------------------------------------------------------------------------

class _CompatConnection:
    """Async connection wrapper that mimics aiosqlite.Connection."""

    __slots__ = ("_conn", "_row_factory")

    def __init__(self, conn: aiomysql.Connection):
        self._conn = conn
        self._row_factory: Any = None

    # --- row_factory (accepted but ignored; we always return _DualRow) ---
    @property
    def row_factory(self) -> Any:
        return self._row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._row_factory = value

    # --- execute / executemany ---
    async def execute(self, sql: str, parameters: tuple | list = ()) -> _CompatCursor:
        cur = _CompatCursor(self._conn)
        await cur.execute(sql, parameters)
        return cur

    async def executemany(self, sql: str, seq_of_parameters: list[tuple] | list[list]) -> _CompatCursor:
        cur = _CompatCursor(self._conn)
        await cur.executemany(sql, seq_of_parameters)
        return cur

    async def executescript(self, sql_script: str) -> None:
        """Execute multiple statements separated by ;"""
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        for stmt in statements:
            translated = _translate_sql(stmt)
            try:
                async with self._conn.cursor() as cur:
                    await cur.execute(translated)
            except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as e:
                # 1061 = duplicate key name, 1060 = duplicate column name
                if e.args and e.args[0] in (1061, 1060):
                    continue
                print(f"[aiosqlite_compat] WARN: {str(e)[:100]}")

    # --- commit / rollback (no-ops; autocommit is on) ---
    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    # --- cursor (raw aiomysql cursor) ---
    async def cursor(self, *args, **kwargs) -> aiomysql.Cursor:
        return await self._conn.cursor(*args, **kwargs)

    # --- close ---
    async def close(self) -> None:
        self._conn.close()

    @property
    def lastrowid(self) -> int | None:
        return None

    @property
    def in_transaction(self) -> bool:
        return False

    @property
    def isolation_level(self) -> str | None:
        return None

    @isolation_level.setter
    def isolation_level(self, value: str | None) -> None:
        pass

    @property
    def total_changes(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# connect() — drop-in replacement for aiosqlite.connect()
# ---------------------------------------------------------------------------

class _ConnectContextManager:
    """Async context manager that yields a :class:`_CompatConnection`."""

    __slots__ = ("_pool", "_acquire_cm", "_conn")

    def __init__(self):
        self._pool = get_pool()
        self._acquire_cm = None
        self._conn = None

    async def __aenter__(self) -> _CompatConnection:
        self._acquire_cm = self._pool.acquire()
        raw_conn = await self._acquire_cm.__aenter__()
        self._conn = _CompatConnection(raw_conn)
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._acquire_cm is not None:
            await self._acquire_cm.__aexit__(exc_type, exc, tb)
        self._conn = None
        self._acquire_cm = None

    def __await__(self):
        """Support ``db = await aiosqlite.connect(path)`` pattern."""
        return self._await().__await__()

    async def _await(self) -> _CompatConnection:
        self._acquire_cm = self._pool.acquire()
        raw_conn = await self._acquire_cm.__aenter__()
        self._conn = _CompatConnection(raw_conn)
        return self._conn


def connect(path: Any = None, **kwargs) -> _ConnectContextManager:
    """Drop-in replacement for :func:`aiosqlite.connect`.

    The *path* argument is ignored — all connections come from the
    global MySQL pool.
    """
    return _ConnectContextManager()


# ---------------------------------------------------------------------------
# Public class aliases — match the aiosqlite module interface
# ---------------------------------------------------------------------------

Connection = _CompatConnection
Cursor = _CompatCursor
