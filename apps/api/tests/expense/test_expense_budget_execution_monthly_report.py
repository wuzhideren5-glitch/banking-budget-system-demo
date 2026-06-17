from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    ParsedFramework,
    build_framework_context,
)
from app.services import expense_budget_execution_monthly_report as monthly_report_module
from app.services.expense_budget_execution_monthly_report import build_monthly_report_sections


def _months(first: float = 0.0, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * 10


def _subject_rows() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "parent_id": None,
            "level_number": 1,
            "level_label": "一级",
            "subject_name": "业务及管理费",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 1,
        },
        {
            "id": 2,
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "业务费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 2,
        },
        {
            "id": 3,
            "parent_id": 2,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "营销费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 3,
        },
        {
            "id": 4,
            "parent_id": 3,
            "level_number": 4,
            "level_label": "四级",
            "subject_name": "品牌营销",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 4,
        },
        {
            "id": 5,
            "parent_id": 2,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "运营费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 5,
        },
        {
            "id": 6,
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "IT费用",
            "manage_department": "T01 平台部",
            "formula_text": "",
            "sort_order": 6,
        },
        {
            "id": 7,
            "parent_id": 6,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "IT外包服务费",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 7,
        },
        {
            "id": 8,
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "日常费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 8,
        },
        {
            "id": 9,
            "parent_id": 8,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "职场费用",
            "manage_department": "行政部",
            "formula_text": "",
            "sort_order": 9,
        },
        {
            "id": 10,
            "parent_id": 8,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "外包服务费",
            "manage_department": "行政部",
            "formula_text": "",
            "sort_order": 10,
        },
        {
            "id": 11,
            "parent_id": 8,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "进项税转出",
            "manage_department": "行政部",
            "formula_text": "",
            "sort_order": 11,
        },
        {
            "id": 12,
            "parent_id": 8,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "非IT咨询费",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 12,
        },
        {
            "id": 13,
            "parent_id": 8,
            "level_number": 3,
            "level_label": "三级",
            "subject_name": "业务招待费",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 13,
        },
    ]


def _parsed_framework() -> ParsedFramework:
    return ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
            FrameworkBudgetDepartmentRow("微众银行", "资源管理及管控职能群", "行政部", "行政部"),
            FrameworkBudgetDepartmentRow("科技子", "科技及智能事业群", "T01 平台部", "T01 平台部"),
        ],
        product_departments=[],
        subjects=[],
    )


class ExpenseBudgetExecutionMonthlyReportTests(unittest.TestCase):
    def test_monthly_subject_source_name_resolution_is_a_single_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "resolve_monthly_subject_source_names"))
        self.assertEqual(
            monthly_report_module.resolve_monthly_subject_source_names(
                "办公资产摊销及折旧",
                {"办公资产摊销及折旧": ["日常资产摊销及折旧"]},
            ),
            ["日常资产摊销及折旧"],
        )
        self.assertEqual(
            monthly_report_module.resolve_monthly_subject_source_names("业务招待费", {}),
            ["业务招待费"],
        )
        self.assertEqual(
            monthly_report_module.resolve_monthly_subject_source_names("", {}),
            [],
        )

    def test_monthly_matrix_uses_subject_source_resolution_interface(self) -> None:
        source_text = inspect.getsource(monthly_report_module._build_metric_matrix_rows_for_scope)

        self.assertNotIn(".get(subject_name, [subject_name])", source_text)
        self.assertIn("resolve_monthly_subject_source_names(", source_text)

    def test_monthly_business_rows_hide_display_rules_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_business_metric_rows"))
        source_text = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_business_metric_rows(", source_text)
        self.assertNotIn("BUSINESS_FORCE_OPERATING_GROUP", source_text)
        self.assertNotIn("force_subject_labels_by_owner=", source_text)

    def test_monthly_it_rows_hide_display_rules_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_it_metric_rows"))
        source_text = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_it_metric_rows(", source_text)
        self.assertNotIn("IT_OTHER_SOURCE_OWNER", source_text)
        self.assertNotIn("IT费用合计", source_text)

    def test_monthly_daily_managed_rows_hide_display_rules_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_daily_managed_metric_rows"))
        source_text = inspect.getsource(monthly_report_module._build_daily_metric_sections)
        top_source = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_daily_managed_metric_rows(", source_text)
        self.assertNotIn("DAILY_MANAGED_OTHER_SOURCE_OWNER", top_source)
        self.assertNotIn("DAILY_MANAGED_FORCE_SUBJECT_SPECS", top_source)

    def test_monthly_daily_topic_blocks_hide_display_rules_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_daily_topic_metric_blocks"))
        source_text = inspect.getsource(monthly_report_module._build_daily_metric_sections)
        top_source = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_daily_topic_metric_blocks(", source_text)
        self.assertNotIn("中后台外包服务费合计", top_source)
        self.assertNotIn("其他进项税转出合计", top_source)

    def test_monthly_daily_other_matrix_hides_subject_specs_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_daily_other_matrix"))
        source_text = inspect.getsource(monthly_report_module._build_daily_metric_sections)
        top_source = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_daily_other_matrix(", source_text)
        self.assertNotIn("DAILY_OTHER_SUBJECT_SPECS", top_source)

    def test_monthly_daily_managed_blocks_hide_titles_and_filtering_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_daily_managed_blocks"))
        source_text = inspect.getsource(monthly_report_module._build_daily_metric_sections)
        top_source = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_daily_managed_blocks(", source_text)
        self.assertNotIn("3.1日常费用-分解至归口部门", top_source)
        self.assertNotIn('if block["rows"]', top_source)

    def test_monthly_daily_sections_hide_daily_tree_assembly_behind_interface(self) -> None:
        self.assertTrue(hasattr(monthly_report_module, "_build_daily_metric_sections"))
        source_text = inspect.getsource(monthly_report_module.build_monthly_report_sections)

        self.assertIn("_build_daily_metric_sections(", source_text)
        self.assertNotIn('_collect_descendant_subject_rows(subject_rows, "日常费用")', source_text)
        self.assertNotIn("_build_daily_managed_metric_rows(", source_text)

    def test_build_monthly_report_sections_returns_business_it_and_daily_blocks(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        sections = build_monthly_report_sections(
            ctx=ctx,
            parsed=parsed,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "品牌营销"): _months(10.0, 20.0),
                ("A01 产品部", "运营费用"): _months(5.0, 10.0),
                ("A01 产品部", "IT外包服务费"): _months(11.0, 9.0),
                ("A01 产品部", "职场费用"): _months(4.0, 6.0),
                ("A01 产品部", "日常外包服务费"): _months(3.0, 2.0),
                ("A01 产品部", "进项税转出"): _months(1.0, 1.0),
                ("A01 产品部", "非IT咨询费"): _months(7.0, 8.0),
                ("A01 产品部", "业务招待费"): _months(2.0, 3.0),
            },
            budget_by_owner={
                ("A01 产品部", "品牌营销"): 100.0,
                ("A01 产品部", "运营费用"): 50.0,
                ("A01 产品部", "IT外包服务费"): 200.0,
                ("A01 产品部", "职场费用"): 40.0,
                ("A01 产品部", "日常外包服务费"): 25.0,
                ("A01 产品部", "进项税转出"): 10.0,
                ("A01 产品部", "非IT咨询费"): 30.0,
                ("A01 产品部", "业务招待费"): 10.0,
            },
            previous_year_actual_by_owner_subject={
                ("A01 产品部", "品牌营销"): _months(3.0, 4.0),
                ("A01 产品部", "运营费用"): _months(1.0, 2.0),
                ("A01 产品部", "IT外包服务费"): _months(4.0, 4.0),
                ("A01 产品部", "职场费用"): _months(1.0, 1.0),
            },
            current_month=2,
            selected_entity="",
            selected_group="",
            selected_owner="",
        )

        business_total = next(
            row
            for row in sections.business_rows
            if row["label"] == "全行" and row["subject_name"] == "业务费用合计"
        )
        self.assertEqual(business_total["current_actual"], 45.0)
        self.assertEqual(business_total["annual_budget"], 150.0)
        self.assertEqual(business_total["last_year_actual"], 10.0)
        self.assertEqual(business_total["yoy_change"], 35.0)

        it_total = next(row for row in sections.it_rows if row["subject_name"] == "IT费用合计")
        self.assertEqual(it_total["label"], "T01 平台部")
        self.assertEqual(it_total["current_actual"], 20.0)
        self.assertEqual(it_total["annual_budget"], 200.0)
        self.assertEqual(it_total["last_year_actual"], 8.0)
        self.assertEqual(sections.it_rows[0]["subject_name"], "IT费用合计")

        managed_block = next(block for block in sections.managed_blocks if block["title"] == "3.1日常费用-分解至归口部门")
        managed_total = managed_block["rows"][0]
        self.assertEqual(managed_total["label"], "资源管理及管控职能群")
        self.assertEqual(managed_total["subject_name"], "日常费用合计")
        self.assertEqual(managed_total["current_actual"], 10.0)

        self.assertNotIn("3.1.2 中后台外包服务费", [block["title"] for block in sections.managed_blocks])

        tax_block = next(block for block in sections.managed_blocks if block["title"] == "3.1.3 其他进项税转出")
        self.assertEqual(tax_block["rows"][0]["subject_name"], "其他进项税转出合计")
        self.assertEqual(tax_block["rows"][0]["current_actual"], 2.0)

        self.assertEqual(
            sections.daily_other_columns,
            ["业务招待费", "差旅及会议费", "非IT咨询费", "日常外包服务费", "协会费", "部门经费", "部门会议费", "办公杂费"],
        )
        daily_other_total = sections.daily_other_rows[0]
        self.assertEqual(daily_other_total["label"], "全行")
        self.assertEqual(daily_other_total["actual_total"], 25.0)
        self.assertEqual(daily_other_total["actuals"]["非IT咨询费"], 15.0)
        self.assertEqual(daily_other_total["actuals"]["业务招待费"], 5.0)
        self.assertEqual(daily_other_total["actuals"]["日常外包服务费"], 5.0)

    def test_monthly_it_total_is_first_row_and_includes_tax_subtotal(self) -> None:
        parsed = ParsedFramework(
            source_file=Path("framework.xlsx"),
            budget_departments=[
                FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
                FrameworkBudgetDepartmentRow("微众银行", "资源管理及管控职能群", "行长室", "行长室"),
            ],
            product_departments=[],
            subjects=[],
        )
        ctx = build_framework_context(parsed)

        sections = build_monthly_report_sections(
            ctx=ctx,
            parsed=parsed,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "IT外包服务费"): _months(11.0, 9.0),
                ("行长室", "IT外包服务费"): _months(1.0, 2.0),
            },
            budget_by_owner={
                ("A01 产品部", "IT外包服务费"): 200.0,
                ("行长室", "IT外包服务费"): 30.0,
            },
            previous_year_actual_by_owner_subject={
                ("A01 产品部", "IT外包服务费"): _months(4.0, 4.0),
                ("行长室", "IT外包服务费"): _months(1.0, 1.0),
            },
            current_month=2,
            selected_entity="",
            selected_group="",
            selected_owner="",
        )

        self.assertGreaterEqual(len(sections.it_rows), 3)
        self.assertEqual(sections.it_rows[0]["subject_name"], "IT费用合计")
        self.assertEqual(sections.it_rows[0]["current_actual"], 23.0)
        self.assertEqual(sections.it_rows[0]["annual_budget"], 230.0)
        self.assertEqual(sections.it_rows[0]["last_year_actual"], 10.0)

        tax_subtotal = next(row for row in sections.it_rows if row["subject_name"] == "进项税小计")
        self.assertEqual(tax_subtotal["label"], "其他")
        self.assertEqual(tax_subtotal["current_actual"], 3.0)
        self.assertEqual(tax_subtotal["annual_budget"], 30.0)

    def test_build_monthly_report_sections_limits_to_selected_owner(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        sections = build_monthly_report_sections(
            ctx=ctx,
            parsed=parsed,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "品牌营销"): _months(10.0, 20.0),
                ("T01 平台部", "品牌营销"): _months(99.0, 99.0),
            },
            budget_by_owner={
                ("A01 产品部", "品牌营销"): 100.0,
                ("T01 平台部", "品牌营销"): 999.0,
            },
            previous_year_actual_by_owner_subject={
                ("A01 产品部", "品牌营销"): _months(1.0, 2.0),
                ("T01 平台部", "品牌营销"): _months(99.0, 99.0),
            },
            current_month=2,
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
        )

        self.assertEqual(
            [(row["label"], row["subject_name"], row["current_actual"]) for row in sections.business_rows],
            [("A01 产品部", "营销费用", 30.0), ("A01 产品部", "费用小计", 30.0)],
        )
        marketing_row = sections.business_rows[0]
        self.assertEqual(marketing_row["annual_budget"], 100.0)
        self.assertEqual(marketing_row["last_year_actual"], 3.0)


if __name__ == "__main__":
    unittest.main()
