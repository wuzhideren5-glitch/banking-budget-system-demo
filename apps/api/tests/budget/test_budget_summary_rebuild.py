from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from app.core.config import settings
import app.services.budget_summary_rebuild as budget_summary_rebuild_module
from app.services.budget_summary_rebuild import rebuild_budget_summary_for_version


class BudgetSummaryRebuildTests(unittest.IsolatedAsyncioTestCase):
    async def test_rebuild_budget_summary_uses_metric_tree_and_month_window(self) -> None:
        original_data_dir = settings.data_dir
        original_budget_year = settings.budget_year
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            settings.budget_year = 2099
            try:
                common_path = data_dir / "common.db"
                budget_path = data_dir / "budget_2099.db"
                common_conn = sqlite3.connect(common_path)
                try:
                    common_conn.executescript(
                        """
                        CREATE TABLE data_account (
                          data_acct_code TEXT PRIMARY KEY NOT NULL,
                          data_acct_name TEXT NOT NULL,
                          value_type TEXT NOT NULL
                        );
                        CREATE TABLE org_product_tree_snapshot (
                          id INTEGER PRIMARY KEY CHECK (id = 1),
                          payload_json TEXT NOT NULL,
                          updated_at TEXT NOT NULL
                        );
                        CREATE TABLE period (
                          period_id INTEGER PRIMARY KEY NOT NULL,
                          year TEXT NOT NULL,
                          month TEXT NOT NULL,
                          quarter TEXT NOT NULL
                        );
                        CREATE TABLE data_account_metric_node (
                          node_code TEXT PRIMARY KEY NOT NULL,
                          node_name TEXT NOT NULL,
                          parent_code TEXT,
                          level INTEGER NOT NULL,
                          sort_order INTEGER NOT NULL,
                          is_active INTEGER NOT NULL
                        );
                        CREATE TABLE data_account_metric_binding (
                          metric_node_code TEXT NOT NULL,
                          data_acct_code TEXT NOT NULL,
                          scope_code TEXT NOT NULL,
                          sort_order INTEGER NOT NULL DEFAULT 0,
                          is_active INTEGER NOT NULL
                        );
                        CREATE TABLE dept_account (
                          dept_code TEXT PRIMARY KEY NOT NULL,
                          dept_name TEXT NOT NULL,
                          parent_code TEXT
                        );
                        INSERT INTO data_account(data_acct_code, data_acct_name, value_type)
                        VALUES ('A01.01.01.001', '开鑫贷日均余额', '金额');
                        INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                        VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}', 'now');
                        INSERT INTO period(period_id, year, month, quarter)
                        VALUES (4, 'Y2099', 'M04', 'Q2'), (5, 'Y2099', 'M05', 'Q2');
                        INSERT INTO data_account_metric_node(
                          node_code, node_name, parent_code, level, sort_order, is_active
                        ) VALUES
                          ('A01', '开鑫贷', NULL, 1, 1, 1),
                          ('A01.01', '规模与余额', 'A01', 2, 1, 1),
                          ('A01.01.01', '日均指标', 'A01.01', 3, 1, 1),
                          ('A01.01.01.001', '日均余额', 'A01.01.01', 4, 1, 1);
                        INSERT INTO data_account_metric_binding(
                          metric_node_code, data_acct_code, scope_code, sort_order, is_active
                        ) VALUES ('A01.01.01.001', 'A01.01.01.001', 'A01', 1, 1);
                        INSERT INTO dept_account(dept_code, dept_name, parent_code)
                        VALUES ('D01', '零售金融部', NULL);
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
                        CREATE TABLE budget_data (
                          data_acct_code TEXT NOT NULL,
                          product_code TEXT NOT NULL,
                          period_id INTEGER NOT NULL,
                          budget_actual INTEGER NOT NULL,
                          version_id INTEGER NOT NULL,
                          value REAL NOT NULL,
                          value_source TEXT NOT NULL DEFAULT 'manual'
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
                        INSERT INTO budget_data(
                          data_acct_code, product_code, period_id, budget_actual, version_id, value, value_source
                        ) VALUES
                          ('A01.01.01.001', 'A01', 4, 1, 1, 100, 'manual'),
                          ('A01.01.01.001', 'A01', 4, 0, 1, 999, 'manual'),
                          ('A01.01.01.001', 'A01', 5, 0, 1, 200, 'formula');
                        """
                    )
                    budget_conn.commit()
                finally:
                    budget_conn.close()

                inserted = await rebuild_budget_summary_for_version(1, budget_path)

                conn = sqlite3.connect(budget_path)
                try:
                    rows = conn.execute(
                        """
                        SELECT metric_level1, metric_level2, metric_level3,
                               dept_level1, data_code_name, product_code_name,
                               month, budget_actual, value, value_source
                        FROM budget_summary
                        ORDER BY month
                        """
                    ).fetchall()
                finally:
                    conn.close()

                self.assertEqual(inserted, 2)
                self.assertEqual(
                    rows,
                    [
                        (
                            "A01 开鑫贷",
                            "A01.01 规模与余额",
                            "A01.01.01 日均指标",
                            None,
                            "A01.01.01.001 开鑫贷日均余额",
                            "A01 开鑫贷",
                            "M04",
                            1,
                            100.0,
                            "manual",
                        ),
                        (
                            "A01 开鑫贷",
                            "A01.01 规模与余额",
                            "A01.01.01 日均指标",
                            None,
                            "A01.01.01.001 开鑫贷日均余额",
                            "A01 开鑫贷",
                            "M05",
                            0,
                            200.0,
                            "formula",
                        ),
                    ],
                )
            finally:
                settings.data_dir = original_data_dir
                settings.budget_year = original_budget_year

    async def test_rebuild_budget_summary_rejects_old_budget_data_without_value_source(self) -> None:
        original_data_dir = settings.data_dir
        original_budget_year = settings.budget_year
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            settings.data_dir = data_dir
            settings.budget_year = 2099
            try:
                common_path = data_dir / "common.db"
                budget_path = data_dir / "budget_2099.db"
                common_conn = sqlite3.connect(common_path)
                try:
                    common_conn.executescript(
                        """
                        CREATE TABLE data_account (
                          data_acct_code TEXT PRIMARY KEY NOT NULL,
                          data_acct_name TEXT NOT NULL,
                          value_type TEXT NOT NULL
                        );
                        CREATE TABLE org_product_tree_snapshot (
                          id INTEGER PRIMARY KEY CHECK (id = 1),
                          payload_json TEXT NOT NULL,
                          updated_at TEXT NOT NULL
                        );
                        INSERT INTO org_product_tree_snapshot(id, payload_json, updated_at)
                        VALUES(1, '{"code":"AA","name":"微众银行","children":[{"code":"A","name":"个金群","children":[{"code":"A01","name":"开鑫贷","children":[]}]}]}', 'now');
                        CREATE TABLE period (
                          period_id INTEGER PRIMARY KEY NOT NULL,
                          year TEXT NOT NULL,
                          month TEXT NOT NULL,
                          quarter TEXT NOT NULL
                        );
                        CREATE TABLE data_account_metric_node (
                          node_code TEXT PRIMARY KEY NOT NULL,
                          node_name TEXT NOT NULL,
                          parent_code TEXT,
                          level INTEGER NOT NULL,
                          sort_order INTEGER NOT NULL,
                          is_active INTEGER NOT NULL
                        );
                        CREATE TABLE data_account_metric_binding (
                          metric_node_code TEXT NOT NULL,
                          data_acct_code TEXT NOT NULL,
                          scope_code TEXT NOT NULL,
                          sort_order INTEGER NOT NULL DEFAULT 0,
                          is_active INTEGER NOT NULL
                        );
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
                        CREATE TABLE budget_data (
                          data_acct_code TEXT NOT NULL,
                          product_code TEXT NOT NULL,
                          period_id INTEGER NOT NULL,
                          budget_actual INTEGER NOT NULL,
                          version_id INTEGER NOT NULL,
                          value REAL NOT NULL
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
                        """
                    )
                    budget_conn.commit()
                finally:
                    budget_conn.close()

                with self.assertRaisesRegex(RuntimeError, "value_source"):
                    await rebuild_budget_summary_for_version(1, budget_path)
            finally:
                settings.data_dir = original_data_dir
                settings.budget_year = original_budget_year

    async def test_rebuild_budget_summary_uses_mysql_for_runtime_budget_path(self) -> None:
        class FakePool:
            def __init__(self) -> None:
                self.executed: list[tuple[str, tuple[object, ...]]] = []
                self.executed_many: list[tuple[str, list[tuple[object, ...]]]] = []

            async def fetch_one(self, sql, params=()):
                if "FROM version" in sql:
                    return {"version_name": "V2026.01", "current_month": 5}
                return None

            async def fetch_all(self, sql, params=()):
                if "INFORMATION_SCHEMA.COLUMNS" in sql:
                    return [{"COLUMN_NAME": "value_source"}]
                if "FROM data_account\n" in sql:
                    return [
                        {
                            "data_acct_code": "A01.01.01.001",
                            "data_acct_name": "开鑫贷日均余额",
                            "value_type": "金额",
                        }
                    ]
                if "FROM org_product_runtime_products" in sql:
                    return [{"product_code": "A01", "product_name": "开鑫贷"}]
                if "FROM period" in sql:
                    return [
                        {"period_id": 4, "year": "Y2026", "month": "M04", "quarter": "Q2"},
                        {"period_id": 5, "year": "Y2026", "month": "M05", "quarter": "Q2"},
                    ]
                if "FROM data_account_metric_node" in sql:
                    return [
                        {"node_code": "A01", "node_name": "开鑫贷", "parent_code": None, "level": 1, "sort_order": 1},
                        {"node_code": "A01.01", "node_name": "规模与余额", "parent_code": "A01", "level": 2, "sort_order": 1},
                        {"node_code": "A01.01.01", "node_name": "日均指标", "parent_code": "A01.01", "level": 3, "sort_order": 1},
                        {"node_code": "A01.01.01.001", "node_name": "日均余额", "parent_code": "A01.01.01", "level": 4, "sort_order": 1},
                    ]
                if "FROM data_account_metric_binding" in sql:
                    return [
                        {
                            "metric_node_code": "A01.01.01.001",
                            "data_acct_code": "A01.01.01.001",
                            "scope_code": "A01",
                            "node_sort_order": 1,
                            "binding_sort_order": 1,
                            "node_level": 4,
                        }
                    ]
                if "FROM budget_data" in sql:
                    return [
                        {
                            "data_acct_code": "A01.01.01.001",
                            "product_code": "A01",
                            "period_id": 4,
                            "budget_actual": 1,
                            "value": 100,
                            "value_source": "manual",
                        },
                        {
                            "data_acct_code": "A01.01.01.001",
                            "product_code": "A01",
                            "period_id": 5,
                            "budget_actual": 0,
                            "value": 200,
                            "value_source": "formula",
                        },
                    ]
                return []

            async def execute(self, sql, params=()):
                self.executed.append((sql, tuple(params)))
                return 1

            async def execute_many(self, sql, rows):
                self.executed_many.append((sql, list(rows)))
                return len(rows)

        fake_pool = FakePool()
        previous_get_pool = budget_summary_rebuild_module.get_pool
        budget_summary_rebuild_module.get_pool = lambda: fake_pool
        try:
            inserted = await rebuild_budget_summary_for_version(
                2026000003,
                Path(settings.data_dir) / "budget_2026.db",
            )
        finally:
            budget_summary_rebuild_module.get_pool = previous_get_pool

        self.assertEqual(inserted, 2)
        self.assertTrue(any("budget_year = %s" in sql and "DELETE FROM budget_summary" in sql for sql, _ in fake_pool.executed))
        self.assertEqual(len(fake_pool.executed_many), 1)
        insert_sql, rows = fake_pool.executed_many[0]
        self.assertIn("budget_year", insert_sql)
        self.assertEqual(rows[0][0], 2026)

    def test_budget_summary_rebuild_service_does_not_import_aiosqlite(self) -> None:
        source = Path(budget_summary_rebuild_module.__file__).read_text(encoding="utf-8")
        self.assertNotIn("aiosqlite", source)


if __name__ == "__main__":
    unittest.main()
