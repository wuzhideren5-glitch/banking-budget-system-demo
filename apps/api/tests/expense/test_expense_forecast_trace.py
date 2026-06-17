from __future__ import annotations

import unittest

from app.services import expense_forecast_trace as trace_module
from app.services.expense_forecast_trace import build_expense_forecast_trace_read_model


class FakeTraceSource:
    def __init__(self) -> None:
        self.requests: list[tuple[str, int, str, tuple[str, ...]]] = []

    async def load_calc_result_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("calc", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11, 2): {
                "calc_value": 120.0,
                "calc_basis_json": '{"basis":"auto"}',
            }
        }

    async def load_override_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("override", year, forecast_version, tuple(owner_names)))
        return {}

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("forecast", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11, 1): 100.0,
            ("部门A", 11, 2): 120.0,
        }

    async def load_rule_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        self.requests.append(("rule", year, forecast_version, tuple(owner_names)))
        return {
            ("部门A", 11): {
                "id": 7,
                "scheme_code": "RESIDUAL_ALLOC",
            }
        }


class ExpenseForecastTraceTests(unittest.TestCase):
    def test_trace_marks_manual_auto_and_override_months(self) -> None:
        trace = build_expense_forecast_trace_read_model(
            owner_name="部门A",
            subject_id=11,
            calc_map={
                ("部门A", 11, 2): {
                    "calc_value": 120.0,
                    "calc_basis_json": '{"basis":"auto"}',
                },
                ("部门A", 11, 3): {
                    "calc_value": 130.0,
                    "calc_basis_json": '{"basis":"auto"}',
                },
            },
            override_map={
                ("部门A", 11, 3): {
                    "system_value": 130.0,
                    "override_value": 150.0,
                    "override_reason": "管理调整",
                }
            },
            forecast_map={
                ("部门A", 11, 1): 100.0,
                ("部门A", 11, 2): 120.0,
                ("部门A", 11, 3): 150.0,
            },
            rule={"id": 7, "scheme_code": "RESIDUAL_ALLOC"},
        )

        self.assertEqual(trace.rule_id, 7)
        self.assertEqual(trace.rule_scheme, "RESIDUAL_ALLOC")
        self.assertEqual(len(trace.items), 12)
        self.assertEqual(trace.items[0].value_source, "manual")
        self.assertEqual(trace.items[0].final_value, 100.0)
        self.assertIsNone(trace.items[0].system_value)
        self.assertEqual(trace.items[1].value_source, "auto")
        self.assertEqual(trace.items[1].system_value, 120.0)
        self.assertEqual(trace.items[1].calc_basis_json, '{"basis":"auto"}')
        self.assertEqual(trace.items[2].value_source, "override")
        self.assertEqual(trace.items[2].final_value, 150.0)
        self.assertEqual(trace.items[2].system_value, 130.0)
        self.assertEqual(trace.items[2].override_value, 150.0)
        self.assertEqual(trace.items[2].calc_basis_json, '{"basis":"auto"}')


class ExpenseForecastTraceSourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_trace_read_model_loads_month_maps_from_source(self) -> None:
        source = FakeTraceSource()

        trace = await trace_module.build_expense_forecast_trace_read_model_from_source(
            year=2026,
            forecast_version="V1",
            owner_name="部门A",
            subject_id=11,
            source=source,
        )

        self.assertEqual(
            source.requests,
            [
                ("calc", 2026, "V1", ("部门A",)),
                ("override", 2026, "V1", ("部门A",)),
                ("forecast", 2026, "V1", ("部门A",)),
                ("rule", 2026, "V1", ("部门A",)),
            ],
        )
        self.assertEqual(trace.rule_id, 7)
        self.assertEqual(trace.items[0].final_value, 100.0)
        self.assertEqual(trace.items[1].value_source, "auto")


if __name__ == "__main__":
    unittest.main()
