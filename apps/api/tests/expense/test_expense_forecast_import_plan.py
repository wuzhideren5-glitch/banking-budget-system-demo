from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import Workbook

from app.services.expense_forecast_import_plan import (
    ExpenseForecastImportPlanError,
    build_expense_forecast_import_plan,
    parse_expense_forecast_import_rows_for_plan,
)


ALL_OWNER_SCOPE_VALUE = "__ALL_OWNER_DEPARTMENTS__"


def workbook_bytes(rows: list[list[object | None]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def subject_row(
    *,
    subject_id: int = 11,
    subject_name: str = "差旅费",
    is_leaf: bool = True,
    formula_text: str | None = None,
) -> dict[str, object | None]:
    return {
        "id": subject_id,
        "subject_name": subject_name,
        "is_leaf": is_leaf,
        "formula_text": formula_text,
    }


class ExpenseForecastImportPlanTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_owner_scope_plan_uses_regular_import_contract(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            self.fail(f"unexpected owner lookup: {scope_type=} {scope_value=}")

        plan = await build_expense_forecast_import_plan(
            scope_type="owner",
            scope_value="部门A",
            group_name="",
            compile_mode="unknown",
            subject_id=None,
            subjects_by_id={},
            all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
            resolve_scope_owners=resolve_scope_owners,
        )

        self.assertEqual(plan.normalized_compile_mode, "scope")
        self.assertFalse(plan.is_group_import)
        self.assertEqual(plan.allowed_owner_names, ["部门A"])
        self.assertIsNone(plan.selected_subject)

        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["元数据"],
                ["预算科目", "M1"],
                ["差旅费", 100],
            ]
        )
        rows = parse_expense_forecast_import_rows_for_plan(raw=raw, plan=plan)

        self.assertEqual(rows[0]["owner_name"], "")
        self.assertEqual(rows[0]["budget_subject"], "差旅费")
        self.assertEqual(rows[0]["value"], 100.0)

    async def test_compile_mode_normalization_accepts_trimmed_case_insensitive_value(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            self.fail(f"unexpected owner lookup: {scope_type=} {scope_value=}")

        plan = await build_expense_forecast_import_plan(
            scope_type="owner",
            scope_value="部门A",
            group_name="",
            compile_mode=" SUBJECT ",
            subject_id=11,
            subjects_by_id={11: subject_row()},
            all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
            resolve_scope_owners=resolve_scope_owners,
        )

        self.assertEqual(plan.normalized_compile_mode, "subject")

    async def test_group_subject_plan_resolves_group_and_parses_subject_workbook(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            self.assertEqual(scope_type, "group")
            self.assertEqual(scope_value, "事业群A")
            return ["部门A", "部门B"]

        plan = await build_expense_forecast_import_plan(
            scope_type="owner",
            scope_value=ALL_OWNER_SCOPE_VALUE,
            group_name="事业群A",
            compile_mode="subject",
            subject_id=11,
            subjects_by_id={11: subject_row()},
            all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
            resolve_scope_owners=resolve_scope_owners,
        )

        self.assertTrue(plan.is_group_import)
        self.assertEqual(plan.normalized_compile_mode, "subject")
        self.assertEqual(plan.target_group_name, "事业群A")
        self.assertEqual(plan.allowed_owner_names, ["部门A", "部门B"])
        self.assertEqual(plan.selected_subject, subject_row())

        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["费用归属部门", "M1", "业务报送"],
                ["部门A", 100, 200],
            ]
        )
        rows = parse_expense_forecast_import_rows_for_plan(raw=raw, plan=plan)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["owner_name"], "部门A")
        self.assertEqual(rows[0]["budget_subject"], "差旅费")
        self.assertEqual(rows[1]["field_name"], "business_submission")

    async def test_single_owner_subject_plan_supplies_default_owner(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            self.fail(f"unexpected owner lookup: {scope_type=} {scope_value=}")

        plan = await build_expense_forecast_import_plan(
            scope_type="owner",
            scope_value="部门A",
            group_name="",
            compile_mode="subject",
            subject_id=11,
            subjects_by_id={11: subject_row()},
            all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
            resolve_scope_owners=resolve_scope_owners,
        )
        raw = workbook_bytes(
            [
                ["费用预测表"],
                ["费用归属部门", "M1"],
                [None, 100],
            ]
        )
        rows = parse_expense_forecast_import_rows_for_plan(raw=raw, plan=plan)

        self.assertEqual(rows[0]["owner_name"], "部门A")
        self.assertEqual(rows[0]["budget_subject"], "差旅费")

    async def test_rejects_non_owner_scope(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            return []

        with self.assertRaisesRegex(ExpenseForecastImportPlanError, "费用归属部门口径"):
            await build_expense_forecast_import_plan(
                scope_type="group",
                scope_value="事业群A",
                group_name="",
                compile_mode="scope",
                subject_id=None,
                subjects_by_id={},
                all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
                resolve_scope_owners=resolve_scope_owners,
            )

    async def test_rejects_missing_subject_id(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            return []

        with self.assertRaisesRegex(ExpenseForecastImportPlanError, "缺少 subject_id"):
            await build_expense_forecast_import_plan(
                scope_type="owner",
                scope_value="部门A",
                group_name="",
                compile_mode="subject",
                subject_id=None,
                subjects_by_id={},
                all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
                resolve_scope_owners=resolve_scope_owners,
            )

    async def test_rejects_non_leaf_subject(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            return []

        with self.assertRaisesRegex(ExpenseForecastImportPlanError, "末级叶子预算科目"):
            await build_expense_forecast_import_plan(
                scope_type="owner",
                scope_value="部门A",
                group_name="",
                compile_mode="subject",
                subject_id=11,
                subjects_by_id={11: subject_row(is_leaf=False)},
                all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
                resolve_scope_owners=resolve_scope_owners,
            )

    async def test_group_import_requires_group_name(self) -> None:
        async def resolve_scope_owners(scope_type: str, scope_value: str) -> list[str]:
            return []

        with self.assertRaisesRegex(ExpenseForecastImportPlanError, "缺少事业群参数"):
            await build_expense_forecast_import_plan(
                scope_type="owner",
                scope_value=ALL_OWNER_SCOPE_VALUE,
                group_name="",
                compile_mode="scope",
                subject_id=None,
                subjects_by_id={},
                all_owner_scope_value=ALL_OWNER_SCOPE_VALUE,
                resolve_scope_owners=resolve_scope_owners,
            )


if __name__ == "__main__":
    unittest.main()
