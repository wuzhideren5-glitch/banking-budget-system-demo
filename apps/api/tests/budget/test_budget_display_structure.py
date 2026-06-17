from __future__ import annotations

import unittest

import aiosqlite

from app.db_bootstrap.report_display import ensure_budget_output_display_item_schema
from app.services.budget_display_structure import (
    allocate_budget_display_row_key,
    clear_budget_display_runtime_ref_binding,
    format_budget_display_row_key,
    parse_display_row_key,
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
          value_type TEXT NOT NULL
        );
        INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
        VALUES ('A01.01.01.001', '开鑫贷日均余额', '金额');
        """
    )
    await ensure_budget_output_display_item_schema(db)
    return db


class BudgetDisplayStructureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        db = getattr(self, "db", None)
        if db is not None:
            await db.close()

    def test_parse_and_format_display_row_key(self) -> None:
        self.assertEqual(
            format_budget_display_row_key("PRODUCT.A01", (1, 2, 3)),
            "PRODUCT.A01.01.02.03",
        )
        self.assertEqual(parse_display_row_key("TOTAL.01.02"), ("TOTAL", (1, 2)))
        self.assertEqual(parse_display_row_key("PRODUCT.A01.01.02"), ("PRODUCT.A01", (1, 2)))
        self.assertIsNone(parse_display_row_key("PRODUCT.A01"))
        self.assertIsNone(parse_display_row_key("A01.01.01.001"))

    async def test_allocate_row_key_by_display_position(self) -> None:
        self.db = await build_db()
        await self.db.execute(
            """
            INSERT INTO budget_output_display_item(
              row_key, display_view, parent_row_key, row_type, display_name, level, sort_order
            )
            VALUES
              ('TOTAL.01', 'TOTAL', NULL, 'GROUP', '资产业务', 1, 10),
              ('TOTAL.01.01', 'TOTAL', 'TOTAL.01', 'GROUP', '贷款', 2, 10)
            """
        )

        root_key = await allocate_budget_display_row_key(self.db, display_view="TOTAL", parent_row_key=None)
        child_key = await allocate_budget_display_row_key(self.db, display_view="TOTAL", parent_row_key="TOTAL.01")

        self.assertEqual(root_key, "TOTAL.02")
        self.assertEqual(child_key, "TOTAL.01.02")

    async def test_clear_binding_preserves_display_row(self) -> None:
        self.db = await build_db()
        await self.db.execute(
            """
            INSERT INTO budget_output_display_item(
              row_key, display_view, parent_row_key, data_acct_code, row_type,
              display_name, value_type, level, sort_order
            )
            VALUES (
              'PRODUCT.A01.01', 'PRODUCT.A01', NULL, 'A01.01.01.001', 'METRIC',
              '开鑫贷日均余额', '金额', 1, 10
            )
            """
        )

        changed = await clear_budget_display_runtime_ref_binding(self.db, "A01.01.01.001")

        self.assertEqual(changed, 1)
        cur = await self.db.execute(
            """
            SELECT row_key, data_acct_code, row_type, value_type, display_name
            FROM budget_output_display_item
            WHERE row_key = 'PRODUCT.A01.01'
            """
        )
        row = await cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["row_key"], "PRODUCT.A01.01")
        self.assertIsNone(row["data_acct_code"])
        self.assertEqual(row["row_type"], "GROUP")
        self.assertIsNone(row["value_type"])
        self.assertEqual(row["display_name"], "开鑫贷日均余额")

if __name__ == "__main__":
    unittest.main()
