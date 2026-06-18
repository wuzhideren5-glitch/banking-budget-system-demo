from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import expense_actual_import_schema as schema_module
from app.services.expense_actual_import_schema import ensure_expense_actual_import_schema_ready


class ExpenseActualImportSchemaTests(unittest.TestCase):
    def test_runtime_common_actual_import_schema_ready_validates_mysql_contract(self) -> None:
        required_tables = schema_module.REQUIRED_TABLES

        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple]] = []

            async def fetch_all(self, sql, params=()):
                self.fetch_all_calls.append((sql, tuple(params)))
                table_name = str(params[0])
                return [{"COLUMN_NAME": column_name} for column_name in sorted(required_tables[table_name])]

        async def run() -> FakePool:
            fake_pool = FakePool()
            with patch.object(schema_module, "get_pool", return_value=fake_pool):
                await ensure_expense_actual_import_schema_ready(Path(settings.data_dir) / "common.db")
            return fake_pool

        fake_pool = asyncio.run(run())

        queried_tables = {params[0] for _sql, params in fake_pool.fetch_all_calls}
        self.assertEqual(queried_tables, set(required_tables))
        self.assertTrue(any("INFORMATION_SCHEMA.COLUMNS" in sql for sql, _ in fake_pool.fetch_all_calls))
        all_sql = "\n".join(sql for sql, _ in fake_pool.fetch_all_calls)
        self.assertNotIn("PRAGMA foreign_keys", all_sql)
        self.assertNotIn("sqlite_master", all_sql)

    def test_runtime_common_actual_import_schema_ready_rejects_missing_mysql_columns(self) -> None:
        required_tables = {
            table_name: set(columns)
            for table_name, columns in schema_module.REQUIRED_TABLES.items()
        }
        required_tables["expense_actual_detail_raw"].discard("import_kind")

        class FakePool:
            async def fetch_all(self, sql, params=()):
                table_name = str(params[0])
                return [{"COLUMN_NAME": column_name} for column_name in sorted(required_tables[table_name])]

        with patch.object(schema_module, "get_pool", return_value=FakePool()):
            with self.assertRaisesRegex(RuntimeError, "缺少当前字段"):
                asyncio.run(ensure_expense_actual_import_schema_ready(Path(settings.data_dir) / "common.db"))

    def test_actual_import_schema_adapter_does_not_import_aiosqlite(self) -> None:
        source = Path(schema_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

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
