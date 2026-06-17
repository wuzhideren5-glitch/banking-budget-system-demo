from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sqlite3

from app.core.config import settings
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


if __name__ == "__main__":
    unittest.main()
