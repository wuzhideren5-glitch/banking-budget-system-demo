from __future__ import annotations

import unittest
from pathlib import Path

from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    ParsedFramework,
    build_framework_context,
)
from app.services.expense_budget_execution_query_report import build_query_report_model


def _months(first: float = 0.0, second: float = 0.0) -> list[float]:
    return [first, second] + [0.0] * 10


def _subject_rows() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "parent_id": None,
            "level_number": 1,
            "level_label": "一级",
            "subject_name": "业务费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 1,
        },
        {
            "id": 2,
            "parent_id": None,
            "level_number": 1,
            "level_label": "一级",
            "subject_name": "IT费用",
            "manage_department": "T01 平台部",
            "formula_text": "",
            "sort_order": 2,
        },
        {
            "id": 3,
            "parent_id": None,
            "level_number": 1,
            "level_label": "一级",
            "subject_name": "零值费用",
            "manage_department": "",
            "formula_text": "",
            "sort_order": 3,
        },
    ]


def _parsed_framework() -> ParsedFramework:
    return ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
            FrameworkBudgetDepartmentRow("微众银行", "企业及机构金融事业群", "B01 企业部", "B01 企业部"),
            FrameworkBudgetDepartmentRow("科技子", "科技及智能事业群", "T01 平台部", "T01 平台部"),
        ],
        product_departments=[],
        subjects=[],
    )


class ExpenseBudgetExecutionQueryReportTests(unittest.TestCase):
    def test_build_query_report_model_aggregates_group_rows_with_scope_and_keyword(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        model = build_query_report_model(
            ctx=ctx,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "业务费用"): _months(10.0, 20.0),
                ("B01 企业部", "业务费用"): _months(99.0, 99.0),
                ("T01 平台部", "IT费用"): _months(5.0, 5.0),
            },
            budget_by_owner={
                ("A01 产品部", "业务费用"): 100.0,
                ("B01 企业部", "业务费用"): 999.0,
                ("T01 平台部", "IT费用"): 50.0,
            },
            perspective="group",
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="",
            keyword="业务",
            include_zero_rows=False,
            current_month=2,
        )

        self.assertEqual(len(model.rows), 1)
        row = model.rows[0]
        self.assertEqual(row["perspective"], "group")
        self.assertEqual(row["dimension_value"], "个人金融事业群")
        self.assertEqual(row["entity_name"], "微众银行")
        self.assertEqual(row["budget_subject"], "业务费用")
        self.assertEqual(row["monthly_actuals"], _months(10.0, 20.0))
        self.assertEqual(row["cumulative_actual"], 30.0)
        self.assertEqual(row["annual_budget"], 100.0)
        self.assertEqual(row["execution_rate"], 0.3)
        self.assertEqual(row["month_over_month"], 10.0)
        self.assertEqual(row["month_over_month_rate"], 1.0)

    def test_build_query_report_model_filters_manage_department_and_zero_rows(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        model = build_query_report_model(
            ctx=ctx,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "IT费用"): _months(1.0, 1.0),
                ("A01 产品部", "零值费用"): _months(),
            },
            budget_by_owner={
                ("A01 产品部", "IT费用"): 10.0,
                ("A01 产品部", "零值费用"): 0.0,
            },
            perspective="owner_dept",
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
            keyword="",
            include_zero_rows=False,
            current_month=2,
        )

        self.assertEqual(model.rows, [])

        zero_model = build_query_report_model(
            ctx=ctx,
            subject_rows=_subject_rows(),
            actual_by_owner={},
            budget_by_owner={("A01 产品部", "零值费用"): 0.0},
            perspective="owner_dept",
            selected_entity="微众银行",
            selected_group="个人金融事业群",
            selected_owner="A01 产品部",
            keyword="",
            include_zero_rows=True,
            current_month=2,
        )
        self.assertEqual(len(zero_model.rows), 1)
        self.assertEqual(zero_model.rows[0]["budget_subject"], "零值费用")
        self.assertEqual(zero_model.rows[0]["cumulative_actual"], 0.0)


if __name__ == "__main__":
    unittest.main()
