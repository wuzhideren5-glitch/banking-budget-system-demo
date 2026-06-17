from __future__ import annotations

from datetime import date
import unittest

from app.services.agent_analysis_filters import (
    analysis_fact_filters,
    compare_scope_from_query,
    norm_code_name_list,
    pm_metric_locked_without_data,
    pm_metric_scope_label,
    pm_time_filter_sql,
    sql_missing_pm_dimensions,
)


class AgentAnalysisFiltersTests(unittest.TestCase):
    def test_pm_structured_dimensions_build_current_fact_filters(self) -> None:
        state = {
            "pm_query_spec": {
                "data_accounts": [{"code": "A03.03.01.01.01.078", "name": "汽金贷款利息收入"}],
                "departments": [{"code": "Y103", "name": "汽车金融部"}],
                "products": [{"code": "A03", "name": "汽车金融"}],
                "year": "Y2026",
                "month": "M05",
            }
        }

        sql = analysis_fact_filters(state, "查询汽金贷款利息收入")

        self.assertIn("IFNULL(data_code_name,'')", sql)
        self.assertIn("'A03.03.01.01.01.078'", sql)
        self.assertIn("'汽金贷款利息收入'", sql)
        self.assertIn("IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,'')", sql)
        self.assertIn("'汽车金融'", sql)
        self.assertIn("year = 'Y2026'", sql)
        self.assertIn("month = 'M05'", sql)
        self.assertNotIn("贷款') > 0 OR", sql)

    def test_metric_lock_disables_keyword_scope_fallback(self) -> None:
        state = {"pm_query_spec": {"metric_nodes": [{"code": "A03.03", "name": "净利息收入"}]}}

        sql = analysis_fact_filters(state, "贷款规模")

        self.assertEqual(sql, "")
        self.assertTrue(pm_metric_locked_without_data(state["pm_query_spec"]))
        self.assertEqual(pm_metric_scope_label(state["pm_query_spec"]), "A03.03 净利息收入")

    def test_keyword_and_department_fallbacks_still_apply_without_pm_lock(self) -> None:
        sql = analysis_fact_filters({}, "企业金融贷款规模")

        self.assertIn("INSTR(IFNULL(data_code_name,''), '日均')", sql)
        self.assertIn("INSTR(IFNULL(dept_level1,'')||IFNULL(dept_level2,'')||IFNULL(dept_level3,''), '企业金融')", sql)
        self.assertEqual(compare_scope_from_query("存款趋势"), "")

    def test_time_windows_are_testable_without_system_date(self) -> None:
        self.assertEqual(
            pm_time_filter_sql(
                {"period_description": "最近三个月"},
                today=date(2026, 6, 1),
            ),
            " AND ((year = 'Y2026' AND month IN ('M05','M04','M03')))",
        )
        self.assertEqual(
            pm_time_filter_sql(
                {"period_description": "最近一个季度"},
                today=date(2026, 6, 1),
            ),
            " AND ((year = 'Y2026' AND quarter IN ('Q1')))",
        )
        self.assertEqual(
            pm_time_filter_sql(
                {"year": "Y2026", "period_description": "1-3月"},
                today=date(2026, 6, 1),
            ),
            " AND (year = 'Y2026' AND month IN ('M01','M02','M03'))",
        )

    def test_missing_pm_dimensions_uses_escaped_literal_contract(self) -> None:
        spec = {
            "metric_nodes": [{"code": "A03.03", "name": "净利息收入"}],
            "data_accounts": [{"code": "A03.03.01.01.01.078", "name": "汽金贷款利息收入"}],
            "departments": [{"code": "Y103", "name": "汽车金融部"}],
            "products": [{"code": "A03", "name": "汽车金融"}],
        }
        sql = "WHERE data_code_name = 'A03.03.01.01.01.078' AND dept_level1 = 'Y103'"

        self.assertEqual(sql_missing_pm_dimensions(sql, spec), ["指标节点", "机构及产品"])
        self.assertEqual(norm_code_name_list([{"code": " A03 ", "name": " 汽车金融 "}]), [{"code": "A03", "name": "汽车金融"}])


if __name__ == "__main__":
    unittest.main()
