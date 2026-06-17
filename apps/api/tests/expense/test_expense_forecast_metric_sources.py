from __future__ import annotations

import asyncio
import sqlite3
import tempfile
from pathlib import Path
import unittest

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
            INSERT INTO data_account_metric_node(node_code, functional_group_code, local_metric_code)
            VALUES (?, ?, ?)
            """,
            [
                ("PRD1.MKT", "MARKETING", "MKT"),
                ("PRD1.OPS", "OPERATIONS", "OPS"),
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
