from __future__ import annotations

import unittest
from pathlib import Path

from app.services.expense_budget_execution_framework import (
    FrameworkBudgetDepartmentRow,
    ParsedFramework,
    build_framework_context,
)
from app.services.expense_budget_execution_report_context import (
    build_report_entity_context,
    build_report_scope_context,
)


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


class ExpenseBudgetExecutionReportContextTests(unittest.TestCase):
    def test_build_report_scope_context_filters_group_and_owner_options(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        context = build_report_scope_context(
            ctx,
            parsed,
            entity_name="  微众银行 ",
            group_name="个人金融事业群",
            owner_dept="",
        )

        self.assertEqual(context.available_entities, ["微众银行", "科技子"])
        self.assertEqual(context.available_groups, ["个人金融事业群", "企业及机构金融事业群"])
        self.assertEqual(context.available_owner_departments, ["A01 产品部"])
        self.assertEqual(context.selected_entity, "微众银行")
        self.assertEqual(context.selected_group, "个人金融事业群")
        self.assertEqual(context.selected_owner, "")
        self.assertEqual(
            context.selected_scope_note_parts(include_permission_note=True),
            [
                "当前主体筛选：微众银行。",
                "当前事业群筛选：个人金融事业群。",
                "对已设置归口管理部门的预算科目，仅展示当前筛选部门范围内有权限查看的科目。",
            ],
        )

    def test_report_context_payloads_match_route_contract_fields(self) -> None:
        parsed = _parsed_framework()
        ctx = build_framework_context(parsed)

        scope_context = build_report_scope_context(ctx, parsed, owner_dept=" T01   平台部 ")
        entity_context = build_report_entity_context(ctx, entity_name=" 科技子 ")

        self.assertEqual(scope_context.available_owner_departments, ["A01 产品部", "B01 企业部", "T01 平台部"])
        self.assertEqual(
            scope_context.payload_fields(),
            {
                "available_entities": ["微众银行", "科技子"],
                "available_groups": ["个人金融事业群", "企业及机构金融事业群", "科技及智能事业群"],
                "available_owner_departments": ["A01 产品部", "B01 企业部", "T01 平台部"],
                "template_scope_options": [
                    {
                        "entity_name": "微众银行",
                        "group_name": "个人金融事业群",
                        "owner_dept": "A01 产品部",
                    },
                    {
                        "entity_name": "微众银行",
                        "group_name": "企业及机构金融事业群",
                        "owner_dept": "B01 企业部",
                    },
                    {
                        "entity_name": "科技子",
                        "group_name": "科技及智能事业群",
                        "owner_dept": "T01 平台部",
                    },
                ],
                "selected_entity_name": "",
                "selected_group_name": "",
                "selected_owner_dept": "T01 平台部",
            },
        )
        self.assertEqual(
            entity_context.payload_fields(),
            {
                "available_entities": ["微众银行", "科技子"],
                "selected_entity_name": "科技子",
            },
        )


if __name__ == "__main__":
    unittest.main()
