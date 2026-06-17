from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db_bootstrap.retired_deletion import (
    delete_retired_tables,
    existing_retired_tables,
)


class RetiredDeletionTests(unittest.TestCase):
    def test_delete_retired_tables_backs_up_and_drops_only_retired_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            db_path = base / "common.db"
            backup_root = base / "backups"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE _codex_write_test (id INTEGER PRIMARY KEY);
                    CREATE TABLE report_account (legacy_report_code TEXT PRIMARY KEY);
                    CREATE TABLE report_data_mapping (
                      id INTEGER PRIMARY KEY,
                      legacy_report_code TEXT REFERENCES report_account(legacy_report_code)
                    );
                    CREATE TABLE budget_report_display_item (row_key TEXT PRIMARY KEY);
                    CREATE TABLE driver_category (category_code TEXT PRIMARY KEY);
                    CREATE TABLE driver_indicator (
                      indicator_code TEXT PRIMARY KEY,
                      category_code TEXT REFERENCES driver_category(category_code)
                    );
                    CREATE TABLE driver_product (
                      id INTEGER PRIMARY KEY,
                      indicator_code TEXT REFERENCES driver_indicator(indicator_code)
                    );
                    CREATE TABLE driver_account_mapping (
                      id INTEGER PRIMARY KEY,
                      indicator_code TEXT REFERENCES driver_indicator(indicator_code)
                    );
                    CREATE TABLE control_item_subject_mapping (
                      id INTEGER PRIMARY KEY,
                      control_item_name TEXT NOT NULL
                    );
                    CREATE TABLE scenario_catalog (scenario_code TEXT PRIMARY KEY);
                    CREATE TABLE assumption_parameter (parameter_code TEXT PRIMARY KEY);
                    CREATE TABLE assumption_rule_template (rule_code TEXT PRIMARY KEY);
                    CREATE TABLE assumption_value (
                      id INTEGER PRIMARY KEY,
                      parameter_code TEXT REFERENCES assumption_parameter(parameter_code),
                      scenario_code TEXT REFERENCES scenario_catalog(scenario_code)
                    );
                    CREATE TABLE forecast_workbench_layout (line_code TEXT PRIMARY KEY);
                    CREATE TABLE forecast_line_binding (
                      id INTEGER PRIMARY KEY,
                      line_code TEXT REFERENCES forecast_workbench_layout(line_code)
                    );
                    CREATE TABLE chart_template (template_id INTEGER PRIMARY KEY);
                    CREATE TABLE smart_report_definition (report_id INTEGER PRIMARY KEY);
                    CREATE TABLE pivot_aggregate_rule (rule_code TEXT PRIMARY KEY);
                    CREATE TABLE dept_product_mapping (id INTEGER PRIMARY KEY);
                    CREATE TABLE dept_name_alias (alias_name TEXT PRIMARY KEY);
                    CREATE TABLE expense_execution_monthly (id INTEGER PRIMARY KEY);
                    CREATE TABLE expense_sync_meta (
                      sync_key TEXT PRIMARY KEY NOT NULL,
                      source_file TEXT NOT NULL,
                      source_mtime TEXT,
                      synced_at TEXT NOT NULL,
                      row_count INTEGER NOT NULL DEFAULT 0,
                      note TEXT
                    );
                    CREATE TABLE product_budget_component (id INTEGER PRIMARY KEY);
                    CREATE TABLE data_account (data_acct_code TEXT PRIMARY KEY NOT NULL);
                    INSERT INTO expense_sync_meta(sync_key, source_file, synced_at, row_count, note)
                    VALUES
                      ('actual_import', 'old-actual-sync.xlsx', '2026-05-01', 10, 'retired'),
                      ('framework_import', 'framework.xlsx', '2026-05-01', 3, 'current');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            self.assertEqual(
                existing_retired_tables(db_path),
                (
                    "_codex_write_test",
                    "report_data_mapping",
                    "report_account",
                    "budget_report_display_item",
                    "driver_account_mapping",
                    "driver_product",
                    "driver_indicator",
                    "driver_category",
                    "control_item_subject_mapping",
                    "forecast_line_binding",
                    "forecast_workbench_layout",
                    "assumption_value",
                    "assumption_rule_template",
                    "assumption_parameter",
                    "scenario_catalog",
                    "chart_template",
                    "smart_report_definition",
                    "pivot_aggregate_rule",
                    "dept_product_mapping",
                    "dept_name_alias",
                    "expense_execution_monthly",
                    "product_budget_component",
                ),
            )

            result = delete_retired_tables(db_path, backup_root=backup_root)

            self.assertEqual(
                result.deleted_tables,
                (
                    "_codex_write_test",
                    "report_data_mapping",
                    "report_account",
                    "budget_report_display_item",
                    "driver_account_mapping",
                    "driver_product",
                    "driver_indicator",
                    "driver_category",
                    "control_item_subject_mapping",
                    "forecast_line_binding",
                    "forecast_workbench_layout",
                    "assumption_value",
                    "assumption_rule_template",
                    "assumption_parameter",
                    "scenario_catalog",
                    "chart_template",
                    "smart_report_definition",
                    "pivot_aggregate_rule",
                    "dept_product_mapping",
                    "dept_name_alias",
                    "expense_execution_monthly",
                    "product_budget_component",
                ),
            )
            self.assertIsNotNone(result.backup_path)
            self.assertTrue(result.backup_path and result.backup_path.exists())
            conn = sqlite3.connect(db_path)
            try:
                tables = {
                    str(row[0])
                    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
            finally:
                conn.close()
            self.assertNotIn("_codex_write_test", tables)
            self.assertNotIn("report_data_mapping", tables)
            self.assertNotIn("report_account", tables)
            self.assertNotIn("budget_report_display_item", tables)
            self.assertNotIn("driver_account_mapping", tables)
            self.assertNotIn("driver_product", tables)
            self.assertNotIn("driver_indicator", tables)
            self.assertNotIn("driver_category", tables)
            self.assertNotIn("control_item_subject_mapping", tables)
            self.assertNotIn("forecast_line_binding", tables)
            self.assertNotIn("forecast_workbench_layout", tables)
            self.assertNotIn("assumption_value", tables)
            self.assertNotIn("assumption_rule_template", tables)
            self.assertNotIn("assumption_parameter", tables)
            self.assertNotIn("scenario_catalog", tables)
            self.assertNotIn("chart_template", tables)
            self.assertNotIn("smart_report_definition", tables)
            self.assertNotIn("pivot_aggregate_rule", tables)
            self.assertNotIn("dept_product_mapping", tables)
            self.assertNotIn("dept_name_alias", tables)
            self.assertNotIn("expense_execution_monthly", tables)
            self.assertNotIn("product_budget_component", tables)
            self.assertIn("data_account", tables)
            conn = sqlite3.connect(db_path)
            try:
                sync_keys = {
                    str(row[0])
                    for row in conn.execute("SELECT sync_key FROM expense_sync_meta")
                }
            finally:
                conn.close()
            self.assertNotIn("actual_import", sync_keys)
            self.assertIn("framework_import", sync_keys)


if __name__ == "__main__":
    unittest.main()
