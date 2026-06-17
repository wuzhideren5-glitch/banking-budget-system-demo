from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.expense_budget_execution_status import build_expense_budget_execution_status


def _seed_status_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE expense_sync_meta (
              sync_key TEXT PRIMARY KEY NOT NULL,
              source_file TEXT NOT NULL,
              source_mtime TEXT,
              synced_at TEXT NOT NULL,
              row_count INTEGER NOT NULL DEFAULT 0,
              note TEXT
            );
            CREATE TABLE expense_framework_budget_department(id INTEGER PRIMARY KEY AUTOINCREMENT);
            CREATE TABLE expense_framework_product_department(id INTEGER PRIMARY KEY AUTOINCREMENT);
            CREATE TABLE expense_framework_subject(id INTEGER PRIMARY KEY AUTOINCREMENT);
            CREATE TABLE expense_actual_detail_raw(id INTEGER PRIMARY KEY AUTOINCREMENT);
            INSERT INTO expense_sync_meta(sync_key, source_file, source_mtime, synced_at, row_count, note)
            VALUES
              ('framework_import', 'framework.xlsx', NULL, '2026-06-02T00:00:00Z', 3, 'framework rows'),
              ('master_apply', 'framework.xlsx', NULL, '2026-06-02T00:01:00Z', 2, 'master rows'),
              ('actual_import', 'old-monthly.xlsx', NULL, '2026-06-02T00:02:00Z', 1, 'retired sync key');
            INSERT INTO expense_framework_budget_department DEFAULT VALUES;
            INSERT INTO expense_framework_product_department DEFAULT VALUES;
            INSERT INTO expense_framework_product_department DEFAULT VALUES;
            INSERT INTO expense_framework_subject DEFAULT VALUES;
            INSERT INTO expense_actual_detail_raw DEFAULT VALUES;
            INSERT INTO expense_actual_detail_raw DEFAULT VALUES;
            INSERT INTO expense_actual_detail_raw DEFAULT VALUES;
            """
        )
        conn.commit()
    finally:
        conn.close()


class ExpenseBudgetExecutionStatusTests(unittest.TestCase):
    def test_status_read_model_returns_current_keys_and_counts(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                db_path = Path(tmp) / "common.db"
                _seed_status_db(db_path)

                status = await build_expense_budget_execution_status(db_path)

            self.assertEqual(status["framework_import"]["source_file"], "framework.xlsx")
            self.assertEqual(status["master_apply"]["row_count"], 2)
            self.assertNotIn("actual_import", status)
            self.assertEqual(
                status["counts"],
                {
                    "expense_framework_budget_department": 1,
                    "expense_framework_product_department": 2,
                    "expense_framework_subject": 1,
                    "expense_actual_detail_raw": 3,
                },
            )

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
