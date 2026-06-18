from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3
from unittest.mock import patch

from app.services import annual_aggregation as annual_aggregation_module
from app.services.annual_aggregation import (
    aggregate_single_metric,
    compute_annual,
    refresh_annual_aggregates_for_products,
    upsert_annual_aggregate,
)


class _FakeAnnualAggregationMysqlPool:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    async def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized_sql = " ".join(sql.lower().split())
        self.fetch_all_calls.append((" ".join(sql.split()), params))
        if "from data_account_metric_node" in normalized_sql:
            return [
                {
                    "node_code": "A01.01.001",
                    "annual_agg_rule": "SUM",
                    "product_code": "A01",
                }
            ]
        if "from budget_data" in normalized_sql:
            return [
                {"month": "M01", "value": 10},
                {"month": "M02", "value": 15},
            ]
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class AnnualAggregationTests(unittest.IsolatedAsyncioTestCase):
    def test_compute_annual_rules(self) -> None:
        values = [1.0, 2.0, 0.0, 4.0]

        self.assertEqual(compute_annual(values, "SUM"), 7.0)
        self.assertEqual(compute_annual(values, "AVG"), 7.0 / 3.0)
        self.assertEqual(compute_annual(values, "LAST"), 4.0)
        self.assertIsNone(compute_annual(values, ""))

    async def test_aggregate_single_metric_supports_non_runtime_sqlite_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            common_path = root / "fixture_common.sqlite"
            budget_path = root / "fixture_budget.sqlite"
            with sqlite3.connect(common_path) as db:
                db.executescript(
                    """
                    CREATE TABLE data_account_metric_node (
                      node_code TEXT PRIMARY KEY,
                      annual_agg_rule TEXT NOT NULL
                    );
                    CREATE TABLE data_account_metric_binding (
                      metric_node_code TEXT NOT NULL,
                      data_acct_code TEXT NOT NULL,
                      is_active INTEGER NOT NULL
                    );
                    CREATE TABLE period (
                      period_id INTEGER PRIMARY KEY,
                      year TEXT NOT NULL,
                      month TEXT NOT NULL
                    );
                    INSERT INTO data_account_metric_node(node_code, annual_agg_rule)
                    VALUES ('A01.01.001', 'SUM');
                    INSERT INTO data_account_metric_binding(metric_node_code, data_acct_code, is_active)
                    VALUES ('A01.01.001', 'A01.01.001', 1);
                    INSERT INTO period(period_id, year, month)
                    VALUES (1, 'Y2099', 'M01'), (2, 'Y2099', 'M02');
                    """
                )
            with sqlite3.connect(budget_path) as db:
                db.executescript(
                    """
                    CREATE TABLE budget_data (
                      data_acct_code TEXT NOT NULL,
                      period_id INTEGER NOT NULL,
                      budget_actual INTEGER NOT NULL,
                      value REAL NOT NULL
                    );
                    INSERT INTO budget_data(data_acct_code, period_id, budget_actual, value)
                    VALUES ('A01.01.001', 1, 0, 10), ('A01.01.001', 2, 0, 15);
                    """
                )

            result = await aggregate_single_metric(
                common_path,
                budget_path,
                "A01.01.001",
                budget_actual=0,
                year=2099,
            )

        self.assertEqual(result.rule, "SUM")
        self.assertEqual(result.month_count, 2)
        self.assertEqual(result.annual_value, 25.0)

    async def test_upsert_annual_aggregate_uses_mysql_for_runtime_budget_db(self) -> None:
        original_data_dir = annual_aggregation_module.settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            annual_aggregation_module.settings.data_dir = Path(tmp)
            fake_pool = _FakeAnnualAggregationMysqlPool()
            budget_path = Path(tmp) / "budget_2099.db"
            try:
                with patch.object(annual_aggregation_module, "get_pool", return_value=fake_pool):
                    await upsert_annual_aggregate(
                        budget_path=budget_path,
                        data_acct_code="a01.01.001",
                        product_code="A01",
                        year=2099,
                        budget_actual=0,
                        version_id=7,
                        annual_value=25.0,
                        agg_rule="SUM",
                        month_count=2,
                    )
            finally:
                annual_aggregation_module.settings.data_dir = original_data_dir

        all_sql = "\n".join(sql for sql, _params in fake_pool.executed)
        self.assertIn("CREATE TABLE IF NOT EXISTS budget_annual_aggregate", all_sql)
        self.assertIn("budget_year INT NOT NULL", all_sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", all_sql)
        insert_calls = [
            (sql, params)
            for sql, params in fake_pool.executed
            if "INSERT INTO budget_annual_aggregate" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        self.assertEqual(insert_calls[0][1][:6], (2099, "A01.01.001", "A01", 2099, 0, 7))

    async def test_refresh_annual_aggregates_uses_mysql_and_filters_runtime_scope(self) -> None:
        original_data_dir = annual_aggregation_module.settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            annual_aggregation_module.settings.data_dir = Path(tmp)
            fake_pool = _FakeAnnualAggregationMysqlPool()
            common_path = Path(tmp) / "common.db"
            budget_path = Path(tmp) / "budget_2099.db"
            try:
                with patch.object(annual_aggregation_module, "get_pool", return_value=fake_pool):
                    result = await refresh_annual_aggregates_for_products(
                        common_path=common_path,
                        budget_path=budget_path,
                        product_codes=["A01"],
                        budget_actuals=[0],
                        year=2099,
                        version_id=7,
                    )
            finally:
                annual_aggregation_module.settings.data_dir = original_data_dir

        self.assertEqual(result, {"refreshed": 1})
        monthly_sql, monthly_params = next(
            (sql, params)
            for sql, params in fake_pool.fetch_all_calls
            if "FROM budget_data" in sql
        )
        self.assertIn("bd.budget_year = %s", monthly_sql)
        self.assertIn("bd.version_id = %s", monthly_sql)
        self.assertNotIn("ATTACH", monthly_sql.upper())
        self.assertEqual(monthly_params, ("A01.01.001", 0, 2099, "Y2099", 7))
        insert_calls = [
            (sql, params)
            for sql, params in fake_pool.executed
            if "INSERT INTO budget_annual_aggregate" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        self.assertEqual(insert_calls[0][1][6], 25.0)

    def test_annual_aggregation_service_does_not_import_aiosqlite(self) -> None:
        source = Path(annual_aggregation_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
