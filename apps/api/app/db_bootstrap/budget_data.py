"""Current annual budget_data schema and value contract checks."""
from __future__ import annotations

import sqlite3
from pathlib import Path

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


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def ensure_budget_data_fact_contract(conn: sqlite3.Connection) -> None:
    """Ensure budget_data uses the current product-scoped fact grain."""
    if not _table_exists(conn, "budget_data"):
        return
    cur = conn.execute("PRAGMA table_info(budget_data)")
    cols = {str(r[1]) for r in cur.fetchall()}
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
        for row in conn.execute(
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE need_calc IS NULL OR need_calc NOT IN (0, 1)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
    ]
    if invalid_need_calc:
        raise RuntimeError(
            "年度预算事实表发现无效 need_calc，系统不再自动修正："
            + ", ".join(invalid_need_calc)
        )


def ensure_budget_data_value_contract(conn: sqlite3.Connection) -> None:
    """Ensure budget_data uses the current manual/formula/effective value contract."""
    if not _table_exists(conn, "budget_data"):
        return
    cur = conn.execute("PRAGMA table_info(budget_data)")
    cols = {str(r[1]) for r in cur.fetchall()}
    missing_columns = sorted(BUDGET_DATA_REQUIRED_VALUE_COLUMNS - cols)
    if missing_columns:
        raise RuntimeError(
            "年度预算事实表缺少当前取值字段，系统不再自动迁移："
            + ", ".join(missing_columns)
        )

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'budget_data'"
    ).fetchone()
    table_sql = str(row[0] or "") if row else ""
    if not all(f"'{source}'" in table_sql for source in BUDGET_DATA_VALUE_SOURCES):
        raise RuntimeError(
            "年度预算事实表 value_source 约束不是当前合同，系统不再自动重建"
        )

    bad_sources = [
        str(row[0] or "").strip()
        for row in conn.execute(
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
    ]
    if bad_sources:
        raise RuntimeError(
            "年度预算事实表发现无效取值来源，系统不再自动回填："
            + ", ".join(bad_sources)
        )

    mismatched_values = [
        str(row[0] or "").strip()
        for row in conn.execute(
            """
            SELECT data_acct_code
            FROM budget_data
            WHERE (value_source = 'manual' AND ABS(COALESCE(value, 0) - COALESCE(manual_value, 0)) > 0.0000001)
               OR (value_source IN ('formula', 'rollup') AND ABS(COALESCE(value, 0) - COALESCE(formula_value, 0)) > 0.0000001)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
    ]
    if mismatched_values:
        raise RuntimeError(
            "年度预算事实表发现生效值与来源值不一致，系统不再自动修正："
            + ", ".join(mismatched_values)
        )


def ensure_budget_data_update_time_triggers(conn: sqlite3.Connection) -> None:
    """Ensure budget_data update_time is maintained at DB level."""
    if not _table_exists(conn, "budget_data"):
        return
    ensure_budget_data_fact_contract(conn)
    ensure_budget_data_value_contract(conn)
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_insert
        AFTER INSERT ON budget_data
        FOR EACH ROW
        WHEN NEW.update_time IS NULL OR TRIM(NEW.update_time) = ''
        BEGIN
          UPDATE budget_data
          SET update_time = CURRENT_TIMESTAMP
          WHERE rowid = NEW.rowid;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_budget_data_set_update_time_update
        AFTER UPDATE OF data_acct_code, product_code, period_id, budget_actual, version_id, value, formula_value, manual_value, value_source, need_calc, create_time
        ON budget_data
        FOR EACH ROW
        BEGIN
          UPDATE budget_data
          SET update_time = CURRENT_TIMESTAMP
          WHERE rowid = NEW.rowid;
        END;
        """
    )


def validate_budget_data_fact_table(budget_path: Path) -> None:
    """Validate one annual budget_data table against the current fact schema."""
    conn = sqlite3.connect(budget_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_budget_data_fact_contract(conn)
        ensure_budget_data_update_time_triggers(conn)
        conn.commit()
    finally:
        conn.close()
    ensure_budget_data_uses_current_metric_identity(budget_path)
