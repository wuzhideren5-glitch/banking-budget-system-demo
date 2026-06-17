from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from app.services.expense_master_data import sync_expense_dept_name_refs


class ExpenseMasterDataTests(unittest.TestCase):
    def test_sync_expense_dept_name_refs_updates_owner_level_tables(self) -> None:
        async def run() -> dict[str, int]:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "common.db"
                conn = sqlite3.connect(path)
                try:
                    conn.executescript(
                        """
                        CREATE TABLE expense_framework_budget_department (
                          owner_name TEXT,
                          budget_department TEXT
                        );
                        CREATE TABLE expense_forecast_entry (
                          scope_type TEXT,
                          scope_value TEXT
                        );
                        CREATE TABLE expense_actual_detail_raw (
                          owner_name_mapped TEXT
                        );
                        INSERT INTO expense_framework_budget_department(owner_name, budget_department)
                        VALUES ('旧部门', '旧部门');
                        INSERT INTO expense_forecast_entry(scope_type, scope_value)
                        VALUES ('owner', '旧部门'), ('group', '旧部门');
                        INSERT INTO expense_actual_detail_raw(owner_name_mapped)
                        VALUES ('旧部门');
                        """
                    )
                    conn.commit()
                finally:
                    conn.close()

                async with aiosqlite.connect(path) as db:
                    counts = await sync_expense_dept_name_refs(
                        db,
                        dept_level=2,
                        old_name="旧部门",
                        new_name="新部门",
                    )
                    await db.commit()

                conn = sqlite3.connect(path)
                try:
                    owner_row = conn.execute(
                        "SELECT owner_name, budget_department FROM expense_framework_budget_department"
                    ).fetchone()
                    forecast_rows = conn.execute(
                        "SELECT scope_type, scope_value FROM expense_forecast_entry ORDER BY scope_type"
                    ).fetchall()
                    raw_row = conn.execute("SELECT owner_name_mapped FROM expense_actual_detail_raw").fetchone()
                finally:
                    conn.close()

                self.assertEqual(owner_row, ("新部门", "新部门"))
                self.assertEqual(forecast_rows, [("group", "旧部门"), ("owner", "新部门")])
                self.assertEqual(raw_row, ("新部门",))
                return counts

        counts = asyncio.run(run())
        self.assertEqual(counts["expense_framework_budget_department.owner_name"], 1)
        self.assertEqual(counts["expense_forecast_entry.scope_value[owner]"], 1)
        self.assertEqual(counts["expense_actual_detail_raw.owner_name_mapped"], 1)


if __name__ == "__main__":
    unittest.main()
