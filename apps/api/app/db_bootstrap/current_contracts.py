"""Current-contract checks for existing SQLite databases."""
from __future__ import annotations

import sqlite3
import app.core.pymysql_compat  # noqa: F401 -- SQLite->MySQL compat

from app.services.org_product_runtime_catalog import drop_retired_product_type_object


RUNTIME_METRIC_REF_REQUIRED_COLUMNS = [
    "data_acct_code",
    "data_acct_name",
    "budget_formula",
    "actual_formula",
    "budget_rule_code",
    "budget_rule_config_json",
    "need_calc",
    "formula_calc_mode",
    "allow_manual_entry",
    "value_type",
    "remark",
]

def ensure_runtime_metric_identity_schema(conn: sqlite3.Connection) -> None:
    """Reject runtime metric reference shapes outside the current product-prefixed contract."""
    cur = conn.execute("PRAGMA table_info(data_account)")
    cols = {str(r[1]) for r in cur.fetchall()}
    required = set(RUNTIME_METRIC_REF_REQUIRED_COLUMNS)
    missing = sorted(required - cols)
    if missing:
        raise RuntimeError(
            "运行指标引用表缺少当前字段，系统不再自动迁移："
            + ", ".join(missing)
        )

    retired_or_extra = sorted(cols - required)
    if retired_or_extra:
        raise RuntimeError(
            "运行指标引用表发现旧字段/非当前字段，系统不再自动迁移："
            + ", ".join(retired_or_extra)
        )

    bad_flags = [
        str(row[0] or "").strip()
        for row in conn.execute(
            """
            SELECT data_acct_code
            FROM data_account
            WHERE need_calc NOT IN (0, 1)
               OR allow_manual_entry NOT IN (0, 1)
               OR formula_calc_mode NOT BETWEEN 0 AND 3
               OR value_type IS NULL
               OR TRIM(value_type) = ''
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
    ]
    if bad_flags:
        raise RuntimeError(
            "运行指标引用表发现无效当前字段值，系统不再自动修正："
            + ", ".join(bad_flags)
        )

    stale_formula_modes = [
        str(row[0] or "").strip()
        for row in conn.execute(
            """
            SELECT data_acct_code
            FROM data_account
            WHERE formula_calc_mode <>
              (CASE WHEN COALESCE(TRIM(budget_formula), '') <> '' THEN 1 ELSE 0 END) +
              (CASE WHEN COALESCE(TRIM(actual_formula), '') <> '' THEN 2 ELSE 0 END)
            ORDER BY data_acct_code
            LIMIT 10
            """
        )
    ]
    if stale_formula_modes:
        raise RuntimeError(
            "运行指标引用表发现公式计算模式与公式字段不一致，系统不再自动修正："
            + ", ".join(stale_formula_modes)
        )


def ensure_org_product_runtime_catalog_schema(conn: sqlite3.Connection) -> None:
    """Ensure the retired product maintenance table/view is absent."""
    drop_retired_product_type_object(conn)
