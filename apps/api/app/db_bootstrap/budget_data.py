"""Current annual budget_data schema and value contract checks."""
from __future__ import annotations

import pymysql

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


def _table_exists(conn: pymysql.Connection, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            """,
            (table_name,),
        )
        return cur.fetchone() is not None


def _table_columns(conn: pymysql.Connection, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
            """,
            (table_name,),
        )
        return {str(row[0]) for row in cur.fetchall()}


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
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE need_calc IS NULL OR need_calc NOT IN (0, 1)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
        invalid_need_calc = [
            str(row[0] or "").strip()
            for row in cur.fetchall()
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

    # Verify CHECK constraint exists via INFORMATION_SCHEMA
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT CHECK_CLAUSE FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'budget_data'
            """
        )
        check_rows = cur.fetchall()
    check_text = " ".join(str(r[0] or "") for r in check_rows).lower()
    if not any(source in check_text for source in BUDGET_DATA_VALUE_SOURCES):
        raise RuntimeError(
            "年度预算事实表 value_source 约束不是当前合同，系统不再自动重建"
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE value_source NOT IN ('manual', 'formula', 'none', 'rollup')
               OR (value_source = 'manual' AND manual_value IS NULL)
               OR (value_source IN ('formula', 'rollup') AND formula_value IS NULL)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
        bad_sources = [
            str(row[0] or "").strip()
            for row in cur.fetchall()
        ]
    if bad_sources:
        raise RuntimeError(
            "年度预算事实表发现无效取值来源，系统不再自动回填："
            + ", ".join(bad_sources)
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE (value_source = 'manual' AND ABS(COALESCE(value, 0) - COALESCE(manual_value, 0)) > 0.0000001)
               OR (value_source IN ('formula', 'rollup') AND ABS(COALESCE(value, 0) - COALESCE(formula_value, 0)) > 0.0000001)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
        mismatched_values = [
            str(row[0] or "").strip()
            for row in cur.fetchall()
        ]
    if mismatched_values:
        raise RuntimeError(
            "年度预算事实表发现生效值与来源值不一致，系统不再自动修正："
            + ", ".join(mismatched_values)
        )


def ensure_budget_data_update_time_triggers(conn: pymysql.Connection) -> None:
    """Ensure budget_data update_time is maintained at DB level (MySQL trigger)."""
    if not _table_exists(conn, "budget_data"):
        return
    ensure_budget_data_fact_contract(conn)
    ensure_budget_data_value_contract(conn)
    with conn.cursor() as cur:
        # MySQL BEFORE INSERT trigger
        cur.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_insert
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
            CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_update
            BEFORE UPDATE ON budget_data
            FOR EACH ROW
            BEGIN
              SET NEW.update_time = NOW();
            END
            """
        )


def validate_budget_data_fact_table(conn: pymysql.Connection) -> None:
    """Validate budget_data table against the current fact schema."""
    with conn.cursor() as cur:
        cur.execute("SET foreign_key_checks = 1")
    ensure_budget_data_fact_contract(conn)
    ensure_budget_data_update_time_triggers(conn)
    conn.commit()
    ensure_budget_data_uses_current_metric_identity(conn)
