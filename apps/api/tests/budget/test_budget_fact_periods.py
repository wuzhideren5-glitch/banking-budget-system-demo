from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

import aiosqlite

from app.services import budget_fact_periods
from app.services.budget_fact_periods import (
    load_budget_fact_period_context,
    load_budget_fact_period_month_map_from_path,
    load_budget_fact_period_month_map_sync,
)


async def build_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(":memory:")
    await db.executescript(
        """
        CREATE TABLE period (
          period_id INTEGER PRIMARY KEY,
          year TEXT NOT NULL,
          month TEXT NOT NULL
        );
        INSERT INTO period(period_id, year, month)
        VALUES
          (3, 'Y2026', '3月'),
          (1, 'Y2026', '1月'),
          (2, 'Y2026', '2月'),
          (9, 'Y2025', '9月');
        """
    )
    return db


class BudgetFactPeriodTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        db = getattr(self, "db", None)
        if db is not None:
            await db.close()

    async def test_load_period_context_orders_periods_and_marks_editable_allowed_months(self) -> None:
        self.db = await build_db()

        context = await load_budget_fact_period_context(
            self.db,
            year_label="Y2026",
            current_month=2,
            budget_actual=1,
        )

        self.assertEqual([period.period_id for period in context.periods], [1, 2, 3])
        self.assertEqual([period.month_index for period in context.periods], [1, 2, 3])
        self.assertEqual([period.editable for period in context.periods], [True, False, False])
        self.assertEqual(context.period_ids, [1, 2, 3])
        self.assertEqual(context.month_by_period_id, {1: 1, 2: 2, 3: 3})
        self.assertEqual(context.allowed_period_ids, [1])

    def test_budget_fact_month_rules_belong_to_period_module(self) -> None:
        self.assertTrue(hasattr(budget_fact_periods, "budget_fact_month_index"))
        self.assertTrue(hasattr(budget_fact_periods, "is_budget_fact_month_editable"))

        self.assertEqual(budget_fact_periods.budget_fact_month_index("M03"), 3)
        self.assertEqual(budget_fact_periods.budget_fact_month_index("3月"), 3)

        self.assertFalse(
            budget_fact_periods.is_budget_fact_month_editable(
                current_month=4, budget_actual=0, month_index=3
            )
        )
        self.assertTrue(
            budget_fact_periods.is_budget_fact_month_editable(
                current_month=4, budget_actual=0, month_index=4
            )
        )
        self.assertTrue(
            budget_fact_periods.is_budget_fact_month_editable(
                current_month=4, budget_actual=1, month_index=3
            )
        )
        self.assertFalse(
            budget_fact_periods.is_budget_fact_month_editable(
                current_month=4, budget_actual=1, month_index=4
            )
        )

    async def test_load_period_month_map_sync_filters_to_valid_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE period (
                      period_id INTEGER PRIMARY KEY,
                      year TEXT NOT NULL,
                      month TEXT NOT NULL
                    );
                    INSERT INTO period(period_id, year, month)
                    VALUES
                      (3, 'Y2026', '3月'),
                      (1, 'Y2026', '1月'),
                      (2, 'Y2026', '2月'),
                      (13, 'Y2026', '13月'),
                      (99, 'Y2026', '无效'),
                      (9, 'Y2025', '9月');
                    """
                )

                month_map = load_budget_fact_period_month_map_sync(
                    conn,
                    year_label="Y2026",
                )

        self.assertEqual(month_map, {1: 1, 2: 2, 3: 3})

    async def test_load_period_month_map_from_path_filters_to_valid_months(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "common.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE period (
                      period_id INTEGER PRIMARY KEY,
                      year TEXT NOT NULL,
                      month TEXT NOT NULL
                    );
                    INSERT INTO period(period_id, year, month)
                    VALUES
                      (3, 'Y2026', '3月'),
                      (1, 'Y2026', '1月'),
                      (2, 'Y2026', '2月'),
                      (13, 'Y2026', '13月'),
                      (9, 'Y2025', '9月');
                    """
                )

            month_map = await load_budget_fact_period_month_map_from_path(
                db_path,
                year=2026,
            )

        self.assertEqual(month_map, {1: 1, 2: 2, 3: 3})

    def test_main_no_longer_keeps_period_months_sql_helper(self) -> None:
        main_source = (Path(__file__).parent / "app" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("async def _get_year_period_months", main_source)
        self.assertNotIn("SELECT period_id, month", main_source)


if __name__ == "__main__":
    unittest.main()
