from __future__ import annotations

import asyncio
import unittest
import sqlite3
import tempfile
from pathlib import Path

import aiosqlite

from app.db_bootstrap.business_cost_income import (
    ensure_business_cost_income_schema,
    ensure_business_cost_income_schema_async,
)
from app.db_bootstrap.budget_version import ensure_budget_version_schema_sync
from app.db_bootstrap.runtime_metric_tree import (
    ensure_budget_data_uses_current_metric_identity,
    ensure_runtime_metric_identity_tables,
)
from app.db_bootstrap.expense import (
    BI_AI_SUBJECT_MAPPING_SCHEMA,
    BI_MAPPING_SCHEMA,
    EXPENSE_ACTUAL_IMPORT_SCHEMA,
    EXPENSE_FORECAST_SCHEMA,
    ensure_bi_ai_subject_mapping_schema_sync,
    ensure_bi_mapping_schema_sync,
    ensure_department_expense_master_schema_sync,
    ensure_expense_actual_import_schema_sync,
    ensure_expense_forecast_schema,
    ensure_expense_forecast_schema_sync,
)
from app.db_bootstrap.derived_read_models import (
    ensure_budget_read_model_schema,
    ensure_budget_summary_read_model_schema_async,
    ensure_compare_read_model_schema,
)
from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema_sync
from app.db_bootstrap.schemas import BUDGET_SCHEMA, COMMON_SCHEMA, COMPARE_SCHEMA
from app.db_bootstrap.smart_report import ensure_smart_report_schema_sync


def column_names(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")]


class DbBootstrapSchemaTests(unittest.TestCase):
    def test_init_db_imports_current_schema_constants(self) -> None:
        init_db_source = (Path(__file__).resolve().parent / "app" / "init_db.py").read_text()
        self.assertIn(
            "from app.db_bootstrap.schemas import BUDGET_SCHEMA, COMMON_SCHEMA, COMPARE_SCHEMA",
            init_db_source,
        )

    def test_schema_modules_keep_core_tables_visible(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS data_account", COMMON_SCHEMA)
        self.assertIn("CREATE TABLE IF NOT EXISTS budget_output_display_item", COMMON_SCHEMA)
        self.assertIn("CREATE TABLE IF NOT EXISTS budget_data", BUDGET_SCHEMA)
        self.assertIn("CREATE TABLE IF NOT EXISTS business_cost_income_item", BUDGET_SCHEMA)
        self.assertIn("CREATE TABLE IF NOT EXISTS compare_budget_summary", COMPARE_SCHEMA)

    def test_read_model_schemas_use_current_metric_level_names_only(self) -> None:
        self.assertIn("metric_level1", BUDGET_SCHEMA)
        self.assertIn("metric_level1", COMPARE_SCHEMA)
        self.assertNotIn("report_level", BUDGET_SCHEMA)
        self.assertNotIn("report_level", COMPARE_SCHEMA)

    def test_budget_version_schema_accepts_current_budget_schema(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(BUDGET_SCHEMA)
            ensure_budget_version_schema_sync(conn)
        finally:
            conn.close()

    def test_budget_version_schema_rejects_missing_current_month(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE version (
                  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  version_date_time TEXT NOT NULL,
                  version_name TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_version_schema_sync(conn)
            self.assertIn("current_month", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_budget_version_schema_rejects_invalid_current_month(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE version (
                  version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  version_date_time TEXT NOT NULL,
                  version_name TEXT NOT NULL,
                  current_month INTEGER
                );
                INSERT INTO version(version_date_time, version_name, current_month)
                VALUES ('2026-06-01T00:00:00Z', 'V1', 14);
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_version_schema_sync(conn)
            self.assertIn("current_month", str(raised.exception))
            self.assertIn("不再自动修正", str(raised.exception))
        finally:
            conn.close()

    def test_runtime_paths_do_not_default_missing_current_month(self) -> None:
        init_db_source = (Path(__file__).resolve().parent / "app" / "init_db.py").read_text()
        system_admin_source = (
            Path(__file__).resolve().parent / "app" / "routers" / "system_admin.py"
        ).read_text()
        system_versions_source = (
            Path(__file__).resolve().parent / "app" / "services" / "system_versions.py"
        ).read_text()
        main_source = (Path(__file__).resolve().parent / "app" / "main.py").read_text()
        self.assertIn("ensure_budget_version_schema_sync", init_db_source)
        self.assertIn("ensure_budget_version_schema", system_versions_source)
        self.assertNotIn("ADD COLUMN current_month", init_db_source)
        self.assertNotIn("1 AS current_month", system_admin_source)
        self.assertNotIn("1 AS current_month", system_versions_source)
        self.assertNotIn("1 AS current_month", main_source)

    def test_async_read_model_schema_rejects_retired_level_columns(self) -> None:
        async def run() -> None:
            async with aiosqlite.connect(":memory:") as conn:
                await conn.executescript(
                    """
                    CREATE TABLE budget_summary (
                      metric_level1 TEXT,
                      metric_level2 TEXT,
                      metric_level3 TEXT,
                      metric_level4 TEXT,
                      metric_level5 TEXT,
                      report_level1 TEXT,
                      data_code_name TEXT NOT NULL
                    );
                    """
                )
                with self.assertRaisesRegex(RuntimeError, "report_level1"):
                    await ensure_budget_summary_read_model_schema_async(conn)

        asyncio.run(run())

    def test_budget_read_model_schema_rejects_missing_value_source(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE budget_summary (
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  data_code_name TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_read_model_schema(conn)
            self.assertIn("budget_summary", str(raised.exception))
            self.assertIn("value_source", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_compare_read_model_schema_rejects_missing_value_source(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE compare_budget_summary (
                  show_level INTEGER NOT NULL,
                  data_file_id INTEGER NOT NULL,
                  source_year INTEGER NOT NULL,
                  source_version_id INTEGER NOT NULL,
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  data_code_name TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_compare_read_model_schema(conn)
            self.assertIn("compare_budget_summary", str(raised.exception))
            self.assertIn("value_source", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_async_read_model_schema_rejects_missing_value_source(self) -> None:
        async def run() -> None:
            async with aiosqlite.connect(":memory:") as conn:
                await conn.executescript(
                    """
                    CREATE TABLE budget_summary (
                      metric_level1 TEXT,
                      metric_level2 TEXT,
                      metric_level3 TEXT,
                      metric_level4 TEXT,
                      metric_level5 TEXT,
                      data_code_name TEXT NOT NULL
                    );
                    """
                )
                with self.assertRaises(RuntimeError) as raised:
                    await ensure_budget_summary_read_model_schema_async(conn)
                self.assertIn("budget_summary", str(raised.exception))
                self.assertIn("value_source", str(raised.exception))
                self.assertIn("不再自动迁移", str(raised.exception))

        asyncio.run(run())

    def test_common_schema_does_not_recreate_retired_pivot_rule_table(self) -> None:
        self.assertNotIn("pivot_aggregate_rule", COMMON_SCHEMA)
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'pivot_aggregate_rule'"
            )
            self.assertIsNone(cur.fetchone())
        finally:
            conn.close()

    def test_common_schema_creates_budget_output_display_item(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'budget_output_display_item'"
            )
            self.assertIsNotNone(cur.fetchone())
        finally:
            conn.close()

    def test_report_display_sync_bootstrap_creates_only_current_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL
                )
                """
            )

            ensure_budget_output_display_item_schema_sync(conn)

            tables = {
                str(row[0])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            self.assertIn("budget_output_display_item", tables)
            self.assertNotIn("budget_report_display_item", tables)
            cols = column_names(conn, "budget_output_display_item")
            self.assertIn("display_view", cols)
            self.assertIn("org_product_ref", cols)
            self.assertIn("org_product_entity_code", cols)
            self.assertIn("org_product_table_name", cols)
            self.assertIn("org_product_metric_code", cols)
            self.assertIn("org_product_metric_name", cols)
            self.assertNotIn("report_view", cols)
        finally:
            conn.close()

    def test_smart_report_schema_accepts_current_common_schema(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            ensure_smart_report_schema_sync(conn)
        finally:
            conn.close()

    def test_smart_report_schema_rejects_missing_text_values(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE smart_report_instance")
            conn.execute(
                """
                CREATE TABLE smart_report_instance (
                  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
                  instance_name TEXT NOT NULL,
                  parameter_values_json TEXT NOT NULL,
                  data_snapshot_json TEXT,
                  output_file_path TEXT,
                  generation_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
                  error_message TEXT,
                  last_generated_at TEXT,
                  last_refresh_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_smart_report_schema_sync(conn)
            self.assertIn("smart_report_instance", str(raised.exception))
            self.assertIn("text_values_json", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_smart_report_schema_rejects_retired_report_id(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE smart_report_instance")
            conn.execute(
                """
                CREATE TABLE smart_report_instance (
                  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  report_id INTEGER,
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id),
                  instance_name TEXT NOT NULL,
                  parameter_values_json TEXT NOT NULL,
                  text_values_json TEXT,
                  data_snapshot_json TEXT,
                  output_file_path TEXT,
                  generation_status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (generation_status IN ('pending', 'running', 'success', 'failed')),
                  error_message TEXT,
                  last_generated_at TEXT,
                  last_refresh_at TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_smart_report_schema_sync(conn)
            self.assertIn("smart_report_instance", str(raised.exception))
            self.assertIn("report_id", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_smart_report_schema_rejects_old_template_type_check(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE smart_report_template")
            conn.execute(
                """
                CREATE TABLE smart_report_template (
                  template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_code TEXT NOT NULL UNIQUE,
                  template_name TEXT NOT NULL,
                  template_type TEXT NOT NULL DEFAULT 'analysis'
                    CHECK (template_type IN ('analysis', 'report', 'summary')),
                  file_path TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'archived')),
                  version_no INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_by TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_smart_report_schema_sync(conn)
            self.assertIn("smart_report_template", str(raised.exception))
            self.assertIn("ppt", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_smart_report_schema_rejects_old_variable_type_check(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("DROP TABLE smart_report_template_variable")
            conn.execute(
                """
                CREATE TABLE smart_report_template_variable (
                  variable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_id INTEGER NOT NULL REFERENCES smart_report_template(template_id) ON DELETE CASCADE,
                  variable_key TEXT NOT NULL,
                  variable_name TEXT NOT NULL,
                  variable_type TEXT NOT NULL
                    CHECK (variable_type IN ('metric', 'parameter', 'text', 'table', 'chart', 'analysis')),
                  binding_config_json TEXT,
                  display_order INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE (template_id, variable_key)
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_smart_report_schema_sync(conn)
            self.assertIn("smart_report_template_variable", str(raised.exception))
            self.assertIn("formula", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_init_db_does_not_rebuild_old_smart_report_tables(self) -> None:
        init_db_source = (Path(__file__).resolve().parent / "app" / "init_db.py").read_text()
        contract_source = (
            Path(__file__).resolve().parent / "app" / "db_bootstrap" / "current_contracts.py"
        ).read_text()
        self.assertIn("ensure_smart_report_schema_sync", init_db_source)
        self.assertNotIn("ALTER TABLE smart_report_instance ADD COLUMN text_values_json", init_db_source)
        self.assertNotIn("smart_report_template_new", init_db_source)
        self.assertNotIn("smart_report_template_variable_new", init_db_source)
        self.assertNotIn("smart_report_instance__without_definition", contract_source)

    def test_metric_binding_schema_accepts_product_prefixed_identity(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)

            ensure_runtime_metric_identity_tables(conn)

            self.assertIn("product_code", column_names(conn, "data_account_metric_node"))
            self.assertIn("local_metric_code", column_names(conn, "data_account_metric_node"))
            self.assertIn("functional_group_code", column_names(conn, "data_account_metric_node"))
            self.assertIn("metric_table_name", column_names(conn, "data_account_metric_node"))
            conn.execute(
                """
                INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                VALUES ('A01.01.01.001', '开鑫贷日均余额', '金额')
                """
            )
            conn.execute(
                """
                INSERT INTO data_account_metric_node(
                  node_code, node_name, parent_code, product_code, local_metric_code,
                  level, node_type
                ) VALUES ('A01.01.01.001', '开鑫贷日均余额', NULL, 'A01', '01.01.001', 4, 'METRIC')
                """
            )
            conn.execute(
                """
                INSERT INTO data_account_metric_binding(
                  data_acct_code, metric_node_code, scope_type, scope_code
                ) VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01')
                """
            )
            row = conn.execute("SELECT data_acct_code, scope_code FROM data_account_metric_binding").fetchone()
            self.assertEqual(row, ("A01.01.01.001", "A01"))
        finally:
            conn.close()

    def test_metric_tree_bootstrap_rejects_missing_current_metric_node_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE data_account_metric_node (
                  node_code TEXT PRIMARY KEY NOT NULL,
                  node_name TEXT NOT NULL,
                  parent_code TEXT,
                  level INTEGER NOT NULL,
                  node_type TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE data_account_metric_binding (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  metric_node_code TEXT NOT NULL,
                  scope_type TEXT NOT NULL,
                  scope_code TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "指标树表缺少当前字段"):
                ensure_runtime_metric_identity_tables(conn)
        finally:
            conn.close()

    def test_metric_tree_bootstrap_rejects_old_binding_constraint(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("DROP TABLE data_account_metric_binding")
            conn.execute(
                """
                CREATE TABLE data_account_metric_binding (
                  data_acct_code TEXT PRIMARY KEY NOT NULL REFERENCES data_account(data_acct_code),
                  metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
                  scope_type TEXT NOT NULL CHECK (scope_type IN ('PRODUCT', 'CORP')),
                  scope_code TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                  remark TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE (metric_node_code, scope_code),
                  CHECK (data_acct_code = metric_node_code || '.' || scope_code)
                )
                """
            )

            with self.assertRaisesRegex(RuntimeError, "兼容指标绑定表缺少当前约束"):
                ensure_runtime_metric_identity_tables(conn)
        finally:
            conn.close()

    def test_metric_tree_bootstrap_rejects_auto_derived_field_drift(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute(
                """
                INSERT INTO data_account_metric_node(
                  node_code, node_name, parent_code, product_code, local_metric_code,
                  level, node_type
                ) VALUES ('A01.01.01.001', '开鑫贷日均余额', NULL, 'A02', '01.01.001', 4, 'METRIC')
                """
            )

            with self.assertRaisesRegex(RuntimeError, "派生字段或汇总方式不符合当前合同"):
                ensure_runtime_metric_identity_tables(conn)
        finally:
            conn.close()

    def test_metric_binding_schema_rejects_retired_metric_scope_identity(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT '金额'
                );
                CREATE TABLE data_account_metric_node (
                  node_code TEXT PRIMARY KEY NOT NULL,
                  node_name TEXT NOT NULL,
                  parent_code TEXT,
                  level INTEGER NOT NULL,
                  node_type TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE data_account_metric_binding (
                  data_acct_code TEXT PRIMARY KEY NOT NULL REFERENCES data_account(data_acct_code),
                  metric_node_code TEXT NOT NULL REFERENCES data_account_metric_node(node_code),
                  scope_type TEXT NOT NULL,
                  scope_code TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  is_active INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  UNIQUE (metric_node_code, scope_code),
                  CHECK (data_acct_code = metric_node_code || '.' || scope_code)
                );
                INSERT INTO data_account(data_acct_code, data_acct_name)
                VALUES ('01.01.001.A01', '旧开鑫贷日均余额');
                INSERT INTO data_account_metric_node(node_code, node_name, level, node_type)
                VALUES ('01.01.001', '旧日均余额', 3, 'METRIC');
                INSERT INTO data_account_metric_binding(
                  data_acct_code, metric_node_code, scope_type, scope_code
                ) VALUES ('01.01.001.A01', '01.01.001', 'PRODUCT', 'A01');
                """
            )

            with self.assertRaisesRegex(RuntimeError, "指标树表缺少当前字段"):
                ensure_runtime_metric_identity_tables(conn)
        finally:
            conn.close()

    def test_metric_tree_bootstrap_does_not_seed_from_data_account_rows(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE product_type (
                  product_code TEXT PRIMARY KEY NOT NULL,
                  product_name TEXT NOT NULL
                );
                INSERT INTO product_type(product_code, product_name)
                VALUES ('A01', '开鑫贷');
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT '金额'
                );
                INSERT INTO data_account(data_acct_code, data_acct_name)
                VALUES ('A01.01.01.001', '开鑫贷日均余额');
                """
            )

            ensure_runtime_metric_identity_tables(conn)

            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM data_account_metric_node").fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM data_account_metric_binding").fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_metric_tree_bootstrap_rejects_retired_data_account_code_shape(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT '金额'
                );
                INSERT INTO data_account(data_acct_code, data_acct_name)
                VALUES ('01.01.001.A01', '旧开鑫贷日均余额');
                """
            )

            with self.assertRaises(RuntimeError) as raised:
                ensure_runtime_metric_identity_tables(conn)
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_budget_fact_validation_rejects_retired_data_account_code_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget_2026.db"
            conn = sqlite3.connect(path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE budget_data (
                      data_acct_code TEXT NOT NULL,
                      product_code TEXT NOT NULL
                    );
                    INSERT INTO budget_data(data_acct_code, product_code)
                    VALUES ('01.01.001.A01', 'A01');
                    """
                )
                conn.commit()
            finally:
                conn.close()

            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_data_uses_current_metric_identity(path)
            self.assertIn("不再自动迁移", str(raised.exception))

    def test_expense_schema_fragments_create_private_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY);
                """
            )
            conn.executescript(EXPENSE_FORECAST_SCHEMA)
            conn.executescript(BI_MAPPING_SCHEMA)
            conn.executescript(BI_AI_SUBJECT_MAPPING_SCHEMA)
            conn.executescript(EXPENSE_ACTUAL_IMPORT_SCHEMA)
            for table_name in (
                "expense_forecast_entry",
                "expense_forecast_rule",
                "expense_forecast_calc_result",
                "expense_actual_detail_raw",
                "bi_ai_subject_mapping",
                "manage_dept_owner_mapping",
            ):
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                )
                self.assertIsNotNone(cur.fetchone())
        finally:
            conn.close()

    def test_bi_ai_subject_mapping_schema_rejects_legacy_contract(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE bi_ai_subject_mapping (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  level6_code TEXT NOT NULL,
                  level6_name TEXT NOT NULL,
                  budget_subject TEXT NOT NULL
                )
                """
            )

            with self.assertRaises(RuntimeError) as raised:
                ensure_bi_ai_subject_mapping_schema_sync(conn)
            self.assertIn("BI-AI科目映射表", str(raised.exception))
            self.assertIn("fee_major", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_department_expense_master_schema_accepts_current_common_schema(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            ensure_department_expense_master_schema_sync(conn)
        finally:
            conn.close()

    def test_department_expense_master_schema_rejects_legacy_dept_account(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE dept_account")
            conn.execute(
                """
                CREATE TABLE dept_account (
                  dept_code TEXT PRIMARY KEY NOT NULL,
                  dept_name TEXT NOT NULL,
                  parent_code TEXT,
                  level INTEGER NOT NULL,
                  is_leaf INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_department_expense_master_schema_sync(conn)
            self.assertIn("dept_account", str(raised.exception))
            self.assertIn("entity_name", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_department_expense_master_schema_rejects_legacy_budget_subject_catalog(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DROP TABLE budget_subject_catalog")
            conn.execute(
                """
                CREATE TABLE budget_subject_catalog (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  parent_id INTEGER,
                  level_number INTEGER NOT NULL,
                  subject_name TEXT NOT NULL,
                  formula_text TEXT,
                  sort_order INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_department_expense_master_schema_sync(conn)
            self.assertIn("budget_subject_catalog", str(raised.exception))
            self.assertIn("manage_department", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_department_expense_master_schema_rejects_legacy_framework_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(COMMON_SCHEMA)
            conn.execute("DROP TABLE expense_framework_budget_department")
            conn.execute(
                """
                CREATE TABLE expense_framework_budget_department (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  group_name TEXT NOT NULL,
                  owner_name TEXT NOT NULL,
                  budget_department TEXT NOT NULL,
                  UNIQUE (group_name, owner_name, budget_department)
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_department_expense_master_schema_sync(conn)
            self.assertIn("expense_framework_budget_department", str(raised.exception))
            self.assertIn("entity_name", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_expense_actual_import_schema_rejects_legacy_raw_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE expense_actual_import_batch (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  file_name TEXT NOT NULL,
                  import_mode TEXT NOT NULL,
                  periods_text TEXT,
                  total_rows INTEGER NOT NULL DEFAULT 0,
                  matched_owner_rows INTEGER NOT NULL DEFAULT 0,
                  matched_subject_rows INTEGER NOT NULL DEFAULT 0,
                  unmatched_rows INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  note TEXT
                );
                CREATE TABLE expense_actual_detail_raw (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  batch_id INTEGER REFERENCES expense_actual_import_batch(id) ON DELETE SET NULL,
                  period_ym TEXT NOT NULL,
                  period_text TEXT,
                  org_code TEXT,
                  org_name TEXT,
                  dep_code TEXT,
                  dep_name TEXT,
                  subject_code TEXT,
                  subject_name TEXT,
                  amount REAL NOT NULL DEFAULT 0,
                  fee_type_code TEXT,
                  fee_type_name TEXT,
                  bi_ai_source_code TEXT,
                  bi_ai_source_name TEXT,
                  manage_department_code TEXT,
                  owner_name_raw TEXT,
                  owner_name_mapped TEXT,
                  monthly_caliber TEXT,
                  budget_subject_raw TEXT,
                  budget_subject_mapped TEXT,
                  owner_matched INTEGER NOT NULL DEFAULT 0 CHECK (owner_matched IN (0, 1)),
                  subject_matched INTEGER NOT NULL DEFAULT 0 CHECK (subject_matched IN (0, 1)),
                  match_note TEXT
                );
                """
            )

            with self.assertRaises(RuntimeError) as raised:
                ensure_expense_actual_import_schema_sync(conn)
            self.assertIn("费用执行明细导入表", str(raised.exception))
            self.assertIn("import_kind", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_expense_actual_import_schema_accepts_current_raw_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            ensure_expense_actual_import_schema_sync(conn)
            self.assertIn("import_kind", column_names(conn, "expense_actual_import_batch"))
            self.assertIn("import_kind", column_names(conn, "expense_actual_detail_raw"))
            self.assertIn("fee_major_mapped", column_names(conn, "expense_actual_detail_raw"))
        finally:
            conn.close()

    def test_budget_subject_catalog_service_does_not_repair_legacy_schema(self) -> None:
        router_source = (
            Path(__file__).resolve().parent / "app" / "routers" / "budget_subject_catalog.py"
        ).read_text()
        service_source = (
            Path(__file__).resolve().parent / "app" / "services" / "budget_subject_catalog.py"
        ).read_text()
        self.assertIn("ensure_department_expense_master_schema", service_source)
        self.assertNotIn("ALTER TABLE budget_subject_catalog", router_source)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS budget_subject_catalog", router_source)
        self.assertNotIn("ALTER TABLE budget_subject_catalog", service_source)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS budget_subject_catalog", service_source)

    def test_expense_schema_rejects_old_driver_rule_contract(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "common.db"
                async with aiosqlite.connect(path) as db:
                    await db.execute("PRAGMA foreign_keys = ON")
                    await db.executescript(
                        """
                        CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY);
                        INSERT INTO budget_subject_catalog(id) VALUES (1);
                        CREATE TABLE expense_forecast_rule (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          forecast_year INTEGER NOT NULL,
                          forecast_version TEXT NOT NULL,
                          owner_name TEXT NOT NULL,
                          subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
                          scheme_code TEXT NOT NULL CHECK (scheme_code IN ('MANUAL', 'RESIDUAL_ALLOC', 'DRIVER_EXPR')),
                          enabled INTEGER NOT NULL DEFAULT 1,
                          allow_manual_override INTEGER NOT NULL DEFAULT 0,
                          auto_refresh_enabled INTEGER NOT NULL DEFAULT 1,
                          manual_recalc_enabled INTEGER NOT NULL DEFAULT 1,
                          driver_source_priority TEXT NOT NULL DEFAULT 'driver_first'
                            CHECK (driver_source_priority IN ('driver_first', 'inline_first')),
                          effective_from_month INTEGER NOT NULL DEFAULT 1 CHECK (effective_from_month BETWEEN 1 AND 12),
                          effective_to_month INTEGER NOT NULL DEFAULT 12 CHECK (effective_to_month BETWEEN 1 AND 12),
                          priority INTEGER NOT NULL DEFAULT 100,
                          remark TEXT,
                          created_at TEXT NOT NULL,
                          updated_at TEXT NOT NULL,
                          UNIQUE (forecast_year, forecast_version, owner_name, subject_id)
                        );
                        CREATE TABLE expense_forecast_rule_param (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          rule_id INTEGER NOT NULL REFERENCES expense_forecast_rule(id) ON DELETE CASCADE,
                          param_group TEXT NOT NULL DEFAULT 'common',
                          param_key TEXT NOT NULL,
                          param_value TEXT,
                          value_type TEXT NOT NULL DEFAULT 'string',
                          UNIQUE (rule_id, param_group, param_key)
                        );
                        CREATE TABLE expense_forecast_rule_variable (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          rule_id INTEGER NOT NULL REFERENCES expense_forecast_rule(id) ON DELETE CASCADE,
                          variable_code TEXT NOT NULL,
                          variable_name TEXT,
                          source_type TEXT NOT NULL CHECK (
                            source_type IN ('driver_module', 'forecast_inline', 'actual', 'annual_field', 'constant')
                          ),
                          source_key TEXT,
                          source_subkey TEXT,
                          default_value REAL,
                          sort_order INTEGER NOT NULL DEFAULT 0
                        );
                        INSERT INTO expense_forecast_rule(
                          id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                          driver_source_priority, created_at, updated_at
                        ) VALUES (10, 2026, '260531v1', '科技业务', 1, 'DRIVER_EXPR',
                                  'driver_first', '2026-05-31T00:00:00Z', '2026-05-31T00:00:00Z');
                        INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                        VALUES (10, 'driver', 'expression', 'base_amount', 'string');
                        INSERT INTO expense_forecast_rule_variable(rule_id, variable_code, source_type, source_key, sort_order)
                        VALUES (10, 'base_amount', 'driver_module', 'A01.01.01.001', 1);
                        """
                    )
                    await ensure_expense_forecast_schema(db)

        with self.assertRaises(RuntimeError) as raised:
            asyncio.run(run())
        self.assertIn("不再自动迁移", str(raised.exception))

    def test_expense_schema_sync_adapter_rejects_old_driver_rule_contract(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE budget_subject_catalog (id INTEGER PRIMARY KEY);
                INSERT INTO budget_subject_catalog(id) VALUES (1);
                CREATE TABLE expense_forecast_rule (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  forecast_year INTEGER NOT NULL,
                  forecast_version TEXT NOT NULL,
                  owner_name TEXT NOT NULL,
                  subject_id INTEGER NOT NULL REFERENCES budget_subject_catalog(id) ON DELETE CASCADE,
                  scheme_code TEXT NOT NULL CHECK (scheme_code IN ('MANUAL', 'RESIDUAL_ALLOC', 'DRIVER_EXPR')),
                  enabled INTEGER NOT NULL DEFAULT 1,
                  allow_manual_override INTEGER NOT NULL DEFAULT 0,
                  auto_refresh_enabled INTEGER NOT NULL DEFAULT 1,
                  manual_recalc_enabled INTEGER NOT NULL DEFAULT 1,
                  driver_source_priority TEXT NOT NULL DEFAULT 'driver_first'
                    CHECK (driver_source_priority IN ('driver_first', 'inline_first')),
                  effective_from_month INTEGER NOT NULL DEFAULT 1 CHECK (effective_from_month BETWEEN 1 AND 12),
                  effective_to_month INTEGER NOT NULL DEFAULT 12 CHECK (effective_to_month BETWEEN 1 AND 12),
                  priority INTEGER NOT NULL DEFAULT 100,
                  remark TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE (forecast_year, forecast_version, owner_name, subject_id)
                );
                CREATE TABLE expense_forecast_rule_param (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  rule_id INTEGER NOT NULL REFERENCES expense_forecast_rule(id) ON DELETE CASCADE,
                  param_group TEXT NOT NULL DEFAULT 'common',
                  param_key TEXT NOT NULL,
                  param_value TEXT,
                  value_type TEXT NOT NULL DEFAULT 'string',
                  UNIQUE (rule_id, param_group, param_key)
                );
                INSERT INTO expense_forecast_rule(
                  id, forecast_year, forecast_version, owner_name, subject_id, scheme_code,
                  driver_source_priority, created_at, updated_at
                ) VALUES (10, 2026, '260531v1', '科技业务', 1, 'DRIVER_EXPR',
                          'driver_first', '2026-05-31T00:00:00Z', '2026-05-31T00:00:00Z');
                INSERT INTO expense_forecast_rule_param(rule_id, param_group, param_key, param_value, value_type)
                VALUES (10, 'driver', 'expression', 'base_amount', 'string');
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_expense_forecast_schema_sync(conn)
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_business_cost_income_schema_fragment_creates_current_private_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            ensure_business_cost_income_schema(conn)
            for table_name in (
                "business_cost_income_item",
                "business_cost_income_indicator",
                "business_cost_income_value",
            ):
                cur = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (table_name,),
                )
                self.assertIsNotNone(cur.fetchone())
            self.assertIn("parent_id", column_names(conn, "business_cost_income_item"))
        finally:
            conn.close()

    def test_business_cost_income_schema_rejects_legacy_item_table(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(
                """
                CREATE TABLE business_cost_income_item (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  section TEXT NOT NULL CHECK (section IN ('input', 'output')),
                  name TEXT NOT NULL,
                  sort_order INTEGER NOT NULL DEFAULT 0,
                  enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                  UNIQUE (section, name)
                )
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_business_cost_income_schema(conn)
            self.assertIn("business_cost_income_item", str(raised.exception))
            self.assertIn("parent_id", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_business_cost_income_async_adapter_rejects_legacy_item_table(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "budget.db"
                async with aiosqlite.connect(path) as db:
                    await db.execute(
                        """
                        CREATE TABLE business_cost_income_item (
                          id INTEGER PRIMARY KEY AUTOINCREMENT,
                          section TEXT NOT NULL CHECK (section IN ('input', 'output')),
                          name TEXT NOT NULL,
                          sort_order INTEGER NOT NULL DEFAULT 0,
                          enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                          UNIQUE (section, name)
                        )
                        """
                    )
                    with self.assertRaises(RuntimeError) as raised:
                        await ensure_business_cost_income_schema_async(db)
                    self.assertIn("business_cost_income_item", str(raised.exception))
                    self.assertIn("parent_id", str(raised.exception))
                    self.assertIn("不再自动迁移", str(raised.exception))

        asyncio.run(run())

    def test_bi_mapping_schema_sync_rejects_missing_unique_constraint(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE manage_dept_owner_mapping (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  manage_department TEXT NOT NULL,
                  owner_department TEXT NOT NULL
                );
                """
            )
            with self.assertRaises(RuntimeError) as raised:
                ensure_bi_mapping_schema_sync(conn)
            self.assertIn("唯一约束", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
