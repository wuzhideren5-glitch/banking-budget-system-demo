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

    # Lowercase for case-insensitive matching
    t = t.lower()

    # Final whitespace collapse
    t = " ".join(t.split())

    return t
