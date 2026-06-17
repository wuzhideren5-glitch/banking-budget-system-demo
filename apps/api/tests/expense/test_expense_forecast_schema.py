from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

from app.services.expense_forecast_schema import ensure_expense_forecast_schema_ready


class ExpenseForecastSchemaTests(unittest.TestCase):
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
