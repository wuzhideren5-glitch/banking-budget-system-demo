from __future__ import annotations

import importlib
from io import BytesIO
import unittest

from openpyxl import Workbook

from app.services.expense_forecast_rule_import_workflow import (
    apply_expense_forecast_rule_import_rows,
    preview_expense_forecast_rule_import_rows,
)


def _row(**overrides) -> dict:
    row = {
        "row_number": 2,
        "forecast_year": 2026,
        "forecast_version": " V1 ",
        "owner_name": " 部门A ",
        "subject_name": "短信费",
        "scheme_code": "METRIC_EXPR",
        "scheme_label": "指标表达式",
        "enabled": True,
        "allow_manual_override": True,
        "auto_refresh_enabled": True,
        "manual_recalc_enabled": True,
        "metric_source_priority": "inline_first",
        "effective_from_month": 1,
        "effective_to_month": 12,
        "priority": 80,
        "remark": "导入规则",
        "expression": "base_amount * factor",
        "variables_json": '[{"variable_code":"base_amount","source_type":"metric_tree","source_key":"A01.01.01.001"}]',
    }
    row.update(overrides)
    return row


SUBJECT_BY_NAME = {
    "短信费": [{"id": 11, "is_leaf": True}],
    "办公费": [{"id": 12, "is_leaf": True}],
    "父级科目": [{"id": 13, "is_leaf": False}],
    "重复科目": [{"id": 14, "is_leaf": True}, {"id": 15, "is_leaf": True}],
}


class FakeRuleImportSource:
    def __init__(self) -> None:
        self.load_requests: list[dict] = []
        self.saved_rules: list[dict] = []
        self.org_product_refs_by_runtime_ref_code = {
            "A01.01.01.001": ("A01:业务状况表:A0101 营业收入",),
            "A01.01.01.01.01.017": ("A01:业务状况表:A0111 管理贷款日均",),
        }

    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str] | None = None,
        subject_id: int | None = None,
    ) -> list[dict]:
        self.load_requests.append(
            {
                "year": year,
                "forecast_version": forecast_version,
                "owner_names": owner_names,
                "subject_id": subject_id,
            }
        )
        if forecast_version == "V1" and owner_names is None and subject_id is None:
            return [
                {
                    "forecast_year": 2026,
                    "forecast_version": "V1",
                    "owner_name": "部门A",
                    "subject_id": 11,
                }
            ]
        if forecast_version == "V1" and owner_names == ["部门A"] and subject_id == 11:
            return [{"id": 7}]
        return []

    async def save_rule(self, *, rule: dict, rule_id: int | None) -> None:
        self.saved_rules.append({"rule": rule, "rule_id": rule_id})

    async def load_subject_lookup(self):
        return {}, SUBJECT_BY_NAME

    async def load_org_product_refs_by_runtime_ref_code(self):
        return self.org_product_refs_by_runtime_ref_code


def rule_import_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "预测规则模板"
    worksheet.append(["年度", "版本", "费用归属部门", "预算科目", "预测逻辑", "表达式", "变量映射JSON"])
    worksheet.append(
        [
            2026,
            "V1",
            "部门A",
            "短信费",
            "指标表达式",
            "base_amount * factor",
            '[{"variable_code":"base_amount","source_type":"org_product_metric","source_key":"A0111","source_subkey":"A01"}]',
        ]
    )
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class ExpenseForecastRuleImportWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def import_workflow_module(self):
        return importlib.import_module("app.services.expense_forecast_rule_import_workflow")

    async def test_preview_workbook_parses_loads_context_and_counts_actions(self) -> None:
        source = FakeRuleImportSource()
        workflow_module = self.import_workflow_module()

        result = await workflow_module.preview_expense_forecast_rule_import_workbook(
            raw=rule_import_workbook(),
            default_year=2026,
            default_version="V1",
            source=source,
        )

        self.assertEqual(result.preview_count, 1)
        self.assertEqual(result.insertable_rules, 0)
        self.assertEqual(result.updatable_rules, 1)
        self.assertEqual(result.error_rules, 0)
        self.assertEqual(result.items[0]["action"], "update")
        self.assertEqual(
            source.load_requests,
            [
                {
                    "year": 2026,
                    "forecast_version": "V1",
                    "owner_names": None,
                    "subject_id": None,
                }
            ],
        )

    async def test_apply_workbook_parses_loads_context_and_saves_rules(self) -> None:
        source = FakeRuleImportSource()
        workflow_module = self.import_workflow_module()

        result = await workflow_module.apply_expense_forecast_rule_import_workbook(
            raw=rule_import_workbook(),
            default_year=2026,
            default_version="V1",
            source=source,
        )

        self.assertEqual(result.inserted_rules, 0)
        self.assertEqual(result.updated_rules, 1)
        self.assertEqual(result.skipped_rules, 0)
        self.assertEqual(result.error_rules, 0)
        self.assertEqual([item["rule_id"] for item in source.saved_rules], [7])

    def test_preview_counts_insert_update_and_errors(self) -> None:
        rows = [
            _row(row_number=2, subject_name="短信费"),
            _row(row_number=3, subject_name="办公费", scheme_code="MANUAL", scheme_label="手工/导入"),
            _row(row_number=4, subject_name="父级科目"),
            _row(row_number=5, expression=""),
        ]
        existing_rows = [
            {
                "forecast_year": 2026,
                "forecast_version": "V1",
                "owner_name": "部门A",
                "subject_id": 11,
            }
        ]

        result = preview_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            existing_rows=existing_rows,
            org_product_refs_by_runtime_ref_code={
                "A01.01.01.001": ("A01:业务状况表:A0101 营业收入",),
            },
        )

        self.assertEqual(result["preview_count"], 4)
        self.assertEqual(result["insertable_rules"], 1)
        self.assertEqual(result["updatable_rules"], 1)
        self.assertEqual(result["error_rules"], 2)
        self.assertEqual([item["action"] for item in result["items"]], ["update", "insert", "error", "error"])
        self.assertEqual(result["items"][2]["message"], "预算科目不存在或不是叶子科目")
        self.assertIn("必须填写表达式", result["items"][3]["message"])

    async def test_apply_saves_valid_rows_and_skips_errors(self) -> None:
        source = FakeRuleImportSource()
        rows = [
            _row(row_number=2, subject_name="短信费"),
            _row(row_number=3, subject_name="办公费", scheme_code="MANUAL", scheme_label="手工/导入"),
            _row(row_number=4, subject_name="重复科目"),
        ]

        result = await apply_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            source=source,
            org_product_refs_by_runtime_ref_code=source.org_product_refs_by_runtime_ref_code,
        )

        self.assertEqual(result, {"inserted_rules": 1, "updated_rules": 1, "skipped_rules": 0, "error_rules": 1})
        self.assertEqual([item["rule_id"] for item in source.saved_rules], [7, None])
        first_rule = source.saved_rules[0]["rule"]
        self.assertEqual(first_rule["forecast_version"], "V1")
        self.assertEqual(first_rule["owner_name"], "部门A")
        self.assertEqual(first_rule["subject_id"], 11)
        self.assertEqual(first_rule["scheme_code"], "METRIC_EXPR")
        self.assertEqual(first_rule["metric_source_priority"], "inline_first")
        self.assertEqual(first_rule["remark"], "导入规则")
        self.assertEqual(first_rule["params"][0]["param_group"], "metric_expr")
        self.assertEqual(first_rule["variables"][0]["variable_code"], "base_amount")
        self.assertEqual(first_rule["variables"][0]["source_type"], "metric_tree")
        self.assertEqual(first_rule["variables"][0]["source_key"], "A01.01.01.001")

    async def test_apply_resolves_org_product_variables_before_saving(self) -> None:
        source = FakeRuleImportSource()
        rows = [
            _row(
                row_number=2,
                subject_name="短信费",
                variables_json='[{"variable_code":"base_amount","source_type":"org_product_metric","source_key":"A0111","source_subkey":"A01"}]',
            ),
        ]

        result = await apply_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            source=source,
            org_product_refs_by_runtime_ref_code=source.org_product_refs_by_runtime_ref_code,
        )

        self.assertEqual(result["error_rules"], 0)
        variable = source.saved_rules[0]["rule"]["variables"][0]
        self.assertEqual(variable["source_type"], "metric_tree")
        self.assertEqual(variable["source_key"], "A01.01.01.01.01.017")
        self.assertEqual(variable["source_subkey"], "A01")
        self.assertEqual(variable["variable_name"], "管理贷款日均")

    def test_preview_resolves_org_product_ref_variables(self) -> None:
        rows = [
            _row(
                variables_json='[{"variable_code":"base_amount","org_product_ref":"A01:业务状况表:A0111"}]',
            )
        ]
        existing_rows = [
            {
                "forecast_year": 2026,
                "forecast_version": "V1",
                "owner_name": "部门A",
                "subject_id": 11,
            }
        ]

        result = preview_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            existing_rows=existing_rows,
            org_product_refs_by_runtime_ref_code={
                "A01.01.01.01.01.017": ("A01:业务状况表:A0111 管理贷款日均",),
            },
        )

        self.assertEqual(result["error_rules"], 0)
        self.assertEqual(result["items"][0]["action"], "update")

    def test_preview_rejects_missing_or_05_filtered_org_product_variable(self) -> None:
        rows = [
            _row(
                variables_json='[{"variable_code":"fee05","source_type":"org_product_metric","source_key":"A010503","source_subkey":"A01"}]',
            )
        ]

        result = preview_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            existing_rows=[],
            org_product_refs_by_runtime_ref_code={
                "A01.01.01.01.01.017": ("A01:业务状况表:A0111 管理贷款日均",),
            },
        )

        self.assertEqual(result["error_rules"], 1)
        self.assertIn("机构产品指标引用不存在或不唯一", result["items"][0]["message"])

    def test_preview_rejects_direct_metric_tree_variable_without_confirmed_org_product_ref(self) -> None:
        rows = [
            _row(
                variables_json='[{"variable_code":"orphan","source_type":"metric_tree","source_key":"Z99.01.001"}]',
            )
        ]

        result = preview_expense_forecast_rule_import_rows(
            rows,
            subject_by_name=SUBJECT_BY_NAME,
            existing_rows=[],
            org_product_refs_by_runtime_ref_code={
                "A01.01.01.001": ("A01:业务状况表:A0101 营业收入",),
            },
        )

        self.assertEqual(result["error_rules"], 1)
        self.assertIn("机构及产品指标编码未在机构产品指标中确认", result["items"][0]["message"])


if __name__ == "__main__":
    unittest.main()
