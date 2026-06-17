from __future__ import annotations

from datetime import date
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.agent_compare_sql import strip_year_constraints, suggest_compare_l1_sql


class AgentCompareSqlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.common_db = root / "common.db"
        self.compare_db = root / "compare.db"
        self._create_common_db()
        self._create_compare_db()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create_common_db(self) -> None:
        with sqlite3.connect(self.common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE databases(
                    id INTEGER PRIMARY KEY,
                    year INTEGER,
                    data_file_name TEXT
                );
                CREATE TABLE edit_show_version(
                    id INTEGER PRIMARY KEY,
                    data_file_id INTEGER,
                    edit_show_sign INTEGER,
                    version_id INTEGER
                );

                INSERT INTO databases(id, year, data_file_name) VALUES (1, 2026, 'base');
                INSERT INTO databases(id, year, data_file_name) VALUES (2, 2025, 'compare');
                INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id) VALUES (1, 1, 1, 101);
                INSERT INTO edit_show_version(id, data_file_id, edit_show_sign, version_id) VALUES (2, 2, 2, 202);
                """
            )

    def _create_compare_db(self) -> None:
        with sqlite3.connect(self.compare_db) as conn:
            conn.executescript(
                """
                CREATE TABLE compare_budget_summary(
                    show_level INTEGER,
                    source_year INTEGER,
                    source_version_id INTEGER,
                    source_version_name TEXT
                );

                INSERT INTO compare_budget_summary VALUES (1, 2026, 101, 'base');
                INSERT INTO compare_budget_summary VALUES (2, 2025, 202, 'last_year');
                """
            )

    def test_strip_year_constraints_keeps_month_and_quarter_filters(self) -> None:
        sql = " AND (year = 'Y2026' AND month IN ('M01','M02')) AND year = 'Y2026'"

        stripped = strip_year_constraints(sql)

        self.assertNotIn("year = 'Y2026'", stripped)
        self.assertIn("month IN ('M01','M02')", stripped)

    def test_yoy_sql_uses_base_l1_and_selected_compare_level(self) -> None:
        sql = suggest_compare_l1_sql(
            "按部门看同比",
            year_tag="Y2026",
            month_tag="M05",
            show_level=2,
            state={
                "clarified_slots": {"comparison_type": "yoy", "comparison_show_level": 2},
                "query_base_year_tag": "Y2026",
                "query_compare_year_tag": "Y2025",
                "pm_query_spec": {"year": "Y2026", "month": "M05"},
            },
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertIn("WITH base AS", sql)
        self.assertIn("show_level = 1 AND year = 'Y2026'", sql)
        self.assertIn("show_level = 2 AND year = 'Y2025'", sql)
        self.assertIn("SELECT dept_level1, month", sql)
        self.assertIn("同比变化比例(%)", sql)
        self.assertIn("month = 'M05'", sql)

    def test_compare_year_falls_back_to_compare_level_metadata(self) -> None:
        sql = suggest_compare_l1_sql(
            "看同比",
            year_tag="Y2026",
            month_tag=None,
            show_level=2,
            state={"clarified_slots": {"comparison_type": "yoy", "comparison_show_level": 2}},
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertIn("show_level = 2 AND year = 'Y2025'", sql)

    def test_metric_only_scope_keeps_report_scope_and_budget_actual_columns(self) -> None:
        sql = suggest_compare_l1_sql(
            "按部门展示预算实际两列",
            year_tag="Y2026",
            month_tag="M05",
            show_level=1,
            state={"pm_query_spec": {"metric_nodes": [{"code": "A03.03", "name": "净利息收入"}]}},
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertIn("'A03.03 净利息收入' AS report_scope", sql)
        self.assertIn("dept_level1, month", sql)
        self.assertIn("AS '预算值'", sql)
        self.assertIn("AS '实际值'", sql)
        self.assertIn("WHERE show_level = 1 AND year = 'Y2026' AND month = 'M05'", sql)

    def test_default_compare_sql_groups_by_data_product_and_month(self) -> None:
        sql = suggest_compare_l1_sql(
            "看趋势",
            year_tag="Y2026",
            month_tag=None,
            show_level=1,
            state={},
            compare_db=self.compare_db,
            common_db=self.common_db,
            today=date(2026, 6, 1),
        )

        self.assertIn("SELECT data_code_name, product_code_name, month, SUM(value) AS total_value", sql)
        self.assertIn("GROUP BY data_code_name, product_code_name, month", sql)
        self.assertIn("FROM compare_budget_summary WHERE show_level = 1 AND year = 'Y2026'", sql)


if __name__ == "__main__":
    unittest.main()
