from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.agent_pivot_suggestion import (
    append_reply_options_footer,
    build_pivot_suggestion,
    build_plan_reply_options,
    should_recommend_pivot,
)


class AgentPivotSuggestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.common_db = Path(self.tmp.name) / "common.db"
        with sqlite3.connect(self.common_db) as conn:
            conn.executescript(
                """
                CREATE TABLE data_account_metric_node(
                    node_code TEXT,
                    node_name TEXT,
                    level INTEGER,
                    is_active INTEGER
                );
                CREATE TABLE edit_show_version(
                    id INTEGER PRIMARY KEY,
                    edit_show_sign INTEGER,
                    version_id INTEGER
                );

                INSERT INTO data_account_metric_node VALUES ('A03.03', '净利息收入', 3, 1);
                INSERT INTO edit_show_version(id, edit_show_sign, version_id) VALUES (1, 1, 101);
                INSERT INTO edit_show_version(id, edit_show_sign, version_id) VALUES (2, 2, 202);
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_compare_pivot_suggestion_aligns_to_base_year_version_and_search_codes(self) -> None:
        suggestion = build_pivot_suggestion(
            {
                "intent_type": "budget",
                "budget_query_kind": "analysis",
                "user_query": "按部门看同比，按季展示",
                "clarified_slots": {"granularity": "quarter"},
                "pm_query_spec": {
                    "metric_nodes": [{"code": "A03.03", "name": "净利息收入"}],
                    "departments": [{"code": "Y103", "name": "汽车金融部"}],
                },
                "query_db_year": 2026,
                "query_version_id": 0,
                "query_base_version_id": 101,
                "query_data_source": "compare_l1",
                "query_show_level": 2,
                "query_year_tag": "Y2026",
                "query_base_year_tag": "Y2026",
            },
            runtime_config={"pivot": {"base_confidence": 0.6}},
            common_db=self.common_db,
            current_year=2026,
        )

        self.assertIsNotNone(suggestion)
        assert suggestion is not None
        self.assertEqual(
            suggestion["row_field_ids"],
            ["metric_level2", "metric_level3", "metric_level4", "metric_level5", "data_code_name"],
        )
        self.assertEqual(suggestion["column_field_ids"], ["quarter", "budget_actual"])
        self.assertEqual(
            suggestion["page_field_ids"],
            ["year", "version_display", "dept_level1", "dept_level2", "dept_level3"],
        )
        self.assertEqual(
            suggestion["page_selections"],
            {
                "year": "Y2026",
                "version_display": "版本号：101",
                "dept_level1": "汽车金融",
                "dept_level2": "汽车金融",
                "dept_level3": "汽车金融",
            },
        )
        self.assertEqual(suggestion["pivot_search_text"], "A03.03")
        self.assertGreaterEqual(suggestion["confidence"], 0.74)

    def test_budget_pivot_suggestion_prefers_explicit_version_and_data_account_rows(self) -> None:
        suggestion = build_pivot_suggestion(
            {
                "intent_type": "budget",
                "budget_query_kind": "analysis",
                "user_query": "看 version: 303 的汽金贷款余额按月趋势",
                "pm_query_spec": {
                    "data_accounts": [{"code": "A03.03.01.01.01.078", "name": "汽金贷款利息收入"}],
                },
                "query_db_year": 2026,
                "query_version_id": 101,
                "query_data_source": "budget",
                "query_year_tag": "Y2026",
            },
            runtime_config={"pivot": {"base_confidence": 0.5}},
            common_db=self.common_db,
            current_year=2026,
        )

        self.assertIsNotNone(suggestion)
        assert suggestion is not None
        self.assertEqual(suggestion["row_field_ids"], ["data_code_name"])
        self.assertEqual(suggestion["column_field_ids"], ["month", "budget_actual"])
        self.assertEqual(suggestion["page_selections"]["version_display"], "版本号：303")
        self.assertEqual(suggestion["pivot_search_text"], "A03.03.01.01.01.078")

    def test_recommendation_and_reply_options_are_independent_of_graph_class(self) -> None:
        pivot = {"confidence": 0.61}
        state = {"budget_query_kind": "analysis", "prefer_pivot_view": True}

        self.assertTrue(should_recommend_pivot(state, pivot, pivot_config={"recommend_all_analysis": False}))
        self.assertEqual(
            [item["id"] for item in build_plan_reply_options(state, recommend_pivot=True)],
            ["open_pivot_table", "sql_and_pivot", "sql_query"],
        )
        footer = append_reply_options_footer("已完成规划", build_plan_reply_options({}, recommend_pivot=False))
        self.assertIn("请选择下一步", footer)
        self.assertIn("sql_query", str(build_plan_reply_options({}, recommend_pivot=False)))

    def test_metadata_or_general_state_has_no_pivot_suggestion(self) -> None:
        self.assertIsNone(
            build_pivot_suggestion(
                {"intent_type": "budget", "budget_query_kind": "metadata", "user_query": "有哪些部门"},
                runtime_config={},
                common_db=self.common_db,
                current_year=2026,
            )
        )
        self.assertIsNone(
            build_pivot_suggestion(
                {"intent_type": "general", "budget_query_kind": "analysis", "user_query": "你好"},
                runtime_config={},
                common_db=self.common_db,
                current_year=2026,
            )
        )


if __name__ == "__main__":
    unittest.main()
