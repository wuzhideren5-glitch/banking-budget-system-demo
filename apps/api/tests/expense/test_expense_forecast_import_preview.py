from __future__ import annotations

import asyncio
import unittest
from io import BytesIO
from typing import Any

from openpyxl import Workbook

from app.services import expense_forecast_import_preview as preview_module
from app.services.expense_forecast_import_preview import evaluate_expense_forecast_import_preview


def parsed_row(
    *,
    row_number: int = 4,
    owner_name: str = "",
    budget_subject: str = "差旅费",
    field_name: str = "month_forecast",
    field_label: str = "M2",
    month: int | None = 2,
    value: float = 100.0,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "owner_name": owner_name,
        "budget_subject": budget_subject,
        "field_name": field_name,
        "field_label": field_label,
        "month": month,
        "value": value,
        "error": error,
    }


def build_import_workbook() -> bytes:
    workbook = Workbook()
    ws = workbook.active
    ws.append(["预算科目", "M2", "业务报送"])
    ws.append(["差旅费", 100.0, 300.0])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class FakePreviewWorkflowSource:
    async def load_subject_lookup(self) -> tuple[dict[int, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        subject = {
            "id": 11,
            "parent_id": None,
            "subject_name": "差旅费",
            "is_leaf": True,
            "formula_text": None,
        }
        return {11: subject}, {"差旅费": [subject]}

    async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
        return [scope_value]

    async def load_actual_cutoff_month(self, year: int) -> int:
        return 1

    async def load_manage_department_map(self) -> dict[str, str]:
        return {"差旅费": "部门A"}

    async def load_forecast_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], float]:
        return {}

    async def load_rule_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int], dict[str, Any]]:
        return {("部门A", 11): {"id": 7, "scheme_code": "RESIDUAL_ALLOC"}}

    async def load_annual_input_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, str], float]:
        return {}

    async def load_calc_result_map(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
    ) -> dict[tuple[str, int, int], dict[str, Any]]:
        return {("部门A", 11, 2): {"calc_value": 88.0}}


class ExpenseForecastImportPreviewTests(unittest.TestCase):
    def evaluate(self, **overrides: Any):
        defaults: dict[str, Any] = {
            "parsed_rows": [parsed_row()],
            "import_mode": "overwrite",
            "actual_cutoff_month": 0,
            "is_group_import": False,
            "scope_value": "部门A",
            "target_group_name": "",
            "preview_owner_names": ["部门A"],
            "by_name": {
                "差旅费": [
                    {
                        "id": 11,
                        "subject_name": "差旅费",
                        "is_leaf": True,
                        "formula_text": None,
                    }
                ]
            },
            "selected_subject": None,
            "effective_manage_by_name": {},
            "forecast_map": {},
            "rule_map": {},
            "annual_input_map": {},
            "calc_result_map": {},
        }
        defaults.update(overrides)
        return evaluate_expense_forecast_import_preview(**defaults)

    def test_month_import_marks_auto_rule_override_and_normalizes_row(self) -> None:
        preview = self.evaluate(
            rule_map={("部门A", 11): {"id": 7, "scheme_code": "RESIDUAL_ALLOC"}},
            calc_result_map={("部门A", 11, 2): {"calc_value": 88.0}},
        )

        self.assertEqual(preview.insertable_cells, 1)
        self.assertEqual(preview.updatable_cells, 0)
        self.assertEqual(preview.skipped_cells, 0)
        self.assertEqual(preview.error_cells, 0)
        self.assertEqual(preview.items[0]["action"], "inserted")
        self.assertEqual(preview.items[0]["message"], "将按人工覆盖导入自动预测")
        self.assertEqual(
            preview.normalized_rows[0],
            {
                "scope_value": "部门A",
                "subject_id": 11,
                "budget_subject": "差旅费",
                "field_name": "month_forecast",
                "field_label": "M2",
                "month": 2,
                "value": 100.0,
                "action": "inserted",
                "rule_id": 7,
                "rule_scheme": "RESIDUAL_ALLOC",
                "system_value": 88.0,
            },
        )

    def test_append_existing_value_is_skipped_even_when_rule_is_auto(self) -> None:
        preview = self.evaluate(
            import_mode="append",
            forecast_map={("部门A", 11, 2): 99.0},
            rule_map={("部门A", 11): {"id": 7, "scheme_code": "RESIDUAL_ALLOC"}},
        )

        self.assertEqual(preview.insertable_cells, 0)
        self.assertEqual(preview.skipped_cells, 1)
        self.assertEqual(preview.items[0]["action"], "skipped")
        self.assertEqual(preview.items[0]["message"], "追加模式下保留已有预估值")
        self.assertEqual(preview.normalized_rows[0]["action"], "skipped")

    def test_skips_actual_months_missing_subjects_and_wrong_manage_department(self) -> None:
        preview = self.evaluate(
            scope_value="部门B",
            actual_cutoff_month=1,
            parsed_rows=[
                parsed_row(row_number=4, month=1, field_label="M1"),
                parsed_row(row_number=5, budget_subject="不存在科目"),
                parsed_row(row_number=6),
            ],
            effective_manage_by_name={"差旅费": ["部门A"]},
        )

        self.assertEqual(preview.insertable_cells, 0)
        self.assertEqual(preview.skipped_cells, 2)
        self.assertEqual(preview.error_cells, 1)
        self.assertEqual(preview.items[0]["message"], "该月份已有实际数，不能导入预估")
        self.assertEqual(preview.items[1]["message"], "预算科目不存在")
        self.assertIn("仅归口管理部门", preview.items[2]["message"])
        self.assertEqual(preview.normalized_rows, [])

    def test_group_subject_import_rejects_owner_outside_group(self) -> None:
        preview = self.evaluate(
            is_group_import=True,
            target_group_name="事业群A",
            preview_owner_names=["部门A"],
            parsed_rows=[parsed_row(owner_name="部门B")],
        )

        self.assertEqual(preview.error_cells, 1)
        self.assertEqual(preview.items[0]["owner_name"], "部门B")
        self.assertEqual(preview.items[0]["action"], "error")
        self.assertIn("不属于事业群", preview.items[0]["message"])

    def test_fills_annual_field_label_from_current_field_name(self) -> None:
        preview = self.evaluate(
            parsed_rows=[
                parsed_row(
                    field_name="business_submission",
                    field_label="",
                    month=None,
                    value=300.0,
                )
            ]
        )

        self.assertEqual(preview.items[0]["field_label"], "业务报送")
        self.assertEqual(preview.normalized_rows[0]["field_label"], "业务报送")

    def test_preview_workflow_builds_plan_parses_workbook_and_loads_context(self) -> None:
        preview = asyncio.run(
            preview_module.build_expense_forecast_import_preview_from_source(
                file_name="费用预测导入.xlsx",
                raw=build_import_workbook(),
                year=2026,
                forecast_version="V1",
                scope_type="owner",
                scope_value="部门A",
                import_mode="overwrite",
                group_name="",
                compile_mode="scope",
                subject_id=None,
                all_owner_scope_value="__ALL_OWNER_DEPARTMENTS__",
                source=FakePreviewWorkflowSource(),
            )
        )

        self.assertEqual(preview.file_name, "费用预测导入.xlsx")
        self.assertEqual(preview.import_mode, "overwrite")
        self.assertEqual(preview.actual_cutoff_month, 1)
        self.assertEqual(preview.preview_count, 2)
        self.assertEqual(preview.insertable_cells, 2)
        self.assertEqual(preview.updatable_cells, 0)
        self.assertEqual(preview.skipped_cells, 0)
        self.assertEqual(preview.error_cells, 0)
        self.assertEqual(preview.items[0]["message"], "将按人工覆盖导入自动预测")
        self.assertEqual(preview.normalized_rows[0]["system_value"], 88.0)


if __name__ == "__main__":
    unittest.main()
