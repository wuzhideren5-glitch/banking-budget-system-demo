from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.services.expense_actual_import_schema import ensure_expense_actual_import_schema_ready


class ExpenseActualImportSchemaTests(unittest.TestCase):
    def test_ensures_current_actual_import_tables_and_mapping_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"

            asyncio.run(ensure_expense_actual_import_schema_ready(db_path))

            with sqlite3.connect(db_path) as db:
                tables = {
                    str(row[0])
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                batch_columns = {
                    str(row[1])
                    for row in db.execute("PRAGMA table_info(expense_actual_import_batch)").fetchall()
                }
                detail_columns = {
                    str(row[1])
                    for row in db.execute("PRAGMA table_info(expense_actual_detail_raw)").fetchall()
                }

            self.assertIn("expense_actual_import_batch", tables)
            self.assertIn("expense_actual_detail_raw", tables)
            self.assertIn("manage_dept_owner_mapping", tables)
            self.assertIn("bi_ai_subject_mapping", tables)
            self.assertIn("import_kind", batch_columns)
            self.assertIn("import_kind", detail_columns)
            self.assertIn("owner_name_mapped", detail_columns)
            self.assertIn("budget_subject_mapped", detail_columns)

    def test_rejects_retired_actual_import_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            with sqlite3.connect(db_path) as db:
                db.execute(
                    """
                    CREATE TABLE expense_actual_import_batch (
                      id INTEGER PRIMARY KEY,
                      file_name TEXT NOT NULL
                    )
                    """
                )
                db.execute(
                    """
                    CREATE TABLE expense_actual_detail_raw (
                      id INTEGER PRIMARY KEY,
                      period_ym TEXT NOT NULL,
                      amount REAL
                    )
                    """
                )
                db.commit()

            with self.assertRaisesRegex(RuntimeError, "缺少当前字段"):
                asyncio.run(ensure_expense_actual_import_schema_ready(db_path))


if __name__ == "__main__":
    unittest.main()
