from __future__ import annotations

import unittest

from app.services.expense_forecast_rule_simulation import (
    ExpenseForecastRuleSimulationError,
    simulate_expense_forecast_rule,
)


class FakeRuleSimulationSource:
    def __init__(self, *, has_subject: bool = True) -> None:
        self.has_subject = has_subject
        self.actual_cutoff_requests: list[int] = []
        self.actual_requests: list[dict] = []
        self.annual_requests: list[dict] = []
        self.forecast_requests: list[dict] = []
        self.calculate_request: dict | None = None

    async def load_subject_by_id(self, subject_id: int) -> dict | None:
        if not self.has_subject:
            return None
        return {"id": subject_id, "subject_name": "短信费"}

    async def load_actual_cutoff_month(self, year: int) -> int:
        self.actual_cutoff_requests.append(year)
        return 6

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict:
        self.actual_requests.append({"year": year, "owner_names": owner_names})
        return {("部门A", "短信费", 6): 100.0}

    async def load_annual_input_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.annual_requests.append({"year": year, "forecast_version": forecast_version, "owner_names": owner_names})
        return {("部门A", 11, "capital_advice"): 120.0}

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.forecast_requests.append({"year": year, "forecast_version": forecast_version, "owner_names": owner_names})
        return {("部门A", 11, 7): 20.0}

    async def calculate_rule_months(self, **kwargs) -> dict:
        self.calculate_request = kwargs
        return {
            8: {"value": 80.0, "basis": "basis-8"},
            7: {"value": 70.0, "basis": ""},
        }


def metric_expr_rule(**overrides) -> dict:
    rule = {
        "forecast_year": 2026,
        "forecast_version": " V1 ",
        "owner_name": "部门A",
        "subject_id": 11,
        "scheme_code": "METRIC_EXPR",
        "metric_source_priority": "inline_first",
        "effective_from_month": 7,
        "effective_to_month": 8,
        "params": [{"param_group": "metric_expr", "param_key": "expression", "param_value": "base"}],
        "variables": [{"variable_code": "base", "source_type": "annual_field", "source_key": "capital_advice"}],
    }
    rule.update(overrides)
    return rule


class ExpenseForecastRuleSimulationTests(unittest.IsolatedAsyncioTestCase):
    async def test_simulation_loads_context_and_returns_sorted_auto_months(self) -> None:
        source = FakeRuleSimulationSource()

        result = await simulate_expense_forecast_rule(rule=metric_expr_rule(), source=source)

        self.assertEqual(result["scheme_code"], "METRIC_EXPR")
        self.assertEqual(
            result["months"],
            [
                {
                    "month": 7,
                    "final_value": 70.0,
                    "system_value": 70.0,
                    "override_value": None,
                    "value_source": "auto",
                    "calc_basis_json": None,
                },
                {
                    "month": 8,
                    "final_value": 80.0,
                    "system_value": 80.0,
                    "override_value": None,
                    "value_source": "auto",
                    "calc_basis_json": "basis-8",
                },
            ],
        )
        self.assertEqual(source.actual_cutoff_requests, [2026])
        self.assertEqual(source.actual_requests, [{"year": 2026, "owner_names": ["部门A"]}])
        self.assertEqual(source.annual_requests, [{"year": 2026, "forecast_version": "V1", "owner_names": ["部门A"]}])
        self.assertEqual(source.forecast_requests, [{"year": 2026, "forecast_version": "V1", "owner_names": ["部门A"]}])
        assert source.calculate_request is not None
        self.assertEqual(source.calculate_request["rule"]["subject_name"], "短信费")
        self.assertEqual(source.calculate_request["rule"]["params"], metric_expr_rule()["params"])
        self.assertEqual(source.calculate_request["actual_cutoff_month"], 6)

    async def test_simulation_raises_when_subject_is_missing(self) -> None:
        source = FakeRuleSimulationSource(has_subject=False)

        with self.assertRaisesRegex(ExpenseForecastRuleSimulationError, "预算科目不存在"):
            await simulate_expense_forecast_rule(rule=metric_expr_rule(), source=source)

        self.assertIsNone(source.calculate_request)


if __name__ == "__main__":
    unittest.main()
