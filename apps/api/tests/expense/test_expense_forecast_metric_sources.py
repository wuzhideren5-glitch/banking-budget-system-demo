from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from app.core.config import settings
import app.services.expense_forecast_metric_sources as module
from app.services.expense_forecast_metric_sources import load_expense_forecast_metric_source_month_map


def init_common_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE period (
                period_id INTEGER PRIMARY KEY,
                year TEXT,
                month INTEGER
            );
            CREATE TABLE data_account_metric_node (
                node_code TEXT PRIMARY KEY,
                functional_group_code TEXT,
                metric_table_name TEXT NOT NULL DEFAULT '',
                local_metric_code TEXT
            );
            CREATE TABLE data_account_metric_binding (
                data_acct_code TEXT,
                metric_node_code TEXT,
                scope_code TEXT,
                is_active INTEGER
            );
            """
        )
        db.executemany(
            "INSERT INTO period(period_id, year, month) VALUES (?, ?, ?)",
            [(101, "2026", 1), (102, "2026", 2), (201, "2025", 1)],
        )
        db.executemany(
            """
            INSERT INTO data_account_metric_node(node_code, functional_group_code, metric_table_name, local_metric_code)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("PRD1.MKT", "MARKETING", "", "MKT"),
                ("PRD1.OPS", "OPERATIONS", "", "OPS"),
            ],
        )
        db.executemany(
            """
            INSERT INTO data_account_metric_binding(data_acct_code, metric_node_code, scope_code, is_active)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("ACCT_MKT_A", "PRD1.MKT", "PRD1", 1),
                ("ACCT_MKT_B", "PRD1.MKT", "PRD1", 1),
                ("ACCT_MKT_INACTIVE", "PRD1.MKT", "PRD1", 0),
                ("ACCT_OPS", "PRD1.OPS", "PRD1", 1),
                ("ACCT_MKT_OTHER_PRODUCT", "PRD1.MKT", "PRD2", 1),
            ],
        )
        db.commit()


def init_budget_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE version (version_id INTEGER PRIMARY KEY);
            CREATE TABLE budget_data (
                version_id INTEGER,
                budget_actual INTEGER,
                period_id INTEGER,
                data_acct_code TEXT,
                product_code TEXT,
                value REAL
            );
            INSERT INTO version(version_id) VALUES (1), (3);
            """
        )
        db.executemany(
            """
            INSERT INTO budget_data(version_id, budget_actual, period_id, data_acct_code, product_code, value)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (3, 0, 101, "ACCT_MKT_A", "PRD1", 10.125),
                (3, 0, 101, "ACCT_MKT_B", "PRD1", 20.0),
                (3, 0, 102, "ACCT_MKT_A", "PRD1", 30.0),
                (3, 1, 102, "ACCT_MKT_A", "PRD1", 999.0),
                (1, 0, 102, "ACCT_MKT_A", "PRD1", 888.0),
                (3, 0, 101, "ACCT_MKT_OTHER_PRODUCT", "PRD2", 777.0),
                (3, 0, 101, "ACCT_OPS", "PRD1", 444.0),
            ],
        )
        db.commit()


class ExpenseForecastMetricSourceTests(unittest.TestCase):
    def test_metric_source_uses_mysql_for_runtime_common_and_budget_dbs(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls = []
                self.fetch_one_calls = []

            async def fetch_all(self, sql, params=()):
                self.fetch_all_calls.append((sql, params))
                if "FROM data_account_metric_binding" in sql:
                    return [{"data_acct_code": "ACCT_MKT_A"}, {"data_acct_code": "ACCT_MKT_B"}]
                if "FROM period" in sql:
                    return [{"period_id": 101, "month": 1}, {"period_id": 102, "month": 2}]
                if "FROM budget_data" in sql:
                    return [{"period_id": 101, "amount": 30.125}, {"period_id": 102, "amount": 40.0}]
                raise AssertionError(sql)

            async def fetch_one(self, sql, params=()):
                self.fetch_one_calls.append((sql, params))
                return {"version_id": 2026000003}

        async def run() -> None:
            fake_pool = FakePool()
            with patch.object(module, "get_pool", return_value=fake_pool):
                result = await load_expense_forecast_metric_source_month_map(
                    common_db_path=Path(settings.data_dir) / "common.db",
                    budget_db_path=Path(settings.data_dir) / "budget_2026.db",
                    year=2026,
                    indicator_code="marketing",
                    product_code="prd1",
                )

            self.assertEqual(result, {1: 30.12, 2: 40.0})
            self.assertEqual(fake_pool.fetch_one_calls[0][1], (2026,))
            budget_sql, budget_params = fake_pool.fetch_all_calls[2]
            self.assertIn("FROM budget_data", budget_sql)
            self.assertIn("budget_year = %s", budget_sql)
            self.assertEqual(budget_params, (2026000003, "ACCT_MKT_A", "ACCT_MKT_B", 2026, "PRD1"))

        asyncio.run(run())

    def test_metric_sources_do_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)

    def test_metric_source_reads_bound_budget_data_by_latest_version_and_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            common_db = Path(tmpdir) / "common.db"
            budget_db = Path(tmpdir) / "budget_2026.db"
            init_common_db(common_db)
            init_budget_db(budget_db)

            month_map = asyncio.run(
                load_expense_forecast_metric_source_month_map(
                    common_db_path=common_db,
                    budget_db_path=budget_db,
                    year=2026,
                    indicator_code="marketing",
                    product_code="prd1",
                )
            )

            self.assertEqual(month_map, {1: 30.12, 2: 30.0})

    def test_metric_source_returns_empty_without_bound_metric_or_budget_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            common_db = Path(tmpdir) / "common.db"
            init_common_db(common_db)

            no_metric = asyncio.run(
                load_expense_forecast_metric_source_month_map(
                    common_db_path=common_db,
                    budget_db_path=Path(tmpdir) / "budget_2026.db",
                    year=2026,
                    indicator_code="missing",
                    product_code="prd1",
                )
            )

            self.assertEqual(no_metric, {})


if __name__ == "__main__":
    unittest.main()
