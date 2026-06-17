from __future__ import annotations

import unittest

from app.services.agent_budget_summary_sql import suggest_budget_summary_sql, suggest_metadata_sql


class AgentBudgetSummarySqlTests(unittest.TestCase):
    def test_compare_metadata_uses_compare_read_model_and_show_level(self) -> None:
        sql = suggest_metadata_sql(
            "有多少部门",
            data_source="compare_l1",
            version_id=101,
            year_tag="Y2026",
            month_tag="M05",
            show_level=3,
        )

        self.assertIn("COUNT(DISTINCT COALESCE(dept_level3, dept_level2, dept_level1))", sql)
        self.assertIn("FROM compare_budget_summary", sql)
        self.assertIn("show_level = 3 AND year = 'Y2026' AND month = 'M05'", sql)
        self.assertNotIn("version_id", sql)

    def test_budget_metadata_uses_current_version_without_compare_filters(self) -> None:
        sql = suggest_metadata_sql(
            "全部产品名称列表",
            data_source="budget",
            version_id=101,
            year_tag="Y2026",
            month_tag="M05",
            show_level=1,
        )

        self.assertIn("SELECT DISTINCT product_code_name", sql)
        self.assertIn("FROM budget_summary", sql)
        self.assertIn("WHERE version_id = 101", sql)
        self.assertNotIn("show_level", sql)
        self.assertNotIn("year = 'Y2026'", sql)

    def test_metric_only_budget_query_adds_report_scope_and_side_by_side_columns(self) -> None:
        sql = suggest_budget_summary_sql(
            "按产品展示预算实际两列",
            version_id=101,
            year_tag="Y2026",
            month_tag="M05",
            state={"pm_query_spec": {"metric_nodes": [{"code": "A03.03", "name": "净利息收入"}]}},
        )

        self.assertIn("'A03.03 净利息收入' AS report_scope", sql)
        self.assertIn("product_code_name, month", sql)
        self.assertIn("AS '预算值'", sql)
        self.assertIn("AS '实际值'", sql)
        self.assertIn("WHERE version_id = 101 AND year = 'Y2026' AND month = 'M05'", sql)

    def test_normal_side_by_side_query_groups_by_account(self) -> None:
        sql = suggest_budget_summary_sql(
            "按科目展示预算实际两列",
            version_id=101,
            year_tag="Y2026",
            month_tag=None,
            state={},
        )

        self.assertIn("SELECT data_code_name, month", sql)
        self.assertIn("SUM(CASE WHEN budget_actual = 0 THEN value ELSE 0 END) AS '预算值'", sql)
        self.assertIn("GROUP BY data_code_name, month", sql)
        self.assertIn("WHERE version_id = 101 AND year = 'Y2026'", sql)

    def test_default_budget_query_groups_month_and_budget_actual(self) -> None:
        sql = suggest_budget_summary_sql(
            "看趋势",
            version_id=101,
            year_tag="Y2026",
            month_tag=None,
            state={},
        )

        self.assertIn("SELECT month, budget_actual, SUM(value) AS total_value", sql)
        self.assertIn("GROUP BY month, budget_actual", sql)
        self.assertIn("FROM budget_summary", sql)


if __name__ == "__main__":
    unittest.main()
