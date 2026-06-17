from __future__ import annotations

import unittest

from app.services.expense_forecast_view_model import (
    build_expense_forecast_scope_view_model,
    build_expense_forecast_subject_owner_view_model,
)


SUBJECT_ROWS = [
    {
        "id": 1,
        "parent_id": None,
        "level_number": 1,
        "subject_name": "费用合计",
        "formula_text": None,
        "sort_order": 1,
        "is_leaf": False,
    },
    {
        "id": 2,
        "parent_id": 1,
        "level_number": 2,
        "subject_name": "差旅费",
        "formula_text": None,
        "sort_order": 1,
        "is_leaf": True,
    },
]


class ExpenseForecastViewModelTests(unittest.TestCase):
    def test_owner_scope_builds_leaf_and_parent_rows_with_override_source(self) -> None:
        view = build_expense_forecast_scope_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="owner",
            scope_value="部门A",
            subject_rows=SUBJECT_ROWS,
            owners=["部门A"],
            actual_cutoff_month=1,
            effective_manage_by_id={},
            actual_map={("部门A", "差旅费", 1): 100.0},
            annual_budget_map={("部门A", "差旅费"): 1000.0},
            forecast_map={("部门A", 2, 2): 200.0},
            rule_map={
                ("部门A", 2): {
                    "id": 7,
                    "scheme_code": "RESIDUAL_ALLOC",
                    "allow_manual_override": True,
                }
            },
            calc_result_map={("部门A", 2, 2): {"calc_value": 180.0}},
            override_map={
                ("部门A", 2, 2): {
                    "system_value": 180.0,
                    "override_value": 200.0,
                    "override_reason": "管理调整",
                }
            },
            annual_input_map={
                ("部门A", 2, "business_submission"): 300.0,
                ("部门A", 2, "capital_advice"): 400.0,
            },
        )

        self.assertEqual(view["year"], 2026)
        self.assertEqual(view["actual_cutoff_month"], 1)
        self.assertEqual([row["subject_name"] for row in view["rows"]], ["费用合计", "差旅费"])
        parent, leaf = view["rows"]
        self.assertEqual(parent["months"][0]["value"], 100.0)
        self.assertEqual(parent["months"][1]["value"], 200.0)
        self.assertEqual(parent["months"][1]["value_source"], "aggregate")
        self.assertFalse(parent["months"][1]["editable"])
        self.assertEqual(parent["total_value"], 300.0)
        self.assertEqual(parent["annual_budget"], 1000.0)

        self.assertEqual(leaf["total_value"], 300.0)
        self.assertEqual(leaf["annual_budget"], 1000.0)
        self.assertEqual(leaf["forecast_budget_gap"], -700.0)
        self.assertEqual(leaf["budget_execution_rate"], 0.3)
        self.assertEqual(leaf["business_submission"], 300.0)
        self.assertEqual(leaf["capital_advice"], 400.0)
        self.assertEqual(leaf["capital_advice_gap"], 100.0)
        self.assertTrue(leaf["business_submission_editable"])
        self.assertTrue(leaf["capital_advice_editable"])
        self.assertTrue(leaf["rule_configured"])
        self.assertEqual(leaf["rule_scheme"], "RESIDUAL_ALLOC")
        self.assertEqual(leaf["rule_id"], 7)

        actual_month = leaf["months"][0]
        forecast_month = leaf["months"][1]
        self.assertEqual(actual_month["source"], "actual")
        self.assertEqual(actual_month["value_source"], "actual")
        self.assertFalse(actual_month["editable"])
        self.assertEqual(forecast_month["source"], "forecast")
        self.assertTrue(forecast_month["editable"])
        self.assertEqual(forecast_month["value_source"], "override")
        self.assertEqual(forecast_month["system_value"], 180.0)
        self.assertEqual(forecast_month["override_value"], 200.0)
        self.assertEqual(forecast_month["override_reason"], "管理调整")

    def test_manage_department_limits_group_scope_to_permitted_owner(self) -> None:
        view = build_expense_forecast_scope_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="group",
            scope_value="事业群A",
            subject_rows=SUBJECT_ROWS,
            owners=["部门A", "部门B"],
            actual_cutoff_month=0,
            effective_manage_by_id={2: "部门B"},
            actual_map={},
            annual_budget_map={
                ("部门A", "差旅费"): 1000.0,
                ("部门B", "差旅费"): 2000.0,
            },
            forecast_map={
                ("部门A", 2, 1): 10.0,
                ("部门B", 2, 1): 20.0,
            },
            rule_map={},
            calc_result_map={},
            override_map={},
            annual_input_map={},
        )

        self.assertEqual([row["subject_name"] for row in view["rows"]], ["费用合计", "差旅费"])
        parent, leaf = view["rows"]
        self.assertEqual(parent["months"][0]["value"], 20.0)
        self.assertEqual(parent["annual_budget"], 2000.0)
        self.assertEqual(leaf["months"][0]["value"], 20.0)
        self.assertEqual(leaf["annual_budget"], 2000.0)
        self.assertFalse(leaf["months"][0]["editable"])

    def test_manage_department_outside_scope_hides_subject(self) -> None:
        view = build_expense_forecast_scope_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="owner",
            scope_value="部门A",
            subject_rows=SUBJECT_ROWS,
            owners=["部门A"],
            actual_cutoff_month=0,
            effective_manage_by_id={2: "部门B"},
            actual_map={},
            annual_budget_map={("部门A", "差旅费"): 1000.0},
            forecast_map={("部门A", 2, 1): 10.0},
            rule_map={},
            calc_result_map={},
            override_map={},
            annual_input_map={},
        )

        self.assertEqual(view["rows"], [])

    def test_subject_owner_view_builds_owner_rows_with_override_source(self) -> None:
        view = build_expense_forecast_subject_owner_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="group",
            scope_value="事业群A",
            actual_cutoff_month=1,
            subject_id=2,
            subject_name="差旅费",
            owners=["部门A"],
            normalized_manage_department="",
            actual_map={("部门A", "差旅费", 1): 100.0},
            annual_budget_map={("部门A", "差旅费"): 1000.0},
            forecast_map={("部门A", 2, 2): 220.0},
            rule_map={
                ("部门A", 2): {
                    "id": 7,
                    "scheme_code": "RESIDUAL_ALLOC",
                    "allow_manual_override": False,
                }
            },
            calc_result_map={("部门A", 2, 2): {"calc_value": 180.0}},
            override_map={
                ("部门A", 2, 2): {
                    "system_value": 180.0,
                    "override_value": 220.0,
                    "override_reason": "管理调整",
                }
            },
            annual_input_map={("部门A", 2, "business_submission"): 300.0},
        )

        self.assertEqual(view["subject_id"], 2)
        self.assertEqual(view["subject_name"], "差旅费")
        self.assertEqual(len(view["rows"]), 1)
        row = view["rows"][0]
        self.assertEqual(row["owner_name"], "部门A")
        self.assertEqual(row["total_value"], 320.0)
        self.assertEqual(row["annual_budget"], 1000.0)
        self.assertEqual(row["forecast_budget_gap"], -680.0)
        self.assertEqual(row["budget_execution_rate"], 0.32)
        self.assertEqual(row["business_submission"], 300.0)
        self.assertEqual(row["capital_advice"], 1000.0)
        self.assertEqual(row["capital_advice_gap"], 700.0)
        self.assertTrue(row["business_submission_editable"])
        self.assertEqual(row["rule_scheme"], "RESIDUAL_ALLOC")
        self.assertEqual(row["rule_id"], 7)

        actual_month = row["months"][0]
        forecast_month = row["months"][1]
        self.assertEqual(actual_month["source"], "actual")
        self.assertEqual(actual_month["value"], 100.0)
        self.assertFalse(actual_month["editable"])
        self.assertEqual(forecast_month["source"], "forecast")
        self.assertEqual(forecast_month["value"], 220.0)
        self.assertFalse(forecast_month["editable"])
        self.assertEqual(forecast_month["value_source"], "override")
        self.assertEqual(forecast_month["system_value"], 180.0)
        self.assertEqual(forecast_month["override_reason"], "管理调整")

    def test_subject_owner_view_uses_manage_department_for_annual_editability(self) -> None:
        view = build_expense_forecast_subject_owner_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="group",
            scope_value="事业群A",
            actual_cutoff_month=0,
            subject_id=2,
            subject_name="差旅费",
            owners=["部门A", "部门B"],
            normalized_manage_department="部门B",
            actual_map={},
            annual_budget_map={},
            forecast_map={},
            rule_map={},
            calc_result_map={},
            override_map={},
            annual_input_map={},
        )

        self.assertEqual([row["owner_name"] for row in view["rows"]], ["部门A", "部门B"])
        self.assertFalse(view["rows"][0]["business_submission_editable"])
        self.assertFalse(view["rows"][0]["capital_advice_editable"])
        self.assertTrue(view["rows"][1]["business_submission_editable"])
        self.assertTrue(view["rows"][1]["capital_advice_editable"])

    def test_subject_owner_view_returns_empty_rows_when_no_owner_is_permitted(self) -> None:
        view = build_expense_forecast_subject_owner_view_model(
            year=2026,
            forecast_version="V1",
            scope_type="owner",
            scope_value="部门A",
            actual_cutoff_month=2,
            subject_id=2,
            subject_name="差旅费",
            owners=[],
            normalized_manage_department="部门B",
            actual_map={},
            annual_budget_map={},
            forecast_map={},
            rule_map={},
            calc_result_map={},
            override_map={},
            annual_input_map={},
        )

        self.assertEqual(view["actual_cutoff_month"], 2)
        self.assertEqual(view["rows"], [])


if __name__ == "__main__":
    unittest.main()
