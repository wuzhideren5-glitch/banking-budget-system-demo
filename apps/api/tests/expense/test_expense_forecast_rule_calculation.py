from __future__ import annotations

import asyncio
import json
import unittest

from app.services.expense_forecast_rule_calculation import calculate_expense_forecast_rule_months


async def empty_metric_loader(_year: int, _source_key: str, _source_subkey: str | None) -> dict[int, float]:
    return {}


class ExpenseForecastRuleCalculationTests(unittest.TestCase):
    def test_manual_rule_returns_no_calculated_months(self) -> None:
        result = asyncio.run(
            calculate_expense_forecast_rule_months(
                rule={
                    "scheme_code": "MANUAL",
                    "effective_from_month": 1,
                    "effective_to_month": 12,
                    "params": [],
                    "variables": [],
                },
                year=2026,
                forecast_version="V1",
                owner_name="部门A",
                subject_id=11,
                subject_name="差旅费",
                actual_cutoff_month=3,
                annual_input_map={},
                actual_map={},
                forecast_map={},
                load_metric_source_month_map=empty_metric_loader,
            )
        )

        self.assertEqual(result, {})

    def test_residual_allocation_falls_back_to_equal_weights(self) -> None:
        result = asyncio.run(
            calculate_expense_forecast_rule_months(
                rule={
                    "scheme_code": "RESIDUAL_ALLOC",
                    "effective_from_month": 11,
                    "effective_to_month": 12,
                    "params": [
                        {
                            "param_group": "common",
                            "param_key": "allocation_mode",
                            "param_value": "custom",
                        }
                    ],
                    "variables": [],
                },
                year=2026,
                forecast_version="V1",
                owner_name="部门A",
                subject_id=11,
                subject_name="差旅费",
                actual_cutoff_month=10,
                annual_input_map={("部门A", 11, "capital_advice"): 300.0},
                actual_map={("部门A", "差旅费", 1): 100.0},
                forecast_map={},
                load_metric_source_month_map=empty_metric_loader,
            )
        )

        self.assertEqual(result[11]["value"], 100.0)
        self.assertEqual(result[12]["value"], 100.0)
        basis = json.loads(result[12]["basis"])
        self.assertEqual(basis["scheme"], "RESIDUAL_ALLOC")
        self.assertEqual(basis["capital_advice"], 300.0)
        self.assertEqual(basis["actual_cumulative"], 100.0)
        self.assertEqual(basis["remaining"], 200.0)
        self.assertEqual(basis["allocation_mode"], "custom")
        self.assertEqual(basis["rounding_mode"], "last_month_adjust")

    def test_metric_expression_resolves_metric_tree_variables(self) -> None:
        loader_calls: list[tuple[int, str, str | None]] = []

        async def metric_loader(year: int, source_key: str, source_subkey: str | None) -> dict[int, float]:
            loader_calls.append((year, source_key, source_subkey))
            return {1: 5.0, 2: 6.0}

        result = asyncio.run(
            calculate_expense_forecast_rule_months(
                rule={
                    "scheme_code": "METRIC_EXPR",
                    "effective_from_month": 1,
                    "effective_to_month": 2,
                    "params": [
                        {
                            "param_group": "metric_expr",
                            "param_key": "expression",
                            "param_value": "metric_a + capital_advice / remaining_months + IF(month_index > 1, 10, 0)",
                        }
                    ],
                    "variables": [
                        {
                            "variable_code": "metric_a",
                            "source_type": "metric_tree",
                            "source_key": "FEE.METRIC.A",
                            "source_subkey": "",
                            "default_value": 1.0,
                        }
                    ],
                },
                year=2026,
                forecast_version="V1",
                owner_name="部门A",
                subject_id=11,
                subject_name="差旅费",
                actual_cutoff_month=0,
                annual_input_map={("部门A", 11, "capital_advice"): 100.0},
                actual_map={},
                forecast_map={},
                load_metric_source_month_map=metric_loader,
            )
        )

        self.assertEqual(result[1]["value"], 55.0)
        self.assertEqual(result[2]["value"], 116.0)
        self.assertEqual(loader_calls, [(2026, "FEE.METRIC.A", None), (2026, "FEE.METRIC.A", None)])
        month_two_basis = json.loads(result[2]["basis"])
        self.assertEqual(month_two_basis["scheme"], "METRIC_EXPR")
        self.assertEqual(month_two_basis["variables"]["metric_a"], 6.0)
        self.assertEqual(month_two_basis["variables"]["remaining_months"], 1)


if __name__ == "__main__":
    unittest.main()
