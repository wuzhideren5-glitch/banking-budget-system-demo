from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.agent_query_context import resolve_compare_query_context


class AgentQueryContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.common_db = root / "common.db"
        self.compare_db = root / "compare.db"
        self.anchor = {"calendar_year": 2026, "year_tag": "Y2026", "month_tag": "M05"}
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

                INSERT INTO databases(id, year, data_file_name) VALUES (1, 2026, 'base_file');
                INSERT INTO databases(id, year, data_file_name) VALUES (2, 2025, 'compare_file');
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

    def test_non_yoy_query_uses_base_l1_context(self) -> None:
        ctx = resolve_compare_query_context(
            {"user_query": "看收入趋势", "clarified_slots": {"comparison_show_level": 2}},
            anchor=self.anchor,
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(ctx["query_db_path"], str(self.compare_db))
        self.assertEqual(ctx["query_data_source"], "compare_l1")
        self.assertEqual(ctx["query_show_level"], 1)
        self.assertEqual(ctx["query_version_id"], 101)
        self.assertEqual(ctx["query_base_version_id"], 101)
        self.assertEqual(ctx["query_compare_version_id"], 202)
        self.assertEqual(ctx["query_base_year_tag"], "Y2026")
        self.assertEqual(ctx["query_compare_year_tag"], "Y2025")
        self.assertEqual(ctx["query_month_tag"], "M05")

    def test_yoy_query_uses_selected_compare_level(self) -> None:
        ctx = resolve_compare_query_context(
            {"user_query": "看同比", "clarified_slots": {"comparison_type": "yoy", "comparison_show_level": 2}},
            anchor=self.anchor,
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(ctx["query_show_level"], 2)
        self.assertEqual(ctx["query_version_id"], 202)
        self.assertEqual(ctx["query_year_tag"], "Y2026")
        self.assertIn("基准L1: Y2026/V101", ctx["query_version_source"])
        self.assertIn("比较L2: Y2025/V202", ctx["query_version_source"])

    def test_missing_compare_db_keeps_compare_contract_without_budget_fallback(self) -> None:
        self.compare_db.unlink()

        ctx = resolve_compare_query_context(
            {"user_query": "看同比", "pm_query_spec": {"__selected_compare_level__": 2}},
            anchor=self.anchor,
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(ctx["query_db_path"], str(self.compare_db))
        self.assertEqual(ctx["query_data_source"], "compare_l1")
        self.assertEqual(ctx["query_show_level"], 2)
        self.assertEqual(ctx["query_version_id"], 202)
        self.assertEqual(ctx["query_version_source"], "compare.db 缺失（当前要求仅使用 compare 库）")
        self.assertEqual(ctx["query_base_year_tag"], "Y2026")
        self.assertEqual(ctx["query_compare_year_tag"], "Y2025")


if __name__ == "__main__":
    unittest.main()
