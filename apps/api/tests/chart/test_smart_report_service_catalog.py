from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.schemas import (
    SmartReportCalcMetricComponent,
    SmartReportCalcMetricUpsert,
    SmartReportTemplateVariableUpsert,
)
from app.services.smart_report_service import SmartReportService


class SmartReportServiceCatalogTests(unittest.IsolatedAsyncioTestCase):
    def _build_common_db(self, common_path: Path) -> None:
        with sqlite3.connect(common_path) as conn:
            conn.executescript(
                """
                CREATE TABLE data_account (
                  data_acct_code TEXT PRIMARY KEY,
                  data_acct_name TEXT NOT NULL,
                  budget_formula TEXT,
                  actual_formula TEXT,
                  value_type TEXT NOT NULL
                );
                CREATE TABLE data_account_metric_node (
                  node_code TEXT PRIMARY KEY,
                  node_name TEXT NOT NULL
                );
                CREATE TABLE data_account_metric_binding (
                  data_acct_code TEXT NOT NULL,
                  metric_node_code TEXT NOT NULL
                );
                CREATE TABLE org_product_metric_table (
                  entity_code TEXT,
                  table_name TEXT,
                  payload_json TEXT
                );
                CREATE TABLE smart_report_calc_metric (
                  metric_code TEXT PRIMARY KEY NOT NULL,
                  metric_name TEXT NOT NULL,
                  expression TEXT NOT NULL,
                  components_json TEXT NOT NULL,
                  value_type TEXT NOT NULL DEFAULT '金额',
                  format_type TEXT NOT NULL DEFAULT 'number',
                  remark TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE smart_report_template (
                  template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_code TEXT NOT NULL UNIQUE,
                  template_name TEXT NOT NULL,
                  template_type TEXT NOT NULL,
                  file_path TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'active',
                  version_no INTEGER NOT NULL DEFAULT 1,
                  remark TEXT,
                  created_by TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL
                );
                CREATE TABLE smart_report_template_variable (
                  variable_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  template_id INTEGER NOT NULL,
                  variable_key TEXT NOT NULL,
                  variable_name TEXT NOT NULL,
                  variable_type TEXT NOT NULL,
                  binding_config_json TEXT,
                  display_order INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  UNIQUE(template_id, variable_key)
                );
                INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                VALUES
                  ('A01.01.001', '已确认主体系指标', '金额'),
                  ('Z99.01.001', '孤立运行数据科目', '金额');
                INSERT INTO data_account_metric_node(node_code, node_name)
                VALUES
                  ('A01.01.001', '已确认主体系指标'),
                  ('Z99.01.001', '孤立运行指标节点');
                INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code)
                VALUES
                  ('A01.01.001', 'A01.01.001'),
                  ('Z99.01.001', 'Z99.01.001');
                INSERT INTO org_product_metric_table(entity_code, table_name, payload_json)
                VALUES (
                  'A01',
                  '业务状况表',
                  '{"metrics":[{"code":"A0101001","name":"已确认主体系指标","mapping_status":"MANUAL_CONFIRMED","data_acct_code":"SHOULD_BE_IGNORED","metric_node_code":"SHOULD_BE_IGNORED"},{"code":"Z9901001","name":"旧字段孤立指标","mapping_status":"MANUAL_CONFIRMED","data_acct_code":"Z99.01.001","metric_node_code":"Z99.01.001"}]}'
                );
                """
            )

    async def test_ai_binding_catalog_uses_only_derivable_org_product_metric_refs(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            common_path = data_dir / "common.db"
            self._build_common_db(common_path)

            try:
                catalog = await SmartReportService(data_dir=data_dir)._load_ai_binding_catalog()
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual([item["code"] for item in catalog], ["A01.01.001"])
        self.assertEqual(catalog[0]["name"], "已确认主体系指标")
        self.assertNotIn("Z99.01.001", {item["code"] for item in catalog})

    async def test_calc_metric_upsert_rejects_orphan_runtime_data_account(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            self._build_common_db(data_dir / "common.db")
            service = SmartReportService(data_dir=data_dir)
            try:
                saved = await service.upsert_calc_metric(
                    SmartReportCalcMetricUpsert(
                        metric_code="income_ratio",
                        metric_name="收入指标",
                        expression="base",
                        components=[
                            SmartReportCalcMetricComponent(
                                alias="base",
                                data_acct_code="A01.01.001",
                                data_acct_name="已确认主体系指标",
                            )
                        ],
                    )
                )
                self.assertEqual(saved.components[0].data_acct_code, "A01.01.001")

                with self.assertRaises(HTTPException) as raised:
                    await service.upsert_calc_metric(
                        SmartReportCalcMetricUpsert(
                            metric_code="orphan_ratio",
                            metric_name="孤立指标",
                            expression="base",
                            components=[
                                SmartReportCalcMetricComponent(
                                    alias="base",
                                    data_acct_code="Z99.01.001",
                                    data_acct_name="孤立运行数据科目",
                                )
                            ],
                        )
                    )
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("机构及产品指标主表", str(raised.exception.detail))

    async def test_template_formula_variables_require_confirmed_org_product_metric_refs(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            common_path = data_dir / "common.db"
            self._build_common_db(common_path)
            template_path = data_dir / "smart_report_templates" / "demo.docx"
            template_path.parent.mkdir(parents=True)
            template_path.write_bytes(b"demo")
            with sqlite3.connect(common_path) as conn:
                conn.execute(
                    """
                    INSERT INTO smart_report_template(
                      template_code, template_name, template_type, file_path, status,
                      version_no, created_at, updated_at
                    )
                    VALUES ('demo', 'Demo', 'analysis', ?, 'active', 1, 'now', 'now')
                    """,
                    (str(template_path),),
                )
                template_id = int(conn.execute("SELECT template_id FROM smart_report_template").fetchone()[0])
            service = SmartReportService(data_dir=data_dir)
            try:
                variables = await service.upsert_variables(
                    template_id,
                    [
                        SmartReportTemplateVariableUpsert(
                            variable_key="formula:A01.01.001:budget",
                            variable_type="formula",
                            binding_config={"data_acct_code": "A01.01.001", "formula_type": "budget"},
                        )
                    ],
                )
                self.assertEqual(variables[0].binding_config["data_acct_code"], "A01.01.001")

                with self.assertRaises(HTTPException) as raised:
                    await service.upsert_variables(
                        template_id,
                        [
                            SmartReportTemplateVariableUpsert(
                                variable_key="formula:Z99.01.001:budget",
                                variable_type="formula",
                                binding_config={
                                    "data_acct_code": "Z99.01.001",
                                    "formula_type": "budget",
                                },
                            )
                        ],
                    )
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("报告公式变量未在机构及产品指标主表中确认", str(raised.exception.detail))

    async def test_text_template_sync_rejects_orphan_formula_placeholder(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            self._build_common_db(data_dir / "common.db")
            service = SmartReportService(data_dir=data_dir)
            try:
                created = await service.create_or_update_text_template(
                    template_code="confirmed_formula",
                    template_name="确认公式",
                    content="{{formula:A01.01.001:budget}}",
                )
                self.assertEqual(created.placeholders, ["formula:A01.01.001:budget"])

                with self.assertRaises(HTTPException) as raised:
                    await service.create_or_update_text_template(
                        template_code="orphan_formula",
                        template_name="孤立公式",
                        content="{{formula:Z99.01.001:budget}}",
                    )
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("报告公式变量未在机构及产品指标主表中确认", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
