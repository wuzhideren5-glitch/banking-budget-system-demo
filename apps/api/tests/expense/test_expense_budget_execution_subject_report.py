from __future__ import annotations

import unittest
from pathlib import Path

from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    FrameworkSubjectRow,
    ParsedFramework,
    build_framework_context,
)
from app.services.expense_budget_execution_subject_report import build_subject_report_model


def _subject_rows() -> list[dict[str, object]]:
    return [
        {
            "id": 1,
            "parent_id": None,
            "level_number": 1,
            "level_label": "一级",
            "subject_name": "业务及管理费",
            "sort_order": 1,
        },
        {
            "id": 2,
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "业务费用",
            "sort_order": 2,
        },
        {
            "id": 3,
            "parent_id": 1,
            "level_number": 2,
            "level_label": "二级",
            "subject_name": "IT费用",
            "sort_order": 3,
        },
    ]


def _parsed_framework() -> ParsedFramework:
    return ParsedFramework(
        source_file=Path("framework.xlsx"),
        budget_departments=[
            FrameworkBudgetDepartmentRow("微众银行", "个人金融事业群", "A01 产品部", "A01 产品部"),
            FrameworkBudgetDepartmentRow("科技子", "科技及智能事业群", "T01 平台部", "T01 平台部"),
        ],
        product_departments=[],
        subjects=[
            FrameworkSubjectRow("二级", "业务费用", "", "0", 1),
            FrameworkSubjectRow("二级", "IT费用", "科技业务", "0", 2),
        ],
    )


class ExpenseBudgetExecutionSubjectReportTests(unittest.TestCase):
    def test_build_subject_report_model_aggregates_selected_subject_by_entity(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        model = build_subject_report_model(
            ctx=ctx,
            parsed=parsed,
            subject_rows=_subject_rows(),
            actual_by_owner={
                ("A01 产品部", "业务费用"): [10.0, 20.0] + [0.0] * 10,
                ("A01 产品部", "IT费用"): [99.0] + [0.0] * 11,
                ("T01 平台部", "业务费用"): [50.0] + [0.0] * 11,
            },
            budget_by_owner={
                ("A01 产品部", "业务费用"): 100.0,
                ("A01 产品部", "IT费用"): 999.0,
                ("T01 平台部", "业务费用"): 500.0,
            },
            previous_year_actual_by_owner_subject={
                ("A01 产品部", "业务费用"): [5.0, 5.0] + [0.0] * 10,
                ("T01 平台部", "业务费用"): [20.0] + [0.0] * 11,
            },
            current_month=2,
            selected_entity="微众银行",
            selected_subject_id=2,
            include_zero_rows=False,
            keyword="产品部",
        )

        self.assertEqual(model.selected_subject_id, 2)
        self.assertEqual(model.subject_scope_tree[0]["subject_name"], "业务及管理费")
        self.assertEqual(len(model.subject_tree), 1)
        entity_node = model.subject_tree[0]
        group_node = entity_node["children"][0]
        owner_node = group_node["children"][0]
        self.assertEqual(entity_node["subject_name"], "微众银行")
        self.assertEqual(group_node["subject_name"], "个人金融事业群")
        self.assertEqual(owner_node["subject_name"], "A01 产品部")
        self.assertEqual(owner_node["current_actual"], 30.0)
        self.assertEqual(owner_node["annual_budget"], 100.0)
        self.assertEqual(owner_node["last_year_actual"], 10.0)
        self.assertEqual(owner_node["yoy_change"], 20.0)
        self.assertEqual(owner_node["month_over_month"], 10.0)
        self.assertEqual(owner_node["month_over_month_rate"], 1.0)

    def test_build_subject_report_model_filters_zero_rows(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        model = build_subject_report_model(
            ctx=ctx,
            parsed=parsed,
            subject_rows=_subject_rows(),
            actual_by_owner={},
            budget_by_owner={},
            previous_year_actual_by_owner_subject={},
            current_month=2,
            selected_entity="微众银行",
            selected_subject_id=3,
            include_zero_rows=False,
            keyword="",
        )

        self.assertEqual(model.selected_subject_id, 3)
        self.assertEqual(model.subject_tree, [])


if __name__ == "__main__":
    unittest.main()
