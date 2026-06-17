"""Cross-database DDL normalization for contract marker matching.

SQLite's ``sqlite_master.sql`` and MySQL's ``SHOW CREATE TABLE`` produce DDL
text with different syntax. This module normalizes both formats to a common
representation so that contract markers written in SQLite style can match
MySQL DDL output (and vice-versa).

Normalization rules:
  * Remove backticks and double-quotes (MySQL vs SQLite identifier quoting)
  * Remove COLLATE clauses (MySQL-specific)
  * Remove ENGINE/CHARSET table options (MySQL-specific)
  * Remove CONSTRAINT names (MySQL adds ``CONSTRAINT `name` CHECK (...)``)
  * Normalize type names: ``varchar(n)`` → ``TEXT``, ``int`` → ``INTEGER``,
    ``tinyint(1)`` → ``INTEGER``, ``bigint`` → ``INTEGER``, etc.
  * Normalize ``UNIQUE KEY `name` (cols)`` → ``UNIQUE (cols)``
  * Remove plain ``KEY `name` (cols)`` and ``INDEX `name` (cols)``
  * Remove extra parentheses around CHECK expressions (MySQL double-parens)
  * Remove commas (so column-level constraints separated by commas in MySQL
    can match inline SQLite-style markers)
  * Normalize DEFAULT values: ``DEFAULT '0'`` → ``DEFAULT 0``
  * Lowercase for case-insensitive matching
  * Collapse whitespace

For marker matching, use ``marker_matches()`` instead of plain ``in`` — it
auto-splits combined markers (column definition + CHECK constraint) so that
SQLite-style inline markers match MySQL's table-level CHECK constraints.
"""
from __future__ import annotations

import re


def normalize_ddl(text: str) -> str:
    """Normalize DDL text for cross-database marker matching.

    Args:
        text: DDL text from either sqlite_master.sql or SHOW CREATE TABLE.

    Returns:
        Normalized string suitable for substring matching against
        similarly-normalized markers.
    """
    # Collapse all whitespace to single spaces
    t = " ".join(text.split())

    # Remove backticks and double-quotes (identifier quoting)
    t = t.replace("`", "").replace('"', "")

    # Remove COLLATE clauses (e.g., "COLLATE utf8mb4_unicode_ci")
    t = re.sub(r"\bCOLLATE\s+\w+", "", t, flags=re.IGNORECASE)

    # Remove MySQL table options at the end: ENGINE=... DEFAULT CHARSET=...
    t = re.sub(
        r"\)\s*ENGINE\s*=.*$",
        ")",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"\)\s*DEFAULT\s+CHARSET\s*=.*$",
        ")",
        t,
        flags=re.IGNORECASE,
    )

    # Remove "CONSTRAINT `name`" prefix before CHECK (MySQL adds auto-named constraints)
    # e.g., "CONSTRAINT budget_subject_catalog_chk_1 CHECK" → "CHECK"
    t = re.sub(
        r"\bCONSTRAINT\s+\w+\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )

    # Normalize "UNIQUE KEY `name` (cols)" → "UNIQUE (cols)"
    t = re.sub(
        r"\bUNIQUE\s+KEY\s+\w+\s*\(",
        "UNIQUE (",
        t,
        flags=re.IGNORECASE,
    )
    # Also handle "UNIQUE INDEX `name` (cols)" → "UNIQUE (cols)"
    t = re.sub(
        r"\bUNIQUE\s+INDEX\s+\w+\s*\(",
        "UNIQUE (",
        t,
        flags=re.IGNORECASE,
    )

    # Remove plain "KEY `name` (cols)" and "INDEX `name` (cols)"
    # (MySQL secondary indexes, not contract constraints)
    t = re.sub(
        r",\s*KEY\s+\w+\s*\([^)]*\)",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r",\s*INDEX\s+\w+\s*\([^)]*\)",
        "",
        t,
        flags=re.IGNORECASE,
    )

    # Normalize type names (order matters: longer patterns first)
    # tinyint(1) → INTEGER (MySQL boolean)
    t = re.sub(r"\btinyint\s*\(\s*1\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # tinyint(n) → INTEGER
    t = re.sub(r"\btinyint\s*\(\s*\d+\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # smallint(n) → INTEGER
    t = re.sub(r"\bsmallint\s*\(\s*\d+\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # mediumint(n) → INTEGER
    t = re.sub(r"\bmediumint\s*\(\s*\d+\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # int(n) → INTEGER (but NOT "integer" which is already correct)
    t = re.sub(r"\bint\s*\(\s*\d+\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # bigint(n) → INTEGER
    t = re.sub(r"\bbigint\s*\(\s*\d+\s*\)", "INTEGER", t, flags=re.IGNORECASE)
    # standalone "int" → "INTEGER" (word boundary, not part of another word)
    t = re.sub(r"\bint\b", "INTEGER", t, flags=re.IGNORECASE)
    # varchar(n) → TEXT
    t = re.sub(r"\bvarchar\s*\(\s*\d+\s*\)", "TEXT", t, flags=re.IGNORECASE)
    # char(n) → TEXT
    t = re.sub(r"\bchar\s*\(\s*\d+\s*\)", "TEXT", t, flags=re.IGNORECASE)
    # longtext → TEXT, mediumtext → TEXT, tinytext → TEXT
    t = re.sub(r"\blongtext\b", "TEXT", t, flags=re.IGNORECASE)
    t = re.sub(r"\bmediumtext\b", "TEXT", t, flags=re.IGNORECASE)
    t = re.sub(r"\btinytext\b", "TEXT", t, flags=re.IGNORECASE)
    # double → REAL (SQLite uses REAL for doubles)
    t = re.sub(r"\bdouble\b", "REAL", t, flags=re.IGNORECASE)
    t = re.sub(r"\bfloat\b", "REAL", t, flags=re.IGNORECASE)
    # decimal(p,s) → REAL
    t = re.sub(r"\bdecimal\s*\([^)]*\)", "REAL", t, flags=re.IGNORECASE)
    # datetime → TEXT (SQLite stores as TEXT)
    t = re.sub(r"\bdatetime\b", "TEXT", t, flags=re.IGNORECASE)
    # date → TEXT
    t = re.sub(r"\bdate\b", "TEXT", t, flags=re.IGNORECASE)
    # timestamp → TEXT
    t = re.sub(r"\btimestamp\b", "TEXT", t, flags=re.IGNORECASE)
    # json → TEXT (SQLite has no JSON type)
    t = re.sub(r"\bjson\b", "TEXT", t, flags=re.IGNORECASE)
    # blob → BLOB (SQLite uses BLOB)
    t = re.sub(r"\blongblob\b", "BLOB", t, flags=re.IGNORECASE)
    t = re.sub(r"\bmediumblob\b", "BLOB", t, flags=re.IGNORECASE)
    t = re.sub(r"\btinyblob\b", "BLOB", t, flags=re.IGNORECASE)
    # "AUTO_INCREMENT" → "AUTOINCREMENT" (SQLite naming)
    t = re.sub(r"\bAUTO_INCREMENT\b", "AUTOINCREMENT", t, flags=re.IGNORECASE)

    # Normalize double parentheses in CHECK: "CHECK ((expr))" → "CHECK (expr)"
    t = re.sub(
        r"CHECK\s*\(\s*\((.+?)\)\s*\)",
        r"CHECK (\1)",
        t,
        flags=re.IGNORECASE,
    )

    # Normalize DEFAULT values: remove quotes around numbers
    # e.g., DEFAULT '0' → DEFAULT 0, DEFAULT '1' → DEFAULT 1
    t = re.sub(
        r"DEFAULT\s+'(\d+)'",
        r"DEFAULT \1",
        t,
        flags=re.IGNORECASE,
    )

    # Remove commas entirely so that MySQL's comma-separated table-level
    # constraints can match SQLite-style inline markers.
    # e.g., "level_number integer not null, check (...)" matches
    #        "level_number integer not null check (...)"
    t = t.replace(",", " ")

    # Normalize spaces around parentheses: "foo(id)" → "foo (id)"
    # This ensures "references foo(id)" matches "references foo (id)"
    # Also normalizes "CHECK(col)" → "CHECK (col)" etc.
    t = re.sub(r"(\w)\(", r"\1 (", t)

    # Lowercase for case-insensitive matching
    t = t.lower()

    # Final whitespace collapse
    t = " ".join(t.split())

    return t


def marker_matches(normalized_sql: str, normalized_marker: str) -> bool:
    """Check if a normalized marker appears in normalized DDL text.

    If the marker doesn't match as a single substring but contains a ``check``
    or ``references`` clause, it is split into a column-definition part and a
    constraint part. Both parts must independently appear in the DDL.
    This handles the SQLite-vs-MySQL difference where SQLite places CHECK and
    REFERENCES inline with the column definition while MySQL places them as
    separate table-level constraints.

    Args:
        normalized_sql: Normalized DDL text (from ``normalize_ddl``).
        normalized_marker: Normalized marker text (from ``normalize_ddl``).

    Returns:
        True if the marker matches the DDL, False otherwise.
    """
    # Direct substring match — works for most markers
    if normalized_marker in normalized_sql:
        return True

    # Auto-split combined "column TYPE ... CHECK (...)" markers.
    # In MySQL's SHOW CREATE TABLE, CHECK is at table level (separated from
    # the column by other column definitions), so a combined marker won't
    # match as a single substring.
    for split_kw in (" check ", " references "):
        if split_kw in normalized_marker:
            parts = normalized_marker.split(split_kw, 1)
            if len(parts) == 2:
                col_part = parts[0].strip()
                constraint_part = split_kw.strip() + " " + parts[1].strip()
                if col_part in normalized_sql and constraint_part in normalized_sql:
                    return True

    return False


def find_missing_markers(
    table_sql: str,
    markers: tuple[str, ...],
) -> list[str]:
    """Return markers that are missing from the DDL text.

    This is the recommended replacement for the old pattern::

        normalized_sql = " ".join(table_sql.split())
        missing = [m for m in markers if m not in normalized_sql]

    It normalizes both DDL and markers, then uses ``marker_matches()`` for
    cross-database-aware matching.

    Args:
        table_sql: Raw DDL text (from sqlite_master.sql or SHOW CREATE TABLE).
        markers: Tuple of marker strings written in SQLite-style DDL syntax.

    Returns:
        List of markers that could not be found in the DDL.
    """
    normalized_sql = normalize_ddl(table_sql)
    return [
        marker
        for marker in markers
        if not marker_matches(normalized_sql, normalize_ddl(marker))
    ]
