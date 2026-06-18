"""Current annual budget_data schema and value contract checks."""
from __future__ import annotations

import pymysql
import sqlite3
from pathlib import Path

from app.db_bootstrap._ddl_normalize import normalize_ddl
from app.db_bootstrap.runtime_metric_tree import (
    ensure_budget_data_uses_current_metric_identity,
)

BUDGET_DATA_REQUIRED_FACT_COLUMNS = {
    "data_acct_code",
    "product_code",
    "period_id",
    "budget_actual",
    "version_id",
    "value",
    "need_calc",
}
BUDGET_DATA_REQUIRED_VALUE_COLUMNS = {"formula_value", "manual_value", "value_source"}
BUDGET_DATA_VALUE_SOURCES = {"manual", "formula", "none", "rollup"}
RETIRED_BUDGET_DATA_COLUMNS = {"needs_calc", "data_type"}


def _fetchall(conn, sql: str, params: tuple = ()):
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        close = getattr(cur, "close", None)
        if close is not None:
            close()


def _fetchone(conn, sql: str, params: tuple = ()):
    rows = _fetchall(conn, sql, params)
    return rows[0] if rows else None


def _table_exists(conn: pymysql.Connection, table_name: str) -> bool:
    try:
        return _fetchone(
            conn,
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        ) is not None
    except Exception:
        return _fetchone(
            conn,
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ) is not None


def _table_columns(conn: pymysql.Connection, table_name: str) -> set[str]:
    try:
        rows = _fetchall(
            conn,
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        return {str(row[0]) for row in rows}
    except Exception:
        return {str(row[1]) for row in _fetchall(conn, f"PRAGMA table_info({table_name})")}


def ensure_budget_data_fact_contract(conn: pymysql.Connection) -> None:
    """Ensure budget_data uses the current product-scoped fact grain."""
    if not _table_exists(conn, "budget_data"):
        return
    cols = _table_columns(conn, "budget_data")
    retired_columns = sorted(cols & RETIRED_BUDGET_DATA_COLUMNS)
    if retired_columns:
        raise RuntimeError(
            "年度预算事实表发现旧字段，系统不再自动迁移："
            + ", ".join(retired_columns)
        )
    missing_columns = sorted(BUDGET_DATA_REQUIRED_FACT_COLUMNS - cols)
    if missing_columns:
        raise RuntimeError(
            "年度预算事实表缺少当前字段，系统不再自动迁移："
            + ", ".join(missing_columns)
        )
    invalid_need_calc = [
        str(row[0] or "").strip()
        for row in _fetchall(
            conn,
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE need_calc IS NULL OR need_calc NOT IN (0, 1)
            ORDER BY data_acct_code
            LIMIT 10
            """,
        )
    ]
    if invalid_need_calc:
        raise RuntimeError(
            "年度预算事实表发现无效 need_calc，系统不再自动修正："
            + ", ".join(invalid_need_calc)
        )


def ensure_budget_data_value_contract(conn: pymysql.Connection) -> None:
    """Ensure budget_data uses the current manual/formula/effective value contract."""
    if not _table_exists(conn, "budget_data"):
        return
    cols = _table_columns(conn, "budget_data")
    missing_columns = sorted(BUDGET_DATA_REQUIRED_VALUE_COLUMNS - cols)
    if missing_columns:
        raise RuntimeError(
            "年度预算事实表缺少当前取值字段，系统不再自动迁移："
            + ", ".join(missing_columns)
        )

    try:
        row = _fetchone(conn, "SHOW CREATE TABLE `budget_data`")
        ddl = str(row[1] if row and len(row) > 1 else "")
    except Exception:
        row = _fetchone(
            conn,
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("budget_data",),
        )
        ddl = str(row[0] if row else "")
    check_text = normalize_ddl(ddl)
    missing_value_sources = sorted(
        source for source in BUDGET_DATA_VALUE_SOURCES if source not in check_text
    )
    if missing_value_sources:
        raise RuntimeError(
            "年度预算事实表 value_source 约束不是当前合同，系统不再自动重建"
        )

    bad_sources = [
        str(row[0] or "").strip()
        for row in _fetchall(
            conn,
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE value_source NOT IN ('manual', 'formula', 'none', 'rollup')
               OR (value_source = 'manual' AND manual_value IS NULL)
               OR (value_source IN ('formula', 'rollup') AND formula_value IS NULL)
            ORDER BY data_acct_code
            LIMIT 10
            """,
        )
    ]
    if bad_sources:
        raise RuntimeError(
            "年度预算事实表发现无效取值来源，系统不再自动回填："
            + ", ".join(bad_sources)
        )

    mismatched_values = [
        str(row[0] or "").strip()
        for row in _fetchall(
            conn,
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE (value_source = 'manual' AND ABS(COALESCE(value, 0) - COALESCE(manual_value, 0)) > 0.0000001)
               OR (value_source IN ('formula', 'rollup') AND ABS(COALESCE(value, 0) - COALESCE(formula_value, 0)) > 0.0000001)
            ORDER BY data_acct_code
            LIMIT 10
            """,
        )
    ]
    if mismatched_values:
        raise RuntimeError(
            "年度预算事实表发现生效值与来源值不一致，系统不再自动修正："
            + ", ".join(mismatched_values)
        )


def ensure_budget_data_update_time_triggers(conn: pymysql.Connection) -> None:
    """Ensure budget_data update_time is maintained at DB level (MySQL trigger).

    MySQL does not support ``CREATE TRIGGER IF NOT EXISTS`` (MariaDB-only).
    We use ``DROP TRIGGER IF EXISTS`` followed by ``CREATE TRIGGER`` for
    idempotent behaviour.
    """
    if not _table_exists(conn, "budget_data"):
        return
    ensure_budget_data_fact_contract(conn)
    ensure_budget_data_value_contract(conn)
    conn_type = f"{type(conn).__module__}.{type(conn).__name__}".lower()
    if "sqlite" in conn_type:
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_insert
            AFTER INSERT ON budget_data
            FOR EACH ROW
            WHEN NEW.update_time IS NULL OR TRIM(COALESCE(NEW.update_time, '')) = ''
            BEGIN
              UPDATE budget_data SET update_time = datetime('now') WHERE id = NEW.id;
            END;

            CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_update
            AFTER UPDATE ON budget_data
            FOR EACH ROW
            BEGIN
              UPDATE budget_data SET update_time = datetime('now') WHERE id = NEW.id;
            END;
            """
        )
        return
    with conn.cursor() as cur:
        # Drop existing triggers (idempotent — safe if they don't exist)
        cur.execute("DROP TRIGGER IF EXISTS trg_budget_data_set_update_time_insert")
        cur.execute("DROP TRIGGER IF EXISTS trg_budget_data_set_update_time_update")

        # MySQL BEFORE INSERT trigger
        cur.execute(
            """
            CREATE TRIGGER trg_budget_data_set_update_time_insert
            BEFORE INSERT ON budget_data
            FOR EACH ROW
            BEGIN
              IF NEW.update_time IS NULL OR TRIM(NEW.update_time) = '' THEN
                SET NEW.update_time = NOW();
              END IF;
            END
            """
        )
        # MySQL BEFORE UPDATE trigger
        cur.execute(
            """
            CREATE TRIGGER trg_budget_data_set_update_time_update
            BEFORE UPDATE ON budget_data
            FOR EACH ROW
            BEGIN
              SET NEW.update_time = NOW();
            END
            """
        )


def validate_budget_data_fact_table(conn: pymysql.Connection | str | Path) -> None:
    """Validate budget_data table against the current fact schema."""
    if isinstance(conn, (str, Path)):
        sqlite_conn = sqlite3.connect(conn)
        try:
            validate_budget_data_fact_table(sqlite_conn)
            sqlite_conn.commit()
            return
        finally:
            sqlite_conn.close()
    conn_type = f"{type(conn).__module__}.{type(conn).__name__}".lower()
    if "sqlite" in conn_type:
        ensure_budget_data_fact_contract(conn)
        ensure_budget_data_update_time_triggers(conn)
        conn.commit()
        ensure_budget_data_uses_current_metric_identity(conn)
        return
    with conn.cursor() as cur:
        cur.execute("SET foreign_key_checks = 1")
    ensure_budget_data_fact_contract(conn)
    ensure_budget_data_update_time_triggers(conn)
    conn.commit()
    ensure_budget_data_uses_current_metric_identity(conn)
