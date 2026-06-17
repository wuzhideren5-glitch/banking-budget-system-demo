from __future__ import annotations

from pathlib import Path
import unittest

from app.services import expense_forecast_view_read_model as expense_forecast_view_read_model_module
from app.services.expense_forecast_view_read_model import (
    ExpenseForecastViewReadModelError,
    build_expense_forecast_group_read_model,
    build_expense_forecast_scope_read_model,
    build_expense_forecast_subject_read_model,
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


class FakeExpenseForecastViewSource:
    def __init__(self) -> None:
        self.annual_budget_owner_requests: list[list[str]] = []
        self.actual_cutoff_month_loads = 0

    async def load_budget_subject_rows(self) -> list[dict]:
        return SUBJECT_ROWS

    async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
        self.resolved_scope = (scope_type, scope_value)
        return ["部门A"]

    async def load_actual_cutoff_month(self, year: int) -> int:
        self.actual_cutoff_month_loads += 1
        return 1

    async def load_manage_department_map(self) -> dict[str, str]:
        return {}

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict:
        return {("部门A", "差旅费", 1): 100.0}

    async def load_annual_budget_map(self, year: int, owner_names: list[str]) -> dict:
        self.annual_budget_owner_requests.append(owner_names)
        return {("部门A", "差旅费"): 1000.0}

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {("部门A", 2, 2): 200.0}

    async def load_rule_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {}

    async def load_calc_result_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {}

    async def load_override_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {}

    async def load_annual_input_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {}


class EmptySubjectSource(FakeExpenseForecastViewSource):
    async def load_budget_subject_rows(self) -> list[dict]:
        return []


class ManagedSubjectSource(FakeExpenseForecastViewSource):
    def __init__(self) -> None:
        super().__init__()
        self.forecast_owner_requests: list[list[str]] = []

    async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
        self.resolved_scope = (scope_type, scope_value)
        return ["部门A", "部门B"]

    async def load_manage_department_map(self) -> dict[str, str]:
        return {"差旅费": "部门B"}

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict:
        return {("部门B", "差旅费", 1): 120.0}

    async def load_annual_budget_map(self, year: int, owner_names: list[str]) -> dict:
        self.annual_budget_owner_requests.append(owner_names)
        return {("部门B", "差旅费"): 1200.0}

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.forecast_owner_requests.append(owner_names)
        return {("部门B", 2, 2): 240.0}


class ParentSubjectSource(FakeExpenseForecastViewSource):
    async def load_budget_subject_rows(self) -> list[dict]:
        return [
            {
                "id": 1,
                "parent_id": None,
                "level_number": 1,
                "subject_name": "费用合计",
                "formula_text": None,
                "sort_order": 1,
                "is_leaf": False,
            }
        ]


class GroupViewSource(FakeExpenseForecastViewSource):
    def __init__(self) -> None:
        super().__init__()
        self.resolved_scopes: list[tuple[str, str]] = []
        self.subject_row_loads = 0
        self.manage_department_map_loads = 0
        self.actual_cutoff_month_loads = 0
        self.dynamic_owner_requests: list[tuple[str, list[str]]] = []

    async def load_budget_subject_rows(self) -> list[dict]:
        self.subject_row_loads += 1
        return SUBJECT_ROWS

    async def load_manage_department_map(self) -> dict[str, str]:
        self.manage_department_map_loads += 1
        return {}

    async def load_actual_cutoff_month(self, year: int) -> int:
        self.actual_cutoff_month_loads += 1
        return 1

    async def resolve_scope_owners(self, scope_type: str, scope_value: str) -> list[str]:
        self.resolved_scopes.append((scope_type, scope_value))
        if scope_type == "group":
            return ["部门A", "部门B"]
        return [scope_value]

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("actual", list(owner_names)))
        return {
            (owner_name, "差旅费", 1): 100.0 if owner_name == "部门A" else 300.0
            for owner_name in owner_names
        }

    async def load_annual_budget_map(self, year: int, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("annual_budget", list(owner_names)))
        return {
            (owner_name, "差旅费"): 1000.0 if owner_name == "部门A" else 3000.0
            for owner_name in owner_names
        }

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("forecast", list(owner_names)))
        return {
            (owner_name, 2, 2): 200.0 if owner_name == "部门A" else 600.0
            for owner_name in owner_names
        }

    async def load_rule_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("rule", list(owner_names)))
        return {}

    async def load_calc_result_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("calc", list(owner_names)))
        return {}

    async def load_override_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("override", list(owner_names)))
        return {}

    async def load_annual_input_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.dynamic_owner_requests.append(("annual_input", list(owner_names)))
        return {}


class ExpenseForecastViewReadModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_read_model_loads_context_and_builds_view(self) -> None:
        source = FakeExpenseForecastViewSource()

        view = await build_expense_forecast_scope_read_model(
            year=2026,
            forecast_version="V1",
            scope_type="owner",
            scope_value="部门A",
            source=source,
        )

        self.assertEqual(source.resolved_scope, ("owner", "部门A"))
        self.assertEqual(source.annual_budget_owner_requests, [["部门A"]])
        self.assertEqual(view["year"], 2026)
        self.assertEqual(view["forecast_version"], "V1")
        self.assertEqual(view["actual_cutoff_month"], 1)
        self.assertEqual([row["subject_name"] for row in view["rows"]], ["费用合计", "差旅费"])
        self.assertEqual(view["rows"][0]["months"][0]["value"], 100.0)
        self.assertEqual(view["rows"][1]["months"][1]["value"], 200.0)

    async def test_scope_read_model_rejects_missing_budget_subject_tree(self) -> None:
        with self.assertRaisesRegex(ExpenseForecastViewReadModelError, "预算科目树"):
            await build_expense_forecast_scope_read_model(
                year=2026,
                forecast_version="V1",
                scope_type="owner",
                scope_value="部门A",
                source=EmptySubjectSource(),
            )

    async def test_subject_read_model_filters_owners_by_manage_department(self) -> None:
        source = ManagedSubjectSource()

        view = await build_expense_forecast_subject_read_model(
            year=2026,
            forecast_version="V1",
            scope_type="group",
            scope_value="事业群A",
            subject_id=2,
            source=source,
        )

        self.assertEqual(source.resolved_scope, ("group", "事业群A"))
        self.assertEqual(source.annual_budget_owner_requests, [["部门B"]])
        self.assertEqual(source.forecast_owner_requests, [["部门B"]])
        self.assertEqual(view["subject_id"], 2)
        self.assertEqual(view["subject_name"], "差旅费")
        self.assertEqual([row["owner_name"] for row in view["rows"]], ["部门B"])
        row = view["rows"][0]
        self.assertEqual(row["months"][0]["value"], 120.0)
        self.assertEqual(row["months"][1]["value"], 240.0)
        self.assertEqual(row["annual_budget"], 1200.0)

    async def test_subject_read_model_reuses_year_cutoff_context(self) -> None:
        source = ManagedSubjectSource()

        view = await build_expense_forecast_subject_read_model(
            year=2026,
            forecast_version="V1",
            scope_type="group",
            scope_value="事业群A",
            subject_id=2,
            source=source,
        )

        self.assertEqual(view["actual_cutoff_month"], 1)
        self.assertEqual(source.actual_cutoff_month_loads, 1)

    async def test_subject_read_model_rejects_non_leaf_subject(self) -> None:
        with self.assertRaisesRegex(ExpenseForecastViewReadModelError, "末级叶子预算科目"):
            await build_expense_forecast_subject_read_model(
                year=2026,
                forecast_version="V1",
                scope_type="owner",
                scope_value="部门A",
                subject_id=1,
                source=ParentSubjectSource(),
            )

    async def test_group_read_model_builds_owner_views_from_group_scope(self) -> None:
        source = GroupViewSource()

        view = await build_expense_forecast_group_read_model(
            year=2026,
            forecast_version="V1",
            group_name="事业群A",
            source=source,
        )

        self.assertEqual(
            source.resolved_scopes,
            [("group", "事业群A")],
        )
        self.assertEqual(view["group_name"], "事业群A")
        self.assertEqual(view["actual_cutoff_month"], 1)
        self.assertEqual([item["owner_name"] for item in view["owner_views"]], ["部门A", "部门B"])
        self.assertEqual(view["owner_views"][0]["rows"][1]["total_value"], 300.0)
        self.assertEqual(view["owner_views"][1]["rows"][1]["total_value"], 900.0)

    async def test_group_read_model_reuses_static_subject_context_across_owner_views(self) -> None:
        source = GroupViewSource()

        view = await build_expense_forecast_group_read_model(
            year=2026,
            forecast_version="V1",
            group_name="事业群A",
            source=source,
        )

        self.assertEqual([item["owner_name"] for item in view["owner_views"]], ["部门A", "部门B"])
        self.assertEqual(source.subject_row_loads, 1)
        self.assertEqual(source.manage_department_map_loads, 1)

    async def test_group_read_model_reuses_year_cutoff_context_across_owner_views(self) -> None:
        source = GroupViewSource()

        view = await build_expense_forecast_group_read_model(
            year=2026,
            forecast_version="V1",
            group_name="事业群A",
            source=source,
        )

        self.assertEqual(view["actual_cutoff_month"], 1)
        self.assertEqual(source.actual_cutoff_month_loads, 1)

    async def test_group_read_model_reuses_dynamic_context_across_owner_views(self) -> None:
        source = GroupViewSource()

        view = await build_expense_forecast_group_read_model(
            year=2026,
            forecast_version="V1",
            group_name="事业群A",
            source=source,
        )

        self.assertEqual([item["owner_name"] for item in view["owner_views"]], ["部门A", "部门B"])
        self.assertEqual(
            source.dynamic_owner_requests,
            [
                ("actual", ["部门A", "部门B"]),
                ("annual_budget", ["部门A", "部门B"]),
                ("forecast", ["部门A", "部门B"]),
                ("rule", ["部门A", "部门B"]),
                ("calc", ["部门A", "部门B"]),
                ("override", ["部门A", "部门B"]),
                ("annual_input", ["部门A", "部门B"]),
            ],
        )

    def test_scope_and_subject_read_models_share_view_context_loader(self) -> None:
        source_text = Path(expense_forecast_view_read_model_module.__file__).read_text(encoding="utf-8")

        self.assertIn("class ExpenseForecastViewContext:", source_text)
        self.assertIn("async def _load_expense_forecast_view_context(", source_text)
        for adapter_call in [
            "await source.load_actual_map",
            "await source.load_annual_budget_map",
            "await source.load_forecast_map",
            "await source.load_rule_map",
            "await source.load_calc_result_map",
            "await source.load_override_map",
            "await source.load_annual_input_map",
        ]:
            self.assertEqual(source_text.count(adapter_call), 1, adapter_call)


if __name__ == "__main__":
    unittest.main()
