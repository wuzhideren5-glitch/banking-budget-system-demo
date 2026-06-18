from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3
from unittest.mock import patch

from app.core.config import settings
from app.services import compare_summary_sync as compare_summary_sync_module
from app.services.compare_summary_sync import CompareSummarySyncService


class CompareSummarySyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_copies_selected_budget_summary_rows_to_compare_db(self) -> None:
        original_data_dir = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            try:
                common_path = data_dir / "common.db"
                budget_path = data_dir / "budget_2099.db"
                compare_path = data_dir / "compare.db"

                common_conn = sqlite3.connect(common_path)
                try:
                    common_conn.executescript(
                        """
                        CREATE TABLE databases (
                          id INTEGER PRIMARY KEY NOT NULL,
                          data_file_name TEXT NOT NULL,
                          year INTEGER NOT NULL
                        );
                        CREATE TABLE edit_show_version (
                          edit_show_sign INTEGER NOT NULL,
                          data_file_id INTEGER NOT NULL,
                          version_id INTEGER NOT NULL
                        );
                        INSERT INTO databases(id, data_file_name, year)
                        VALUES (7, 'budget_2099.db', 2099);
                        INSERT INTO edit_show_version(edit_show_sign, data_file_id, version_id)
                        VALUES (1, 7, 1);
                        """
                    )
                    common_conn.commit()
                finally:
                    common_conn.close()

                budget_conn = sqlite3.connect(budget_path)
                try:
                    budget_conn.executescript(
                        """
                        CREATE TABLE version (
                          version_id INTEGER PRIMARY KEY NOT NULL,
                          version_date_time TEXT NOT NULL,
                          version_name TEXT NOT NULL,
                          current_month INTEGER NOT NULL
                        );
                        CREATE TABLE budget_summary (
                          metric_level1 TEXT,
                          metric_level2 TEXT,
                          metric_level3 TEXT,
                          metric_level4 TEXT,
                          metric_level5 TEXT,
                          dept_level1 TEXT,
                          dept_level2 TEXT,
                          dept_level3 TEXT,
                          data_code_name TEXT NOT NULL,
                          product_code_name TEXT,
                          year TEXT NOT NULL,
                          month TEXT NOT NULL,
                          quarter TEXT NOT NULL,
                          budget_actual INTEGER NOT NULL,
                          version_id INTEGER NOT NULL,
                          version_name TEXT NOT NULL,
                          value REAL NOT NULL,
                          value_type TEXT NOT NULL,
                          value_source TEXT NOT NULL DEFAULT 'manual',
                          update_time TEXT NOT NULL
                        );
                        INSERT INTO version(version_id, version_date_time, version_name, current_month)
                        VALUES (1, '2099-01-01T00:00:00Z', 'V2099.01', 5);
                        INSERT INTO budget_summary(
                          metric_level1, metric_level2, metric_level3, metric_level4, metric_level5,
                          dept_level1, dept_level2, dept_level3, data_code_name, product_code_name,
                          year, month, quarter, budget_actual, version_id, version_name,
                          value, value_type, value_source, update_time
                        ) VALUES (
                          'A01 开鑫贷', 'A01.01 规模与余额', 'A01.01.01 日均指标', 'A01.01.01.001 日均余额', NULL,
                          'D01 零售金融部', NULL, NULL, 'A01.01.01.001 开鑫贷日均余额', 'A01 开鑫贷',
                          'Y2099', 'M05', 'Q2', 0, 1, 'V2099.01',
                          200, '金额', 'manual', '2099-01-01T00:00:00Z'
                        );
                        """
                    )
                    budget_conn.commit()
                finally:
                    budget_conn.close()

                compare_conn = sqlite3.connect(compare_path)
                try:
                    compare_conn.executescript(
                        """
                        CREATE TABLE compare_budget_summary (
                          show_level INTEGER NOT NULL,
                          data_file_id INTEGER NOT NULL,
                          source_year INTEGER NOT NULL,
                          source_version_id INTEGER NOT NULL,
                          source_version_name TEXT,
                          metric_level1 TEXT,
                          metric_level2 TEXT,
                          metric_level3 TEXT,
                          metric_level4 TEXT,
                          metric_level5 TEXT,
                          dept_level1 TEXT,
                          dept_level2 TEXT,
                          dept_level3 TEXT,
                          data_code_name TEXT NOT NULL,
                          product_code_name TEXT,
                          year TEXT NOT NULL,
                          month TEXT NOT NULL,
                          quarter TEXT NOT NULL,
                          budget_actual INTEGER NOT NULL,
                          value REAL NOT NULL,
                          value_type TEXT NOT NULL,
                          value_source TEXT NOT NULL DEFAULT 'manual',
                          sync_time TEXT NOT NULL
                        );
                        CREATE TABLE compare_sync_job_log (
                          job_id INTEGER PRIMARY KEY AUTOINCREMENT,
                          start_time TEXT NOT NULL,
                          end_time TEXT,
                          trigger_source TEXT NOT NULL,
                          status TEXT NOT NULL,
                          message TEXT,
                          operator_user_id INTEGER
                        );
                        """
                    )
                    compare_conn.commit()
                finally:
                    compare_conn.close()

                refresh_times: list[str] = []

                async def set_refresh_time(ts: str) -> None:
                    refresh_times.append(ts)

                service = CompareSummarySyncService(set_compare_refresh_time=set_refresh_time)

                result = await service.sync(trigger_source="unit-test", operator_user_id=42)

                conn = sqlite3.connect(compare_path)
                try:
                    rows = conn.execute(
                        """
                        SELECT show_level, data_file_id, source_year, source_version_id,
                               source_version_name, data_code_name, month, budget_actual, value
                        FROM compare_budget_summary
                        """
                    ).fetchall()
                    log_rows = conn.execute(
                        "SELECT trigger_source, status, operator_user_id FROM compare_sync_job_log"
                    ).fetchall()
                finally:
                    conn.close()

                self.assertEqual(result.inserted_rows, 1)
                self.assertEqual(result.selected_versions, 1)
                self.assertEqual(len(refresh_times), 1)
                self.assertEqual(
                    rows,
                    [
                        (
                            1,
                            7,
                            2099,
                            1,
                            "V2099.01",
                            "A01.01.01.001 开鑫贷日均余额",
                            "M05",
                            0,
                            200.0,
                        )
                    ],
                )
                self.assertEqual(log_rows, [("unit-test", "success", 42)])
            finally:
                settings.data_dir = original_data_dir

    async def test_sync_uses_mysql_for_runtime_paths(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []
                self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
                self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
                self.execute_many_calls: list[tuple[str, list[tuple[object, ...]]]] = []

            async def fetch_all(self, sql: str, params=()):
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((" ".join(sql.split()), tuple(params)))
                if "from edit_show_version" in normalized:
                    return [
                        {
                            "edit_show_sign": 1,
                            "data_file_id": 7,
                            "version_id": 2026000003,
                            "data_file_name": "budget_2026.db",
                            "year": 2026,
                        }
                    ]
                if "from budget_summary" in normalized:
                    return [
                        {
                            "metric_level1": "A01 开鑫贷",
                            "metric_level2": "A01.01 规模与余额",
                            "metric_level3": "A01.01.01 日均指标",
                            "metric_level4": "A01.01.01.001 日均余额",
                            "metric_level5": None,
                            "dept_level1": "D01 零售金融部",
                            "dept_level2": None,
                            "dept_level3": None,
                            "data_code_name": "A01.01.01.001 开鑫贷日均余额",
                            "product_code_name": "A01 开鑫贷",
                            "year": "Y2026",
                            "month": "M05",
                            "quarter": "Q2",
                            "budget_actual": 0,
                            "version_name": "V2026.04.17",
                            "value": 200.0,
                            "value_type": "金额",
                            "value_source": "manual",
                        }
                    ]
                raise AssertionError(f"Unexpected fetch_all SQL: {sql}")

            async def fetch_one(self, sql: str, params=()):
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((" ".join(sql.split()), tuple(params)))
                if "from version" in normalized:
                    return {"version_name": "V2026.04.17", "current_month": 4}
                if "count(*)" in normalized and "from budget_summary" in normalized:
                    return {"row_count": 1}
                raise AssertionError(f"Unexpected fetch_one SQL: {sql}")

            async def execute(self, sql: str, params=()):
                self.execute_calls.append((" ".join(sql.split()), tuple(params)))
                return 1

            async def execute_many(self, sql: str, rows):
                materialized = [tuple(row) for row in rows]
                self.execute_many_calls.append((" ".join(sql.split()), materialized))
                return len(materialized)

        refresh_times: list[str] = []

        async def set_refresh_time(ts: str) -> None:
            refresh_times.append(ts)

        fake_pool = FakePool()
        service = CompareSummarySyncService(set_compare_refresh_time=set_refresh_time)

        with patch.object(compare_summary_sync_module, "get_pool", return_value=fake_pool):
            result = await service.sync(trigger_source="mysql-test", operator_user_id=42)

        self.assertEqual(result.inserted_rows, 1)
        self.assertEqual(result.selected_versions, 1)
        self.assertEqual(len(refresh_times), 1)
        self.assertTrue(any("DELETE FROM compare_budget_summary" in sql for sql, _ in fake_pool.execute_calls))
        self.assertEqual(len(fake_pool.execute_many_calls), 1)
        insert_sql, inserted_rows = fake_pool.execute_many_calls[0]
        self.assertIn("INSERT INTO compare_budget_summary", insert_sql)
        self.assertEqual(inserted_rows[0][3], 2026000003)
        self.assertEqual(inserted_rows[0][19], 200.0)
        version_sql, version_params = next(
            (sql, params)
            for sql, params in fake_pool.fetch_one_calls
            if "FROM version" in sql
        )
        self.assertIn("budget_year = %s", version_sql)
        self.assertEqual(version_params, (2026000003, 2026))
        summary_sql, summary_params = next(
            (sql, params)
            for sql, params in fake_pool.fetch_all_calls
            if "FROM budget_summary" in sql
        )
        self.assertIn("budget_year = %s", summary_sql)
        self.assertEqual(summary_params, (2026000003, 2026))

    def test_compare_summary_sync_service_does_not_import_aiosqlite(self) -> None:
        source = Path(compare_summary_sync_module.__file__).read_text(encoding="utf-8")

        self.assertNotIn("aiosqlite_compat", source)
        self.assertNotIn("import aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
