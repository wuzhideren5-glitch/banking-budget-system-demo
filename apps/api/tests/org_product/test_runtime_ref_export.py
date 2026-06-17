from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite
from openpyxl import load_workbook

from app.db_bootstrap.runtime_metric_tree import ensure_runtime_metric_identity_tables
from app.services.runtime_ref_export import (
    RUNTIME_REF_EXPORT_HEADERS,
    build_runtime_ref_export_workbook,
    export_runtime_refs_workbook,
)


class RuntimeRefExportTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _seed_org_product_tree(conn: sqlite3.Connection) -> None:
        """Create the org_product_tree_snapshot table used by the CTE."""
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS org_product_tree_snapshot (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM org_product_tree_snapshot WHERE id = 1")
        conn.execute(
            "INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at) VALUES (1, ?, 'now')",
            ('{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"泛微粒贷","children":[]}]}]}',),
        )

    @staticmethod
    def _insert_metric_node(conn: sqlite3.Connection, **kwargs: object) -> None:
        """Insert a row into data_account_metric_node with sensible defaults."""
        cols = {
            "node_code": "",
            "node_name": "",
            "parent_code": None,
            "product_code": "",
            "local_metric_code": "",
            "logic_code": "",
            "functional_group_code": "",
            "metric_table_name": "",
            "level": 1,
            "node_type": "CATEGORY",
            "horizontal_rollup": 0,
            "vertical_rollup": 0,
            "runtime_account_enabled": 0,
            "budget_formula": None,
            "actual_formula": None,
            "budget_rule_code": None,
            "budget_rule_config_json": None,
            "need_calc": 0,
            "formula_calc_mode": 0,
            "allow_manual_entry": 1,
            "value_type": "金额",
            "sort_order": 0,
            "is_active": 1,
            "remark": None,
        }
        cols.update(kwargs)
        col_names = ", ".join(cols.keys())
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(
            f"INSERT INTO data_account_metric_node({col_names}) VALUES ({placeholders})",
            list(cols.values()),
        )

    async def test_export_workbook_uses_current_product_metric_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                # ensure_runtime_metric_identity_tables creates the physical table
                # and the two views (data_account, data_account_metric_binding)
                # on empty tables the validation passes trivially
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)

                # A01: product root (category node, not an account)
                self._insert_metric_node(
                    conn,
                    node_code="A01",
                    node_name="泛微粒贷",
                    product_code="A01",
                    level=1,
                    node_type="CATEGORY",
                )
                # A01.01.01.001: metric node with runtime account enabled
                self._insert_metric_node(
                    conn,
                    node_code="A01.01.01.001",
                    node_name="产品利息收入",
                    parent_code="A01",
                    product_code="A01",
                    local_metric_code="01.01.001",
                    logic_code="01.01.001",
                    functional_group_code="业务状况表",
                    metric_table_name="业务状况表",
                    level=4,
                    node_type="METRIC",
                    runtime_account_enabled=1,
                    remark="产品前缀科目",
                )
                # CORP: corp root (category node, not an account)
                self._insert_metric_node(
                    conn,
                    node_code="CORP",
                    node_name="全行",
                    product_code="CORP",
                    level=1,
                    node_type="CATEGORY",
                )
                # CORP.00: corp metric node with runtime account enabled
                self._insert_metric_node(
                    conn,
                    node_code="CORP.00",
                    node_name="全行指标",
                    parent_code="CORP",
                    product_code="CORP",
                    local_metric_code="00",
                    logic_code="00",
                    level=2,
                    node_type="METRIC",
                    runtime_account_enabled=1,
                    remark="全行口径",
                )
                conn.commit()

            async with aiosqlite.connect(db_path) as db:
                buffer = await build_runtime_ref_export_workbook(db)

        wb = load_workbook(buffer, data_only=True)
        self.assertEqual(wb.sheetnames[:2], ["运行说明", "机构及产品指标编码清单"])
        intro_ws = wb["运行说明"]
        self.assertEqual(intro_ws.cell(row=1, column=1).value, "项目")
        self.assertEqual(intro_ws.cell(row=2, column=1).value, "定位")
        self.assertIn("机构及产品指标体系主键", str(intro_ws.cell(row=2, column=2).value))
        self.assertEqual(intro_ws.cell(row=3, column=2).value, "机构及产品指标")
        self.assertIn("不作为独立配置导入模板", str(intro_ws.cell(row=5, column=2).value))
        ws = wb["机构及产品指标编码清单"]
        headers = [ws.cell(row=1, column=idx).value for idx in range(1, len(RUNTIME_REF_EXPORT_HEADERS) + 1)]
        self.assertEqual(headers, list(RUNTIME_REF_EXPORT_HEADERS))
        self.assertTrue(ws.cell(row=1, column=1).font.bold)

        # Rows are ordered by data_acct_code: A01.01.01.001, then CORP.00
        product_row = [ws.cell(row=2, column=idx).value for idx in range(1, len(RUNTIME_REF_EXPORT_HEADERS) + 1)]
        corp_row = [ws.cell(row=3, column=idx).value for idx in range(1, len(RUNTIME_REF_EXPORT_HEADERS) + 1)]

        self.assertEqual(product_row[0], "泛微粒贷 / 产品利息收入")
        self.assertEqual(product_row[1], "A01.01.01.001")
        self.assertEqual(product_row[2], "A01")
        self.assertEqual(product_row[3], "A01.01.01.001")
        self.assertEqual(product_row[8], "泛微粒贷")
        self.assertEqual(product_row[13], 1)
        self.assertEqual(
            product_row[14],
            "A01:业务状况表:A01.01.01.001 产品利息收入",
        )

        self.assertEqual(corp_row[0], "全行 / 全行指标")
        self.assertEqual(corp_row[1], "CORP.00")
        self.assertEqual(corp_row[2], "CORP")
        self.assertEqual(corp_row[3], "CORP.00")
        self.assertEqual(corp_row[8], "全行")
        self.assertEqual(corp_row[13], 0)
        self.assertIsNone(corp_row[14])

    async def test_export_workbook_wrapper_opens_explicit_common_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                ensure_runtime_metric_identity_tables(conn)
                self._seed_org_product_tree(conn)

                self._insert_metric_node(
                    conn,
                    node_code="A01.01.01.001",
                    node_name="产品利息收入",
                    product_code="A01",
                    local_metric_code="01.01.001",
                    logic_code="01.01.001",
                    functional_group_code="业务状况表",
                    metric_table_name="业务状况表",
                    level=4,
                    node_type="METRIC",
                    runtime_account_enabled=1,
                )
                conn.commit()

            buffer = await export_runtime_refs_workbook(db_path)

        wb = load_workbook(buffer, data_only=True)
        self.assertEqual(wb.sheetnames[:2], ["运行说明", "机构及产品指标编码清单"])
        ws = wb["机构及产品指标编码清单"]
        self.assertEqual(ws.cell(row=2, column=4).value, "A01.01.01.001")
        self.assertEqual(ws.cell(row=2, column=9).value, "泛微粒贷")


if __name__ == "__main__":
    unittest.main()
