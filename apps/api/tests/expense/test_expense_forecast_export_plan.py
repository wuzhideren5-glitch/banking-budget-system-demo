from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.services.expense_forecast_export_plan import (
    ExpenseForecastExportPlanError,
    build_expense_forecast_export_plan,
    build_expense_forecast_group_export_plan,
)


class ExpenseForecastExportPlanTests(unittest.TestCase):
    def test_scope_export_plan_defaults_version_and_compile_mode(self) -> None:
        plan = build_expense_forecast_export_plan(
            year=2026,
            forecast_version="",
            default_version="260519v1",
            scope_type="owner",
            scope_value=" 部门A ",
            compile_mode="unknown",
            subject_id=None,
        )

        self.assertEqual(plan.year, 2026)
        self.assertEqual(plan.forecast_version, "260519v1")
        self.assertEqual(plan.scope_type, "owner")
        self.assertEqual(plan.scope_value, "部门A")
        self.assertEqual(plan.compile_mode, "scope")
        self.assertIsNone(plan.subject_id)

    def test_subject_export_plan_requires_subject_id(self) -> None:
        with self.assertRaisesRegex(ExpenseForecastExportPlanError, "缺少 subject_id"):
            build_expense_forecast_export_plan(
                year=2026,
                forecast_version="V1",
                default_version="260519v1",
                scope_type="owner",
                scope_value="部门A",
                compile_mode="subject",
                subject_id=None,
            )

    def test_subject_export_plan_normalizes_subject_id(self) -> None:
        plan = build_expense_forecast_export_plan(
            year=2026,
            forecast_version=" V1 ",
            default_version="260519v1",
            scope_type="owner",
            scope_value="部门A",
            compile_mode="subject",
            subject_id=11,
        )

        self.assertEqual(plan.forecast_version, "V1")
        self.assertEqual(plan.compile_mode, "subject")
        self.assertEqual(plan.subject_id, 11)

    def test_export_plan_rejects_unknown_scope_type(self) -> None:
        with self.assertRaisesRegex(ExpenseForecastExportPlanError, "编制口径仅支持"):
            build_expense_forecast_export_plan(
                year=2026,
                forecast_version="V1",
                default_version="260519v1",
                scope_type="bad",  # type: ignore[arg-type]
                scope_value="部门A",
                compile_mode="scope",
                subject_id=None,
            )

    def test_group_export_plan_matches_group_and_sorts_owner_names(self) -> None:
        plan = build_expense_forecast_group_export_plan(
            year=2026,
            forecast_version="",
            default_version="260519v1",
            group_name="事业群A",
            owner_group_options=[
                SimpleNamespace(group_value="事业群B", owner_options=[SimpleNamespace(value="部门Z")]),
                SimpleNamespace(
                    group_value="事业群A",
                    owner_options=[
                        SimpleNamespace(value="长期部门"),
                        SimpleNamespace(value="部"),
                        SimpleNamespace(value="部门A"),
                        SimpleNamespace(value=""),
                    ],
                ),
            ],
        )

        self.assertEqual(plan.year, 2026)
        self.assertEqual(plan.forecast_version, "260519v1")
        self.assertEqual(plan.group_name, "事业群A")
        self.assertEqual(plan.owner_names, ["部", "部门A", "长期部门"])

    def test_group_export_plan_rejects_missing_group(self) -> None:
        with self.assertRaisesRegex(ExpenseForecastExportPlanError, '事业群 "事业群X" 不存在'):
            build_expense_forecast_group_export_plan(
                year=2026,
                forecast_version="V1",
                default_version="260519v1",
                group_name="事业群X",
                owner_group_options=[SimpleNamespace(group_value="事业群A", owner_options=[])],
            )


if __name__ == "__main__":
    unittest.main()
