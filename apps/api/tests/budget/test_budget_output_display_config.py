from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from io import BytesIO

import aiosqlite

from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema
from app.services.budget_display_config_import import build_budget_display_config_workbook
from app.services.budget_output_display_config import (
    BudgetOutputDisplayConfigError,
    BudgetOutputDisplayConfigCreateCommand,
    BudgetOutputDisplayConfigUpdateCommand,
    apply_budget_output_display_config_item_create,
    apply_budget_output_display_config_item_delete,
    apply_budget_output_display_config_item_update,
    apply_budget_output_display_config_import_upload,
    build_budget_output_display_config_export_workbook,
    create_budget_output_display_item,
    delete_budget_output_display_item,
    load_budget_output_display_config_response,
    update_budget_output_display_item,
)


async def build_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.executescript(
        """
        CREATE TABLE data_account (
          data_acct_code TEXT PRIMARY KEY NOT NULL,
          data_acct_name TEXT NOT NULL,
          budget_formula TEXT,
          actual_formula TEXT,
          formula_calc_mode INTEGER NOT NULL DEFAULT 0,
          allow_manual_entry INTEGER NOT NULL DEFAULT 1,
          value_type TEXT NOT NULL
        );
        CREATE TABLE data_account_metric_node (
          node_code TEXT PRIMARY KEY,
          node_name TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE data_account_metric_binding (
          data_acct_code TEXT PRIMARY KEY,
          metric_node_code TEXT NOT NULL,
          scope_type TEXT NOT NULL,
          scope_code TEXT NOT NULL,
          is_active INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE org_product_tree_snapshot (
          id INTEGER PRIMARY KEY CHECK (id = 1),
          payload_json TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE org_product_metric_table (
          entity_code TEXT NOT NULL,
          entity_name TEXT NOT NULL,
          table_id TEXT NOT NULL,
          table_name TEXT NOT NULL,
          payload_json TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (entity_code, table_name)
        );
        INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
        VALUES ('A01.01.01.001', '开鑫贷日均余额', '金额');
        INSERT INTO data_account_metric_node(node_code, node_name, sort_order)
        VALUES ('A01.01.01.001', '开鑫贷日均余额', 1);
        INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
        VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}', 'now');
        INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, sort_order)
        VALUES ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1);
        INSERT INTO org_product_metric_table(
          entity_code, entity_name, table_id, table_name, payload_json, updated_at
        )
        VALUES (
          'A01', '开鑫贷', 'table-业务状况表', '业务状况表',
          '{"metrics":[{"code":"A010101001","name":"营业收入","children":[]}]}',
          '2026-06-05T00:00:00Z'
        );
        """
    )
    await ensure_budget_output_display_item_schema(db)
    return db


async def build_db_file(path: Path) -> None:
    db = await aiosqlite.connect(path)
    try:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(
            """
            CREATE TABLE data_account (
              data_acct_code TEXT PRIMARY KEY NOT NULL,
              data_acct_name TEXT NOT NULL,
              budget_formula TEXT,
              actual_formula TEXT,
              formula_calc_mode INTEGER NOT NULL DEFAULT 0,
              allow_manual_entry INTEGER NOT NULL DEFAULT 1,
              value_type TEXT NOT NULL
            );
            CREATE TABLE data_account_metric_node (
              node_code TEXT PRIMARY KEY,
              node_name TEXT NOT NULL,
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE data_account_metric_binding (
              data_acct_code TEXT PRIMARY KEY,
              metric_node_code TEXT NOT NULL,
              scope_type TEXT NOT NULL,
              scope_code TEXT NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1,
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE org_product_tree_snapshot (
              id INTEGER PRIMARY KEY CHECK (id = 1),
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE org_product_metric_table (
              entity_code TEXT NOT NULL,
              entity_name TEXT NOT NULL,
              table_id TEXT NOT NULL,
              table_name TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY (entity_code, table_name)
            );
            INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
            VALUES
              ('A01.01.01.001', '开鑫贷日均余额', '金额'),
              ('A01.05', '05费用', '金额'),
              ('A01.05.01', '05编码', '金额');
            INSERT INTO data_account_metric_node(node_code, node_name, sort_order)
            VALUES
              ('A01.01.01.001', '开鑫贷日均余额', 1),
              ('A01.05', '05费用', 2),
              ('A01.05.01', '05编码', 3);
            INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
            VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}', 'now');
            INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, sort_order)
            VALUES
              ('A01.01.01.001', 'A01.01.01.001', 'PRODUCT', 'A01', 1),
              ('A01.05', 'A01.05', 'PRODUCT', 'A01', 2),
              ('A01.05.01', 'A01.05.01', 'PRODUCT', 'A01', 3);
            INSERT INTO org_product_metric_table(
              entity_code, entity_name, table_id, table_name, payload_json, updated_at
            )
            VALUES (
              'A01', '开鑫贷', 'table-业务状况表', '业务状况表',
              '{"metrics":[{"code":"A010101001","name":"管理贷款余额","children":[]},{"code":"A0105","name":"05费用","children":[]},{"code":"A010501","name":"05编码","children":[]}]}',
              '2026-06-05T00:00:00Z'
            );
            """
        )
        await ensure_budget_output_display_item_schema(db)
        await db.execute(
            """
            INSERT INTO budget_output_display_item(
              row_key, display_view, parent_row_key, data_acct_code, row_type,
              display_name, value_type, level, sort_order, is_active
            )
            VALUES ('TOTAL.01', 'TOTAL', NULL, 'A01.01.01.001', 'METRIC',
                    '日均余额', '金额', 1, 10, 1)
            """
        )
        await db.commit()
    finally:
        await db.close()


class BudgetOutputDisplayConfigTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        db = getattr(self, "db", None)
        if db is not None:
            await db.close()

    async def test_create_metric_after_row_allocates_key_and_shifts_sort_order(self) -> None:
        self.db = await build_db()
        await self.db.executescript(
            """
            INSERT INTO budget_output_display_item(
              row_key, display_view, parent_row_key, row_type, display_name, level, sort_order
            )
            VALUES
              ('TOTAL.01', 'TOTAL', NULL, 'GROUP', '资产业务', 1, 10),
              ('TOTAL.02', 'TOTAL', NULL, 'GROUP', '负债业务', 1, 20);
            """
        )

        row = await create_budget_output_display_item(
            self.db,
            BudgetOutputDisplayConfigCreateCommand(
                data_acct_code="A01.01.01.001",
                insert_after_row_key="TOTAL.01",
                org_product_ref="A01:业务状况表:A010101001",
                org_product_metric_name="营业收入",
            ),
        )

        self.assertEqual(row["row_key"], "TOTAL.03")
        self.assertEqual(row["display_name"], "开鑫贷日均余额")
        self.assertEqual(row["data_acct_code"], "A01.01.01.001")
        self.assertEqual(row["org_product_ref"], "A01:业务状况表:A010101001")
        self.assertEqual(row["org_product_entity_code"], "A01")
        self.assertEqual(row["org_product_table_name"], "业务状况表")
        self.assertEqual(row["org_product_metric_code"], "A010101001")
        self.assertEqual(row["org_product_metric_name"], "营业收入")
        self.assertEqual(row["row_type"], "METRIC")
        self.assertEqual(row["sort_order"], 11)
        cur = await self.db.execute(
            "SELECT sort_order FROM budget_output_display_item WHERE row_key = 'TOTAL.02'"
        )
        shifted = await cur.fetchone()
        self.assertEqual(shifted["sort_order"], 21)

    async def test_update_can_clear_data_account_binding_without_deleting_row(self) -> None:
        self.db = await build_db()
        await create_budget_output_display_item(
            self.db,
            BudgetOutputDisplayConfigCreateCommand(
                data_acct_code="A01.01.01.001",
                org_product_ref="A01:业务状况表:A010101001",
                org_product_metric_name="营业收入",
            ),
        )

        row = await update_budget_output_display_item(
            self.db,
            "TOTAL.01",
            BudgetOutputDisplayConfigUpdateCommand(data_acct_code=""),
        )

        self.assertEqual(row["row_key"], "TOTAL.01")
        self.assertIsNone(row["data_acct_code"])
        self.assertIsNone(row["org_product_ref"])
        self.assertIsNone(row["org_product_metric_code"])
        self.assertIsNone(row["org_product_metric_name"])
        self.assertEqual(row["row_type"], "GROUP")
        self.assertIsNone(row["value_type"])

    async def test_delete_removes_only_selected_display_row(self) -> None:
        self.db = await build_db()
        await self.db.executescript(
            """
            INSERT INTO budget_output_display_item(
              row_key, display_view, parent_row_key, row_type, display_name, level, sort_order
            )
            VALUES
              ('TOTAL.01', 'TOTAL', NULL, 'GROUP', '资产业务', 1, 10),
              ('TOTAL.02', 'TOTAL', NULL, 'GROUP', '负债业务', 1, 20);
            """
        )

        result = await delete_budget_output_display_item(self.db, "TOTAL.01")

        self.assertEqual(result, {"ok": True})
        cur = await self.db.execute("SELECT row_key FROM budget_output_display_item ORDER BY row_key")
        rows = await cur.fetchall()
        self.assertEqual([row["row_key"] for row in rows], ["TOTAL.02"])

    async def test_display_config_workflow_loads_response_and_export_workbook_from_current_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            await build_db_file(common_path)

            response = await load_budget_output_display_config_response(common_path=common_path)

            self.assertEqual([item.row_key for item in response.items], ["TOTAL.01"])
            self.assertEqual(response.items[0].data_acct_code, "A01.01.01.001")
            self.assertEqual(response.items[0].scope_name, "开鑫贷")
            self.assertIn("A01.01.01.001", [candidate.data_acct_code for candidate in response.candidates])
            base_candidates = [
                candidate
                for candidate in response.candidates
                if candidate.source_type == "org_product_runtime_ref"
            ]
            selected_base_candidates = [candidate for candidate in base_candidates if candidate.selected]
            self.assertEqual([candidate.data_acct_code for candidate in selected_base_candidates], ["A01.01.01.001"])

            wb = await build_budget_output_display_config_export_workbook(common_path=common_path)

            ws = wb["预算展示配置"]
            self.assertEqual(ws.cell(row=1, column=1).value, "展示行编码")
            self.assertEqual(ws.cell(row=1, column=11).value, "机构产品引用数量")
            self.assertEqual(ws.cell(row=1, column=12).value, "机构产品来源")
            self.assertEqual(ws.cell(row=2, column=1).value, "TOTAL.01")
            self.assertEqual(ws.cell(row=2, column=5).value, "A01.01.01.001")
            self.assertEqual(ws.cell(row=2, column=11).value, 1)
            self.assertEqual(
                ws.cell(row=2, column=12).value,
                "A01:业务状况表:A010101001 管理贷款余额",
            )

    async def test_display_config_candidates_include_confirmed_org_product_mappings_including_05(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            await build_db_file(common_path)
            db = await aiosqlite.connect(common_path)
            try:
                await db.executescript(
                    """
                    DELETE FROM org_product_metric_table;
                    INSERT INTO org_product_metric_table(
                      entity_code, entity_name, table_id, table_name, payload_json, updated_at
                    )
                    VALUES (
                      'A01', '开鑫贷', 'table-业务状况表', '业务状况表',
                      '{"metrics":[{"code":"A010101001","name":"营业收入","children":[]},{"code":"A0105","name":"05费用","children":[]}]}',
                      '2026-06-05T00:00:00Z'
                    );
                    """
                )
                await db.commit()
            finally:
                await db.close()

            response = await load_budget_output_display_config_response(common_path=common_path)

        org_candidates = [
            candidate
            for candidate in response.candidates
            if candidate.source_type == "org_product_metric"
        ]
        self.assertEqual(len(org_candidates), 2)
        self.assertEqual(org_candidates[0].data_acct_code, "A01.01.01.001")
        self.assertEqual(org_candidates[0].data_acct_name, "营业收入")
        self.assertEqual(org_candidates[0].source_ref, "A01:业务状况表:A010101001")
        self.assertEqual(org_candidates[0].org_product_ref, "A01:业务状况表:A010101001")
        self.assertEqual(org_candidates[0].org_product_entity_code, "A01")
        self.assertEqual(org_candidates[0].org_product_table_name, "业务状况表")
        self.assertEqual(org_candidates[0].org_product_metric_code, "A010101001")
        self.assertEqual(org_candidates[0].org_product_metric_name, "营业收入")
        self.assertEqual(org_candidates[0].metric_code, "A010101001")
        self.assertEqual(org_candidates[0].metric_name, "营业收入")
        self.assertFalse(org_candidates[0].selected)
        self.assertEqual({candidate.data_acct_code for candidate in org_candidates}, {"A01.01.01.001", "A01.05"})
        self.assertIn("A01:业务状况表:A0105", {candidate.source_ref for candidate in org_candidates})

    async def test_display_config_rejects_orphan_runtime_data_account(self) -> None:
        self.db = await build_db()
        await self.db.executescript(
            """
            INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
            VALUES ('Z99.01.001', '孤立运行数据科目', '金额');
            INSERT INTO data_account_metric_node(node_code, node_name, sort_order)
            VALUES ('Z99.01.001', '孤立运行指标节点', 99);
            INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, sort_order)
            VALUES ('Z99.01.001', 'Z99.01.001', 'PRODUCT', 'A01', 99);
            """
        )

        with self.assertRaisesRegex(BudgetOutputDisplayConfigError, "机构及产品指标主表"):
            await create_budget_output_display_item(
                self.db,
                BudgetOutputDisplayConfigCreateCommand(data_acct_code="Z99.01.001"),
            )

    async def test_import_upload_workflow_parses_applies_and_returns_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            await build_db_file(common_path)
            wb = build_budget_display_config_workbook(
                [
                    {
                        "row_key": "TOTAL.02",
                        "display_view": "TOTAL",
                        "parent_row_key": None,
                        "row_type": "METRIC",
                        "data_acct_code": "A01.01.01.001",
                        "display_name": "导入日均余额",
                        "value_type": "金额",
                        "level": 1,
                        "sort_order": 20,
                        "is_active": 1,
                    }
                ]
            )
            raw = BytesIO()
            wb.save(raw)

            result = await apply_budget_output_display_config_import_upload(
                file_name="display-config.xlsx",
                raw=raw.getvalue(),
                mode="replace",
                common_path=common_path,
            )

            self.assertEqual(result.mode, "replace")
            self.assertEqual(result.saved_rows, 1)
            self.assertEqual(result.metric_rows, 1)
            response = await load_budget_output_display_config_response(common_path=common_path)
            self.assertEqual([item.row_key for item in response.items], ["TOTAL.02"])
            self.assertEqual(response.items[0].display_name, "导入日均余额")

    async def test_import_upload_rejects_orphan_runtime_data_account(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            await build_db_file(common_path)
            db = await aiosqlite.connect(common_path)
            try:
                await db.executescript(
                    """
                    INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                    VALUES ('Z99.01.001', '孤立运行数据科目', '金额');
                    INSERT INTO data_account_metric_node(node_code, node_name, sort_order)
                    VALUES ('Z99.01.001', '孤立运行指标节点', 99);
                    INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_type, scope_code, sort_order)
                    VALUES ('Z99.01.001', 'Z99.01.001', 'PRODUCT', 'A01', 99);
                    """
                )
                await db.commit()
            finally:
                await db.close()
            wb = build_budget_display_config_workbook(
                [
                    {
                        "row_key": "TOTAL.99",
                        "display_view": "TOTAL",
                        "parent_row_key": None,
                        "row_type": "METRIC",
                        "data_acct_code": "Z99.01.001",
                        "display_name": "孤立导入行",
                        "value_type": "金额",
                        "level": 1,
                        "sort_order": 99,
                        "is_active": 1,
                    }
                ]
            )
            raw = BytesIO()
            wb.save(raw)

            with self.assertRaisesRegex(Exception, "机构及产品指标主表"):
                await apply_budget_output_display_config_import_upload(
                    file_name="display-config.xlsx",
                    raw=raw.getvalue(),
                    mode="upsert",
                    common_path=common_path,
                )

    async def test_item_write_workflows_manage_common_db_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            common_path = Path(tmp) / "common.db"
            await build_db_file(common_path)

            created = await apply_budget_output_display_config_item_create(
                BudgetOutputDisplayConfigCreateCommand(display_name="资产业务"),
                common_path=common_path,
            )

            self.assertEqual(created.row_key, "TOTAL.02")
            self.assertEqual(created.row_type, "GROUP")
            self.assertEqual(created.display_name, "资产业务")

            updated = await apply_budget_output_display_config_item_update(
                "TOTAL.01",
                BudgetOutputDisplayConfigUpdateCommand(data_acct_code="", display_name="日均余额-手工组"),
                common_path=common_path,
            )

            self.assertEqual(updated.row_key, "TOTAL.01")
            self.assertEqual(updated.row_type, "GROUP")
            self.assertIsNone(updated.data_acct_code)
            self.assertEqual(updated.display_name, "日均余额-手工组")

            deleted = await apply_budget_output_display_config_item_delete("TOTAL.02", common_path=common_path)

            self.assertEqual(deleted, {"ok": True})
            response = await load_budget_output_display_config_response(common_path=common_path)
            self.assertEqual([item.row_key for item in response.items], ["TOTAL.01"])


if __name__ == "__main__":
    unittest.main()
