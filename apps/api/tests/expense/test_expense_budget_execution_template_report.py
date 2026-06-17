from __future__ import annotations

import unittest
from pathlib import Path

from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    ParsedFramework,
    build_framework_context,
)
from app.services.expense_budget_execution_template_report import build_template_report_model


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
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "IT费用",
            "manage_department": "T01 平台部",
            "formula_text": "",
            "sort_order": 3,
        },
    ]


def _context():
    parsed = ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
            FrameworkBudgetDepartmentRow("科技子", "科技及智能事业群", "T01 平台部", "T01 平台部"),
        ],
        product_departments=[],
        subjects=[],
    )
    return build_framework_context(parsed)


class ExpenseBudgetExecutionTemplateReportTests(unittest.TestCase):
    def test_build_template_report_model_aggregates_subject_tree_for_selected_entity(self) -> None:
        ctx = _context()

        model = build_template_report_model(
            ctx=ctx,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "业务费用"): [10.0, 20.0] + [0.0] * 10,
                ("T01 平台部", "IT费用"): [99.0] + [0.0] * 11,
            },
            budget_by_owner={
                ("A01 产品部", "业务费用"): 100.0,
                ("T01 平台部", "IT费用"): 999.0,
            },
            previous_year_subject_monthly_totals={
                "业务费用": [5.0, 5.0] + [0.0] * 10,
            },
            previous_year_subject_totals={"业务费用": 10.0},
            current_month=2,
            selected_entity="微众银行",
            include_zero_rows=False,
            keyword="业务",
        )

        self.assertEqual(len(model.subject_tree), 1)
        root = model.subject_tree[0]
        self.assertEqual(root["subject_name"], "业务及管理费")
        self.assertEqual([child["subject_name"] for child in root["children"]], ["业务费用"])
        self.assertEqual(root["current_actual"], 30.0)
        self.assertEqual(root["annual_budget"], 100.0)
        self.assertEqual(root["last_year_actual"], 10.0)
        self.assertEqual(root["yoy_change"], 20.0)
        self.assertEqual(root["month_over_month"], 10.0)
        self.assertEqual(root["month_over_month_rate"], 1.0)

    def test_build_template_report_model_keeps_zero_rows_when_requested(self) -> None:
        ctx = _context()

        model = build_template_report_model(
            ctx=ctx,
            subject_rows=_subject_rows(),
            actual_by_owner={},
            budget_by_owner={},
            previous_year_subject_monthly_totals={},
            previous_year_subject_totals={},
            current_month=2,
            include_zero_rows=True,
        )

        self.assertEqual(len(model.subject_tree), 1)
        self.assertEqual(
            [child["subject_name"] for child in model.subject_tree[0]["children"]],
            ["业务费用", "IT费用"],
        )

    def test_template_tree_prefers_direct_source_values_and_consumes_duplicate_subject_once(self) -> None:
        ctx = _context()
        rows = [
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
                "subject_name": "运营费用",
                "manage_department": "",
                "formula_text": "",
                "sort_order": 1,
            },
            {
                "id": 3,
                "parent_id": 2,
                "level_number": 3,
                "level_label": "三级",
                "subject_name": "客服费",
                "manage_department": "",
                "formula_text": "",
                "sort_order": 1,
            },
            {
                "id": 4,
                "parent_id": 1,
                "level_number": 2,
                "level_label": "二级",
                "subject_name": "日常资产摊销及折旧",
                "manage_department": "办公室",
                "formula_text": "",
                "sort_order": 2,
            },
            {
                "id": 5,
                "parent_id": 1,
                "level_number": 2,
                "level_label": "二级",
                "subject_name": "日常资产摊销及折旧",
                "manage_department": "法律合规部",
                "formula_text": "",
                "sort_order": 3,
            },
        ]

        model = build_template_report_model(
            ctx=ctx,
            subject_rows=rows,
            actual_by_owner={},
            budget_by_owner={},
            previous_year_subject_monthly_totals={
                "运营费用": [57.6] + [0.0] * 11,
                "客服费": [12.0] + [0.0] * 11,
                "日常资产摊销及折旧": [15.6] + [0.0] * 11,
            },
            previous_year_subject_totals={},
            current_month=1,
            current_subject_monthly_totals_override={
                "运营费用": [48.0] + [0.0] * 11,
                "客服费": [10.0] + [0.0] * 11,
                "日常资产摊销及折旧": [13.0] + [0.0] * 11,
            },
            budget_subject_totals_override={
                "运营费用": 159.0,
                "客服费": 24.0,
                "日常资产摊销及折旧": 190.0,
            },
            include_zero_rows=True,
        )

        root = model.subject_tree[0]
        self.assertEqual(root["current_actual"], 61.0)
        self.assertEqual(root["annual_budget"], 349.0)
        self.assertEqual(root["last_year_actual"], 73.2)
        operation = root["children"][0]
        first_asset = root["children"][1]
        duplicate_asset = root["children"][2]
        self.assertEqual(operation["current_actual"], 48.0)
        self.assertEqual(operation["annual_budget"], 159.0)
        self.assertEqual(first_asset["annual_budget"], 190.0)
        self.assertEqual(duplicate_asset["current_actual"], 0.0)
        self.assertEqual(duplicate_asset["annual_budget"], 0.0)


if __name__ == "__main__":
    unittest.main()
