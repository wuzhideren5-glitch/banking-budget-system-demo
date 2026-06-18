from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.services import expense_forecast_schema as schema_module
from app.services.expense_forecast_schema import ensure_expense_forecast_schema_ready


class ExpenseForecastSchemaTests(unittest.TestCase):
    def test_runtime_common_schema_ready_validates_mysql_contract(self) -> None:
        required_tables = schema_module.REQUIRED_TABLES

        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple]] = []
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            async def fetch_all(self, sql, params=()):
                self.fetch_all_calls.append((sql, tuple(params)))
                table_name = str(params[0])
                return [{"COLUMN_NAME": column_name} for column_name in sorted(required_tables[table_name])]

            async def fetch_one(self, sql, params=()):
                self.fetch_one_calls.append((sql, tuple(params)))
                if "SHOW CREATE TABLE `expense_forecast_rule`" in sql:
                    return {"Create Table": "CREATE TABLE expense_forecast_rule (metric_source_priority varchar(32))"}
                if "SHOW CREATE TABLE `expense_forecast_rule_variable`" in sql:
                    return {"Create Table": "CREATE TABLE expense_forecast_rule_variable (source_type varchar(32))"}
                if "expense_forecast_rule_param" in sql:
                    return None
                raise AssertionError(sql)

        async def run() -> FakePool:
            fake_pool = FakePool()
            with patch.object(schema_module, "get_pool", return_value=fake_pool):
                await ensure_expense_forecast_schema_ready(Path(settings.data_dir) / "common.db")
            return fake_pool

        fake_pool = asyncio.run(run())

        queried_tables = {params[0] for _sql, params in fake_pool.fetch_all_calls}
        self.assertEqual(queried_tables, set(required_tables))
        self.assertTrue(any("INFORMATION_SCHEMA.COLUMNS" in sql for sql, _ in fake_pool.fetch_all_calls))
        all_sql = "\n".join(sql for sql, _ in fake_pool.fetch_one_calls + fake_pool.fetch_all_calls)
        self.assertNotIn("PRAGMA foreign_keys", all_sql)
        self.assertNotIn("sqlite_master", all_sql)

    def test_runtime_common_schema_ready_rejects_mysql_old_driver_contract(self) -> None:
        required_tables = {
            table_name: set(columns)
            for table_name, columns in schema_module.REQUIRED_TABLES.items()
        }
        required_tables["expense_forecast_rule"].add("driver_source_priority")

        class FakePool:
            async def fetch_all(self, sql, params=()):
                table_name = str(params[0])
                return [{"COLUMN_NAME": column_name} for column_name in sorted(required_tables[table_name])]

            async def fetch_one(self, sql, params=()):
                if "SHOW CREATE TABLE `expense_forecast_rule`" in sql:
                    return {
                        "Create Table": "CREATE TABLE expense_forecast_rule (metric_source_priority varchar(32), driver_expr text)"
                    }
                if "SHOW CREATE TABLE `expense_forecast_rule_variable`" in sql:
                    return {"Create Table": "CREATE TABLE expense_forecast_rule_variable (source_type varchar(32))"}
                return None

        with patch.object(schema_module, "get_pool", return_value=FakePool()):
            with self.assertRaisesRegex(RuntimeError, "旧 driver 合同"):
                asyncio.run(ensure_expense_forecast_schema_ready(Path(settings.data_dir) / "common.db"))

    def test_schema_adapter_does_not_import_aiosqlite(self) -> None:
        source = Path(schema_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_ensures_current_expense_forecast_private_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE budget_subject_catalog(id INTEGER PRIMARY KEY)")
                db.commit()

            asyncio.run(ensure_expense_forecast_schema_ready(db_path))

            with sqlite3.connect(db_path) as db:
                tables = {
                    str(row[0])
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                rule_columns = {
                    str(row[1])
                    for row in db.execute("PRAGMA table_info(expense_forecast_rule)").fetchall()
                }

            self.assertIn("expense_forecast_entry", tables)
            self.assertIn("expense_forecast_rule", tables)
            self.assertIn("expense_forecast_rule_param", tables)
            self.assertIn("expense_forecast_rule_variable", tables)
            self.assertIn("expense_forecast_calc_result", tables)
            self.assertIn("expense_forecast_override", tables)
            self.assertIn("metric_source_priority", rule_columns)
            self.assertNotIn("driver_source_priority", rule_columns)

    def test_rejects_retired_driver_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "common.db"
            with sqlite3.connect(db_path) as db:
                db.execute("CREATE TABLE budget_subject_catalog(id INTEGER PRIMARY KEY)")
                db.execute(
                    """
                    CREATE TABLE expense_forecast_rule (
                      id INTEGER PRIMARY KEY,
                      driver_source_priority TEXT
                    )
                    """
                )
                db.commit()

            with self.assertRaisesRegex(RuntimeError, "旧 driver 合同"):
                asyncio.run(ensure_expense_forecast_schema_ready(db_path))


if __name__ == "__main__":
    unittest.main()
