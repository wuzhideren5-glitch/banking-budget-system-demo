#!/usr/bin/env python3
"""MySQL database inventory verification.

Checks that all expected tables, views, columns, and triggers exist
with correct MySQL types after the SQLite→MySQL migration.

Usage:
    python -m apps.api.scripts.verify_mysql_inventory \\
        --host 127.0.0.1 --port 3306 --user root --password '' \\
        --database banking_budget
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pymysql


# ── Expected Schema ──

# Table → required columns with expected MySQL types
# type_map: column_name → expected_data_type (case-insensitive)
EXPECTED_TABLES: dict[str, dict[str, str]] = {
    # Common tables
    "budget_output_display_item": {
        "row_key": "VARCHAR", "display_view": "VARCHAR", "row_type": "VARCHAR",
        "level": "INT", "sort_order": "INT", "is_active": "TINYINT",
    },
    "data_account_metric_node": {
        "node_code": "VARCHAR", "node_name": "VARCHAR", "level": "INT",
        "node_type": "VARCHAR", "is_active": "TINYINT", "runtime_account_enabled": "TINYINT",
        "need_calc": "TINYINT", "formula_calc_mode": "TINYINT",
        "allow_manual_entry": "TINYINT", "horizontal_rollup": "TINYINT",
        "vertical_rollup": "TINYINT",
    },
    "dept_account": {"dept_code": "VARCHAR", "level": "INT", "is_leaf": "TINYINT"},
    "period": {"period_id": "INT", "days": "INT"},
    "users": {"id": "INT", "permission_type": "INT", "first_login_flag": "TINYINT"},
    "operation_log": {"log_id": "INT", "affected_rows": "INT"},
    "user_sessions": {"must_change_password": "TINYINT"},
    "budget_subject_catalog": {"level_number": "INT", "sort_order": "INT"},
    "expense_forecast_entry": {"forecast_value": "DOUBLE", "month": "INT"},
    "expense_forecast_annual_entry": {"field_value": "DOUBLE"},
    "expense_forecast_rule": {
        "enabled": "TINYINT", "allow_manual_override": "TINYINT",
        "auto_refresh_enabled": "TINYINT", "manual_recalc_enabled": "TINYINT",
        "priority": "INT", "effective_from_month": "INT", "effective_to_month": "INT",
    },
    "expense_forecast_calc_result": {"calc_value": "DOUBLE", "calc_basis_json": "JSON"},
    "expense_forecast_override": {"system_value": "DOUBLE", "override_value": "DOUBLE"},
    "expense_actual_detail_raw": {"amount": "DOUBLE", "owner_matched": "TINYINT", "subject_matched": "TINYINT"},

    # Annual tables (must have budget_year)
    "version": {"version_id": "INT", "budget_year": "INT", "current_month": "INT"},
    "settings": {"id": "INT", "budget_year": "INT", "setting_key": "VARCHAR"},
    "budget_data": {
        "id": "INT", "budget_year": "INT", "value": "DOUBLE",
        "formula_value": "DOUBLE", "manual_value": "DOUBLE",
        "budget_actual": "TINYINT", "need_calc": "TINYINT",
    },
    "budget_summary": {"id": "INT", "budget_year": "INT", "value": "DOUBLE", "budget_actual": "TINYINT"},
    "budget_pivot_aggregate": {"id": "INT", "budget_year": "INT", "value": "DOUBLE", "budget_actual": "TINYINT"},

    # Compare tables (have source_year)
    "compare_settings": {"id": "INT", "setting_key": "VARCHAR"},
    "compare_budget_summary": {"show_level": "INT", "source_year": "INT", "value": "DOUBLE", "budget_actual": "TINYINT"},
    "compare_pivot_aggregate": {"show_level": "INT", "source_year": "INT", "value": "DOUBLE", "budget_actual": "TINYINT"},
}

# Tables expected to exist (even if not in EXPECTED_TABLES)
ALL_EXPECTED_TABLES: set[str] = set(EXPECTED_TABLES.keys()) | {
    "smart_report_template", "smart_report_template_variable",
    "smart_report_calc_metric", "smart_report_blueprint",
    "smart_report_instance", "smart_report_job",
    "smart_ppt_scene", "smart_ppt_chart_config", "smart_ppt_instance",
    "databases", "edit_show_version", "feishu_user_binding",
    "expense_sync_meta", "expense_framework_budget_department",
    "expense_framework_product_department", "expense_framework_subject",
    "manage_dept_owner_mapping", "expense_forecast_rule_param",
    "expense_forecast_rule_variable", "expense_actual_import_batch",
    "bi_ai_subject_mapping", "expense_budget_entry_batch", "expense_budget_entry",
    "compare_sync_job_log",
    "business_cost_income_item", "business_cost_income_indicator",
    "business_cost_income_source_mapping", "business_cost_income_value",
    "intelligent_budget_tasks",
    "org_product_data_entry_draft", "org_product_data_entry_snapshot",
    "org_product_data_entry_snapshot_v2", "org_product_metric_table_catalog",
    "org_product_output_snapshot_v1", "org_product_tree_snapshot",
}

# Expected views
EXPECTED_VIEWS: set[str] = {
    "data_account",
    "data_account_metric_binding",
}

# Expected triggers
EXPECTED_TRIGGERS: set[str] = {
    "trg_budget_data_set_update_time_insert",
    "trg_budget_data_set_update_time_update",
}

# Annual tables that MUST have budget_year column
ANNUAL_TABLES: set[str] = {
    "version", "settings", "budget_data", "budget_summary", "budget_pivot_aggregate",
    "business_cost_income_item", "business_cost_income_indicator",
    "business_cost_income_source_mapping", "business_cost_income_value",
}


# ── Verification Logic ──

def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _setting(env_file: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key) or env_file.get(key) or default

class InventoryCheck:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed.append(name)
        else:
            self.failed.append(f"{name}: {detail}" if detail else name)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)


def _connect(params: dict) -> pymysql.Connection:
    return pymysql.connect(
        host=params["host"], port=params["port"],
        user=params["user"], password=params["password"],
        database=params["database"], charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def verify_mysql_inventory(params: dict) -> InventoryCheck:
    inv = InventoryCheck()

    conn = _connect(params)
    try:
        # 1. Check all expected tables exist
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
            """, (params["database"],))
            actual_tables = {r["TABLE_NAME"] for r in cur.fetchall()}

        for table in sorted(ALL_EXPECTED_TABLES):
            inv.check(f"Table '{table}' exists", table in actual_tables,
                      f"not found in database")

        for table in sorted(actual_tables - ALL_EXPECTED_TABLES):
            if table.startswith("__") or table.startswith("_"):
                continue
            inv.warn(f"Unexpected table: '{table}'")

        # 2. Check column types
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = %s
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """, (params["database"],))
            column_rows = cur.fetchall()

        col_map: dict[str, dict[str, str]] = defaultdict(dict)
        for r in column_rows:
            col_map[r["TABLE_NAME"]][r["COLUMN_NAME"]] = r["DATA_TYPE"].upper()

        for table, expected_cols in EXPECTED_TABLES.items():
            if table not in actual_tables:
                continue
            actual_cols = col_map.get(table, {})
            for col, expected_type in expected_cols.items():
                actual_type = actual_cols.get(col, "MISSING")
                inv.check(
                    f"  {table}.{col} type={expected_type}",
                    actual_type.upper() == expected_type.upper(),
                    f"expected {expected_type}, got {actual_type}",
                )

        # 3. Check annual tables have budget_year
        for table in sorted(ANNUAL_TABLES & actual_tables):
            has_budget_year = "budget_year" in col_map.get(table, {})
            inv.check(f"  {table} has budget_year column", has_budget_year)

        # 4. Check views
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS
                WHERE TABLE_SCHEMA = %s
            """, (params["database"],))
            actual_views = {r["TABLE_NAME"] for r in cur.fetchall()}

        for view in sorted(EXPECTED_VIEWS):
            inv.check(f"View '{view}' exists", view in actual_views)

        # 5. Check views are queryable
        for view in sorted(EXPECTED_VIEWS & actual_views):
            try:
                with conn.cursor() as cur:
                    cur.execute(f"SELECT COUNT(*) FROM `{view}`")
                    cur.fetchone()
                inv.check(f"View '{view}' is queryable", True)
            except Exception as e:
                inv.check(f"View '{view}' is queryable", False, str(e))

        # 6. Check triggers
        with conn.cursor() as cur:
            cur.execute("""
                SELECT TRIGGER_NAME FROM INFORMATION_SCHEMA.TRIGGERS
                WHERE TRIGGER_SCHEMA = %s
            """, (params["database"],))
            actual_triggers = {r["TRIGGER_NAME"] for r in cur.fetchall()}

        for trigger in sorted(EXPECTED_TRIGGERS):
            inv.check(f"Trigger '{trigger}' exists", trigger in actual_triggers)

        # 7. Check table row counts (quick sanity)
        with conn.cursor() as cur:
            for table in sorted(actual_tables & ALL_EXPECTED_TABLES):
                try:
                    cur.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
                    row = cur.fetchone()
                    cnt = row["cnt"] if row else 0
                    if cnt > 0:
                        inv.check(f"Table '{table}' has {cnt} rows", True)
                except Exception as e:
                    inv.check(f"Table '{table}' row count", False, str(e))

    finally:
        conn.close()

    return inv


def main() -> None:
    project_root = Path(__file__).resolve().parents[3]
    env_file = _load_env_file(project_root / "apps" / "api" / ".env")

    parser = argparse.ArgumentParser(description="Verify MySQL database inventory")
    parser.add_argument("--host", default=_setting(env_file, "MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(_setting(env_file, "MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=_setting(env_file, "MYSQL_USER", "root"))
    parser.add_argument("--password", default=_setting(env_file, "MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=_setting(env_file, "MYSQL_DATABASE", "banking_budget"))
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    params = {
        "host": args.host, "port": args.port,
        "user": args.user, "password": args.password,
        "database": args.database,
    }

    inv = verify_mysql_inventory(params)

    if args.json:
        print(json.dumps({
            "passed": len(inv.passed),
            "failed": len(inv.failed),
            "warnings": len(inv.warnings),
            "passed_items": inv.passed,
            "failed_items": inv.failed,
            "warnings": inv.warnings,
        }, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("MySQL Inventory Verification Report")
        print("=" * 60)
        print(f"Database: {args.database}@{args.host}:{args.port}")
        print(f"Passed: {len(inv.passed)}")
        print(f"Failed: {len(inv.failed)}")
        print(f"Warnings: {len(inv.warnings)}")
        print()

        if inv.failed:
            print("--- FAILED ---")
            for item in inv.failed:
                print(f"  ❌ {item}")

        if inv.warnings:
            print("--- WARNINGS ---")
            for w in inv.warnings:
                print(f"  ⚠️  {w}")

        if not inv.failed:
            print("✅ All critical checks passed.")

    sys.exit(1 if inv.failed else 0)


if __name__ == "__main__":
    main()
