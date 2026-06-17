from __future__ import annotations

import sqlite3
import tempfile
import unittest
import json
from pathlib import Path

from app.db_bootstrap.budget_data import ensure_budget_data_value_contract
from app.db_bootstrap.current_contracts import (
    ensure_runtime_metric_identity_schema,
    ensure_org_product_runtime_catalog_schema,
)
from app.db_bootstrap.generated_paths import validate_generated_file_paths
from app.db_bootstrap.derived_read_models import (
    ensure_budget_read_model_schema,
    ensure_compare_read_model_schema,
)
from app.db_bootstrap.retired_deletion import drop_retired_tables
from app.services.org_product_runtime_catalog import select_org_product_runtime_products_sql


def column_names(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})")]


class DbBootstrapCurrentContractTests(unittest.TestCase):
    def test_runtime_metric_identity_schema_rejects_retired_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  budget_formula TEXT,
                  actual_formula TEXT,
                  budget_rule_code TEXT,
                  budget_rule_config_json TEXT,
                  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
                  formula_calc_mode INTEGER NOT NULL DEFAULT 0 CHECK (formula_calc_mode BETWEEN 0 AND 3),
                  allow_manual_entry INTEGER NOT NULL DEFAULT 1 CHECK (allow_manual_entry IN (0, 1)),
                  value_type TEXT NOT NULL,
                  legacy_product_code TEXT,
                  legacy_dimension TEXT,
                  remark TEXT
                );
                INSERT INTO data_account(
                  data_acct_code, data_acct_name, budget_formula, actual_formula,
                  budget_rule_code, budget_rule_config_json, need_calc,
                  formula_calc_mode, allow_manual_entry, value_type,
                  legacy_product_code, legacy_dimension, remark
                ) VALUES (
                  '01.01.001.A01', '开鑫贷日均余额', '1+1', '',
                  NULL, NULL, 0, 1, 1, '金额',
                  'A01', 'old', 'keep'
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "旧字段/非当前字段"):
                ensure_runtime_metric_identity_schema(conn)
        finally:
            conn.close()

    def test_runtime_metric_identity_schema_accepts_current_contract(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  budget_formula TEXT,
                  actual_formula TEXT,
                  budget_rule_code TEXT,
                  budget_rule_config_json TEXT,
                  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
                  formula_calc_mode INTEGER NOT NULL DEFAULT 0 CHECK (formula_calc_mode BETWEEN 0 AND 3),
                  allow_manual_entry INTEGER NOT NULL DEFAULT 1 CHECK (allow_manual_entry IN (0, 1)),
                  value_type TEXT NOT NULL,
                  remark TEXT
                );
                INSERT INTO data_account(
                  data_acct_code, data_acct_name, budget_formula, actual_formula,
                  budget_rule_code, budget_rule_config_json, need_calc,
                  formula_calc_mode, allow_manual_entry, value_type, remark
                ) VALUES (
                  'A01.01.01.001', '开鑫贷日均余额', '1+1', '',
                  NULL, NULL, 1, 1, 0, '金额', 'keep'
                );
                """
            )

            ensure_runtime_metric_identity_schema(conn)
            self.assertEqual(
                column_names(conn, "data_account"),
                [
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
                ],
            )
        finally:
            conn.close()

    def test_runtime_metric_identity_schema_rejects_stale_formula_mode(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY NOT NULL,
                  data_acct_name TEXT NOT NULL,
                  budget_formula TEXT,
                  actual_formula TEXT,
                  budget_rule_code TEXT,
                  budget_rule_config_json TEXT,
                  need_calc INTEGER NOT NULL DEFAULT 0 CHECK (need_calc IN (0, 1)),
                  formula_calc_mode INTEGER NOT NULL DEFAULT 0 CHECK (formula_calc_mode BETWEEN 0 AND 3),
                  allow_manual_entry INTEGER NOT NULL DEFAULT 1 CHECK (allow_manual_entry IN (0, 1)),
                  value_type TEXT NOT NULL,
                  remark TEXT
                );
                INSERT INTO data_account(
                  data_acct_code, data_acct_name, budget_formula, actual_formula,
                  need_calc, formula_calc_mode, allow_manual_entry, value_type
                ) VALUES (
                  'A01.01.01.001', '开鑫贷日均余额', '1+1', '',
                  0, 0, 1, '金额'
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "公式计算模式"):
                ensure_runtime_metric_identity_schema(conn)
        finally:
            conn.close()

    def test_org_product_runtime_catalog_schema_removes_legacy_product_object(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            payload = {
                "code": "AA",
                "name": "微众银行",
                "children": [
                    {"code": "A", "name": "个金群", "children": [{"code": "A01", "name": "泛微粒贷"}]}
                ],
            }
            conn.executescript(
                """
                CREATE TABLE org_product_tree_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE product_type (
                  product_code TEXT PRIMARY KEY NOT NULL,
                  product_name TEXT NOT NULL,
                  remark TEXT
                );
                INSERT INTO product_type(product_code, product_name)
                VALUES ('OLD', '旧产品');
                """
            )
            conn.execute(
                "INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at) VALUES(1, ?, 'now')",
                (json.dumps(payload, ensure_ascii=False),),
            )

            ensure_org_product_runtime_catalog_schema(conn)

            product_object = conn.execute(
                "SELECT type FROM sqlite_master WHERE name='product_type'"
            ).fetchone()
            rows = conn.execute(
                select_org_product_runtime_products_sql()
            ).fetchall()
            self.assertIsNone(product_object)
            self.assertEqual([tuple(row[:4]) for row in rows], [("AA", "微众银行", None, 1), ("A", "个金群", "AA", 2), ("A01", "泛微粒贷", "A", 3)])
        finally:
            conn.close()

    def test_org_product_runtime_catalog_schema_does_not_create_product_object(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE org_product_tree_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                VALUES(1, '{"code":"AA","name":"微众银行","children":[]}', 'now');
                """
            )

            ensure_org_product_runtime_catalog_schema(conn)

            self.assertIsNone(
                conn.execute("SELECT type FROM sqlite_master WHERE name='product_type'").fetchone()
            )
        finally:
            conn.close()

    def test_org_product_runtime_catalog_schema_reflects_org_product_snapshot_changes(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            first_payload = {"code": "AA", "name": "微众银行", "children": []}
            second_payload = {
                "code": "AA",
                "name": "微众银行",
                "children": [{"code": "B", "name": "企金群", "children": []}],
            }
            conn.executescript(
                """
                CREATE TABLE org_product_tree_snapshot (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                "INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at) VALUES(1, ?, 'first')",
                (json.dumps(first_payload, ensure_ascii=False),),
            )
            ensure_org_product_runtime_catalog_schema(conn)
            self.assertIsNone(
                conn.execute("SELECT type FROM sqlite_master WHERE name='product_type'").fetchone()
            )

            conn.execute(
                """
                UPDATE org_product_tree_snapshot
                SET payload_json = ?, updated_at = 'second'
                WHERE id = 1
                """,
                (json.dumps(second_payload, ensure_ascii=False),),
            )
            rows = conn.execute(
                select_org_product_runtime_products_sql()
            ).fetchall()
            self.assertEqual([tuple(row[:4]) for row in rows], [("AA", "微众银行", None, 1), ("B", "企金群", "AA", 2)])
        finally:
            conn.close()

    def test_budget_data_value_contract_rejects_missing_value_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_data (
                  id INTEGER PRIMARY KEY,
                  value REAL
                );
                INSERT INTO budget_data(id, value) VALUES (1, 123.45);
                """
            )

            with self.assertRaisesRegex(RuntimeError, "缺少当前取值字段"):
                ensure_budget_data_value_contract(conn)
        finally:
            conn.close()

    def test_budget_data_value_contract_accepts_current_value_source(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_data (
                  id INTEGER PRIMARY KEY,
                  data_acct_code TEXT NOT NULL,
                  product_code TEXT NOT NULL,
                  period_id INTEGER NOT NULL,
                  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
                  version_id INTEGER NOT NULL,
                  value REAL NOT NULL DEFAULT 0,
                  formula_value REAL,
                  manual_value REAL,
                  value_source TEXT NOT NULL DEFAULT 'manual'
                    CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
                  need_calc INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO budget_data(
                  data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc
                ) VALUES (
                  'A01.01.01.001', 'A01', 1, 0, 1,
                  123.45, NULL, 123.45, 'manual', 0
                );
                """
            )

            ensure_budget_data_value_contract(conn)
        finally:
            conn.close()

    def test_budget_data_value_contract_rejects_old_value_source_check(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_data (
                  id INTEGER PRIMARY KEY,
                  data_acct_code TEXT NOT NULL,
                  product_code TEXT NOT NULL,
                  period_id INTEGER NOT NULL,
                  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
                  version_id INTEGER NOT NULL,
                  value REAL NOT NULL DEFAULT 0,
                  formula_value REAL,
                  manual_value REAL,
                  value_source TEXT NOT NULL DEFAULT 'manual'
                    CHECK (value_source IN ('manual', 'formula', 'none')),
                  need_calc INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO budget_data(
                  data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc
                ) VALUES (
                  'A01.01.01.001', 'A01', 1, 0, 1,
                  123.45, NULL, 123.45, 'manual', 0
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "value_source 约束"):
                ensure_budget_data_value_contract(conn)
        finally:
            conn.close()

    def test_budget_data_value_contract_rejects_unbackfilled_manual_value(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_data (
                  id INTEGER PRIMARY KEY,
                  data_acct_code TEXT NOT NULL,
                  product_code TEXT NOT NULL,
                  period_id INTEGER NOT NULL,
                  budget_actual INTEGER NOT NULL CHECK (budget_actual IN (0, 1)),
                  version_id INTEGER NOT NULL,
                  value REAL NOT NULL DEFAULT 0,
                  formula_value REAL,
                  manual_value REAL,
                  value_source TEXT NOT NULL DEFAULT 'manual'
                    CHECK (value_source IN ('manual', 'formula', 'none', 'rollup')),
                  need_calc INTEGER NOT NULL DEFAULT 1
                );
                INSERT INTO budget_data(
                  data_acct_code, product_code, period_id, budget_actual, version_id,
                  value, formula_value, manual_value, value_source, need_calc
                ) VALUES (
                  'A01.01.01.001', 'A01', 1, 0, 1,
                  123.45, NULL, NULL, 'manual', 0
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "无效取值来源"):
                ensure_budget_data_value_contract(conn)
        finally:
            conn.close()

    def test_drop_retired_tables_drops_pivot_rule_mirror(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE pivot_aggregate_rule (
                  rule_code TEXT PRIMARY KEY NOT NULL,
                  source_kind TEXT NOT NULL,
                  grain TEXT NOT NULL,
                  dimension_fields_json TEXT NOT NULL,
                  value_rule TEXT NOT NULL,
                  enabled INTEGER NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                INSERT INTO pivot_aggregate_rule
                VALUES ('budget_year', 'budget', 'year', '[]', 'sum', 1, 'now', 'now');
                """
            )

            deleted = drop_retired_tables(conn)

            cur = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pivot_aggregate_rule'"
            )
            self.assertIsNone(cur.fetchone())
            self.assertIn("pivot_aggregate_rule", deleted)
        finally:
            conn.close()

    def test_drop_retired_tables_drops_smart_definition_without_rebuilding_instance(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE smart_report_definition (
                  report_id INTEGER PRIMARY KEY,
                  report_code TEXT NOT NULL
                );
                CREATE TABLE smart_report_instance (
                  instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  report_id INTEGER REFERENCES smart_report_definition(report_id),
                  template_id INTEGER NOT NULL,
                  instance_name TEXT NOT NULL,
                  parameter_values_json TEXT NOT NULL,
                  text_values_json TEXT,
                  data_snapshot_json TEXT,
                  output_file_path TEXT,
                  generation_status TEXT NOT NULL DEFAULT 'pending',
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                """
            )

            deleted = drop_retired_tables(conn)

            cur = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='smart_report_definition'"
            )
            self.assertIsNone(cur.fetchone())
            self.assertIn("report_id", column_names(conn, "smart_report_instance"))
            self.assertIn("smart_report_definition", deleted)
        finally:
            conn.close()

    def test_budget_read_model_schema_rejects_missing_value_source_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_summary (
                  id INTEGER PRIMARY KEY,
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  dept_level1 TEXT,
                  dept_level2 TEXT,
                  dept_level3 TEXT,
                  data_code_name TEXT NOT NULL,
                  product_code_name TEXT,
                  year TEXT NOT NULL,
                  month TEXT NOT NULL,
                  quarter TEXT NOT NULL,
                  budget_actual INTEGER NOT NULL,
                  version_id INTEGER NOT NULL,
                  version_name TEXT,
                  value REAL NOT NULL DEFAULT 0,
                  value_type TEXT NOT NULL,
                  update_time TEXT
                );
                CREATE TABLE budget_pivot_aggregate (
                  id INTEGER PRIMARY KEY,
                  grain TEXT NOT NULL,
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  dept_level1 TEXT,
                  dept_level2 TEXT,
                  dept_level3 TEXT,
                  data_code_name TEXT NOT NULL,
                  product_code_name TEXT,
                  year TEXT NOT NULL,
                  month TEXT NOT NULL,
                  quarter TEXT NOT NULL,
                  budget_actual INTEGER NOT NULL,
                  version_id INTEGER NOT NULL,
                  version_name TEXT,
                  value REAL NOT NULL DEFAULT 0,
                  value_type TEXT NOT NULL,
                  update_time TEXT NOT NULL
                );
                """
            )

            with self.assertRaises(RuntimeError) as raised:
                ensure_budget_read_model_schema(conn)
            self.assertIn("budget_summary", str(raised.exception))
            self.assertIn("value_source", str(raised.exception))
            self.assertIn("不再自动迁移", str(raised.exception))
        finally:
            conn.close()

    def test_budget_read_model_schema_rejects_retired_report_level_columns(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE budget_summary (
                  id INTEGER PRIMARY KEY,
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  report_level1 TEXT,
                  report_level2 TEXT,
                  data_code_name TEXT NOT NULL
                );
                """
            )

            with self.assertRaisesRegex(RuntimeError, "report_level"):
                ensure_budget_read_model_schema(conn)
        finally:
            conn.close()

    def test_compare_read_model_schema_creates_pivot_and_current_value_source(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            conn.executescript(
                """
                CREATE TABLE compare_budget_summary (
                  id INTEGER PRIMARY KEY,
                  show_level INTEGER NOT NULL,
                  data_file_id INTEGER NOT NULL,
                  source_year INTEGER NOT NULL,
                  source_version_id INTEGER NOT NULL,
                  source_version_name TEXT,
                  metric_level1 TEXT,
                  metric_level2 TEXT,
                  metric_level3 TEXT,
                  metric_level4 TEXT,
                  metric_level5 TEXT,
                  dept_level1 TEXT,
                  dept_level2 TEXT,
                  dept_level3 TEXT,
                  data_code_name TEXT NOT NULL,
                  product_code_name TEXT,
                  year TEXT NOT NULL,
                  month TEXT NOT NULL,
                  quarter TEXT NOT NULL,
                  budget_actual INTEGER NOT NULL,
                  value REAL NOT NULL DEFAULT 0,
                  value_type TEXT NOT NULL,
                  value_source TEXT NOT NULL DEFAULT 'manual',
                  sync_time TEXT NOT NULL
                );
                """
            )

            ensure_compare_read_model_schema(conn)

            self.assertIn("value_source", column_names(conn, "compare_budget_summary"))
            self.assertIn("compare_pivot_aggregate", [
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            ])
            self.assertIn("value_source", column_names(conn, "compare_pivot_aggregate"))
        finally:
            conn.close()

    def test_generated_file_paths_reject_old_repo_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            template_dir = data_dir / "smart_report_templates"
            output_dir = data_dir / "smart_report_outputs"
            template_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            (template_dir / "report_v1.docx").write_bytes(b"template")
            (output_dir / "smart_report_1.docx").write_bytes(b"report")
            (output_dir / "smart_ppt_1.pptx").write_bytes(b"ppt")

            conn = sqlite3.connect(":memory:")
            try:
                conn.executescript(
                    """
                    CREATE TABLE smart_report_template (
                      template_id INTEGER PRIMARY KEY,
                      file_path TEXT NOT NULL
                    );
                    CREATE TABLE smart_report_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    CREATE TABLE smart_ppt_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    INSERT INTO smart_report_template VALUES
                      (1, '/old/root/data/smart_report_templates/report_v1.docx');
                    INSERT INTO smart_report_instance VALUES
                      (1, '/old/root/data/smart_report_outputs/smart_report_1.docx');
                    INSERT INTO smart_ppt_instance VALUES
                      (1, 'smart_report_outputs/smart_ppt_1.pptx');
                    """
                )

                with self.assertRaises(RuntimeError) as raised:
                    validate_generated_file_paths(conn, data_dir)
                self.assertIn("Smart Report/PPT", str(raised.exception))
                self.assertIn("不再自动迁移", str(raised.exception))

                template_path = conn.execute(
                    "SELECT file_path FROM smart_report_template WHERE template_id = 1"
                ).fetchone()[0]
                self.assertEqual(
                    template_path,
                    "/old/root/data/smart_report_templates/report_v1.docx",
                )
            finally:
                conn.close()

    def test_generated_file_paths_accept_current_data_dir_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            template_dir = data_dir / "smart_report_templates"
            output_dir = data_dir / "smart_report_outputs"
            template_dir.mkdir(parents=True)
            output_dir.mkdir(parents=True)
            template_path = template_dir / "report_v1.docx"
            report_path = output_dir / "smart_report_1.docx"
            ppt_path = output_dir / "smart_ppt_1.pptx"
            template_path.write_bytes(b"template")
            report_path.write_bytes(b"report")
            ppt_path.write_bytes(b"ppt")

            conn = sqlite3.connect(":memory:")
            try:
                conn.executescript(
                    """
                    CREATE TABLE smart_report_template (
                      template_id INTEGER PRIMARY KEY,
                      file_path TEXT NOT NULL
                    );
                    CREATE TABLE smart_report_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    CREATE TABLE smart_ppt_instance (
                      instance_id INTEGER PRIMARY KEY,
                      output_file_path TEXT
                    );
                    """
                )
                conn.execute(
                    "INSERT INTO smart_report_template VALUES (1, ?)",
                    (str(template_path),),
                )
                conn.execute(
                    "INSERT INTO smart_report_instance VALUES (1, ?)",
                    (str(report_path),),
                )
                conn.execute(
                    "INSERT INTO smart_ppt_instance VALUES (1, ?)",
                    (str(ppt_path),),
                )

                validate_generated_file_paths(conn, data_dir)
            finally:
                conn.close()

if __name__ == "__main__":
    unittest.main()
