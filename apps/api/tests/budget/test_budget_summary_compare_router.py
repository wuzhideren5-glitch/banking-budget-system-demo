from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import settings
from app.routers import budget_summary_compare as module


class BudgetSummaryCompareRouterStorageTests(unittest.TestCase):
    def test_budget_version_month_map_uses_mysql_for_runtime_budget_db(self) -> None:
        class FakePool:
            async def fetch_all(self, sql, params=()):
                self.sql = sql
                self.params = params
                return [
                    {"version_id": 1, "current_month": 6},
                    {"version_id": 2, "current_month": 13},
                ]

        async def run() -> None:
            fake_pool = FakePool()
            runtime_budget_path = Path(settings.data_dir) / "budget_2099.db"
            with patch.object(module, "get_pool", return_value=fake_pool):
                result = await module.load_budget_version_month_map(runtime_budget_path)

            self.assertEqual(result, {1: 6, 2: 13})
            self.assertIn("FROM version", fake_pool.sql)
            self.assertIn("budget_year", fake_pool.sql)
            self.assertEqual(fake_pool.params, (2099,))

        asyncio.run(run())

    def test_budget_version_month_map_keeps_sqlite_for_temp_budget_db(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                budget_path = Path(tmp) / "budget_2099.db"
                with sqlite3.connect(budget_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE version (
                          version_id INTEGER PRIMARY KEY,
                          version_date_time TEXT NOT NULL,
                          version_name TEXT NOT NULL,
                          current_month INTEGER NOT NULL
                        );
                        INSERT INTO version(version_id, version_date_time, version_name, current_month)
                        VALUES (3, '2099-01-01T00:00:00', 'V2099.03', 7);
                        """
                    )

                result = await module.load_budget_version_month_map(budget_path)

            self.assertEqual(result, {3: 7})

        asyncio.run(run())

    def test_compare_sync_latest_status_uses_mysql_for_runtime_compare_db(self) -> None:
        class FakePool:
            async def fetch_one(self, sql, params=()):
                self.sql = sql
                self.params = params
                return {
                    "job_id": 9,
                    "start_time": "2026-06-18T01:00:00",
                    "end_time": "2026-06-18T01:01:00",
                    "trigger_source": "unit-test",
                    "status": "success",
                    "message": "ok",
                }

        async def run() -> None:
            fake_pool = FakePool()
            runtime_compare_path = Path(settings.data_dir) / "compare.db"
            with patch.object(module, "get_pool", return_value=fake_pool):
                result = await module.load_compare_sync_latest_status(runtime_compare_path)

            self.assertEqual(result.job_id, 9)
            self.assertEqual(result.trigger_source, "unit-test")
            self.assertEqual(result.status, "success")
            self.assertIn("FROM compare_sync_job_log", fake_pool.sql)
            self.assertEqual(fake_pool.params, ())

        asyncio.run(run())

    def test_compare_sync_latest_status_keeps_sqlite_for_temp_compare_db(self) -> None:
        async def run() -> None:
            with tempfile.TemporaryDirectory() as tmp:
                compare_path = Path(tmp) / "compare.db"
                with sqlite3.connect(compare_path) as conn:
                    conn.executescript(
                        """
                        CREATE TABLE compare_sync_job_log (
                          job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                          start_time TEXT NOT NULL,
                          end_time TEXT,
                          trigger_source TEXT NOT NULL,
                          status TEXT NOT NULL,
                          message TEXT,
                          operator_user_id INTEGER
                        );
                        INSERT INTO compare_sync_job_log(
                          start_time, end_time, trigger_source, status, message, operator_user_id
                        ) VALUES
                          ('2026-06-18T01:00:00', NULL, 'older', 'failed', 'bad', 1),
                          ('2026-06-18T02:00:00', '2026-06-18T02:01:00', 'latest', 'success', 'ok', 2);
                        """
                    )

                result = await module.load_compare_sync_latest_status(compare_path)

            self.assertEqual(result.job_id, 2)
            self.assertEqual(result.trigger_source, "latest")
            self.assertEqual(result.status, "success")
            self.assertEqual(result.message, "ok")

        asyncio.run(run())

    def test_budget_summary_compare_router_does_not_import_aiosqlite(self) -> None:
        source = Path(module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
