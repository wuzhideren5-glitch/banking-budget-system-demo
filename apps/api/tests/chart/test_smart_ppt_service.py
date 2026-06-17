from __future__ import annotations

import tempfile
import unittest
import sqlite3
from pathlib import Path

from fastapi import HTTPException

from app.core.config import settings
from app.schemas import SmartPptTemplateBindingConfigRequest, SmartPptTemplateBindingConfigRow
from app.services.smart_ppt_service import SmartPptService


class SmartPptTemplateStudioTests(unittest.TestCase):
    def _build_common_db(self, data_dir: Path) -> None:
        with sqlite3.connect(data_dir / "common.db") as conn:
            conn.executescript(
                """
                CREATE TABLE org_product_metric_table (
                  entity_code TEXT,
                  table_name TEXT,
                  payload_json TEXT
                );
                INSERT INTO org_product_metric_table(entity_code, table_name, payload_json)
                VALUES (
                  'A01',
                  '业务状况表',
                  '{"metrics":[{"code":"A0101020102016","name":"管理贷款余额","mapping_status":"MANUAL_CONFIRMED","data_acct_code":"SHOULD_BE_IGNORED","metric_node_code":"SHOULD_BE_IGNORED"},{"code":"Z9901","name":"孤立指标","mapping_status":"MANUAL_CONFIRMED","data_acct_code":"Z99.01.001","metric_node_code":"Z99.01.001"}]}'
                );
                """
            )

    def test_template_file_name_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = SmartPptService(data_dir=Path(tmp_dir))

            with self.assertRaises(HTTPException) as ctx:
                service.get_template_bindings("")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "模板文件名不能为空")

    def test_template_file_name_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = SmartPptService(data_dir=Path(tmp_dir))

            with self.assertRaises(HTTPException) as ctx:
                service.get_template_bindings("../demo.pptx")

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "模板文件名不合法")

    def test_template_bindings_preserve_org_product_metric_reference(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir)
            settings.data_dir = data_dir
            self._build_common_db(data_dir)
            template_dir = data_dir / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "demo.pptx").write_bytes(b"pptx")
            service = SmartPptService(data_dir=data_dir)

            try:
                saved = service.save_template_bindings(
                    SmartPptTemplateBindingConfigRequest(
                        template_file_name="demo.pptx",
                        bindings=[
                            SmartPptTemplateBindingConfigRow(
                                object_id="chart-1",
                                slide_index=1,
                                object_type="chart",
                                binding_type="chart",
                                chart_config_code="time_trend_line",
                                metric_code="A01.01.02.01.02.016",
                                org_product_metric_ref="A01:业务状况表:A0101020102016",
                                org_product_metric_name="管理贷款余额",
                                org_product_data_acct_code="A01.01.02.01.02.016",
                                enabled=True,
                            )
                        ],
                    )
                )
                loaded = service.get_template_bindings("demo.pptx")
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(saved.bindings[0].org_product_metric_ref, "A01:业务状况表:A0101020102016")
        self.assertEqual(loaded.bindings[0].org_product_metric_name, "管理贷款余额")
        self.assertEqual(loaded.bindings[0].org_product_data_acct_code, "A01.01.02.01.02.016")

    def test_template_bindings_reject_orphan_or_mismatched_org_product_refs(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir)
            settings.data_dir = data_dir
            self._build_common_db(data_dir)
            template_dir = data_dir / "templates"
            template_dir.mkdir(parents=True)
            (template_dir / "demo.pptx").write_bytes(b"pptx")
            service = SmartPptService(data_dir=data_dir)

            try:
                with self.assertRaises(HTTPException) as orphan:
                    service.save_template_bindings(
                        SmartPptTemplateBindingConfigRequest(
                            template_file_name="demo.pptx",
                            bindings=[
                                SmartPptTemplateBindingConfigRow(
                                    object_id="chart-1",
                                    slide_index=1,
                                    object_type="chart",
                                    org_product_data_acct_code="Z99.01.001",
                                )
                            ],
                        )
                    )
                with self.assertRaises(HTTPException) as mismatched:
                    service.save_template_bindings(
                        SmartPptTemplateBindingConfigRequest(
                            template_file_name="demo.pptx",
                            bindings=[
                                SmartPptTemplateBindingConfigRow(
                                    object_id="chart-2",
                                    slide_index=1,
                                    object_type="chart",
                                    org_product_metric_ref="A01:业务状况表:A0111",
                                    org_product_data_acct_code="A01.01.02.01.02.016",
                                )
                            ],
                        )
                    )
            finally:
                settings.data_dir = original_data_dir

        self.assertEqual(orphan.exception.status_code, 400)
        self.assertIn("机构及产品指标主表", str(orphan.exception.detail))
        self.assertEqual(mismatched.exception.status_code, 400)
        self.assertIn("不匹配", str(mismatched.exception.detail))


if __name__ == "__main__":
    unittest.main()
