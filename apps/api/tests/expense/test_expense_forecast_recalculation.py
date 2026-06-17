from __future__ import annotations

import unittest

from app.services.expense_forecast_recalculation import recalculate_expense_forecast_rules


class FakeRecalculationSource:
    def __init__(self) -> None:
        self.saved_rows = []
        self.rule_owner_requests: list[list[str]] = []

    async def load_scope_rows(self) -> list[tuple[str, str, str]]:
        return [("微众银行", "事业群A", "部门A"), ("微众银行", "事业群A", "")]

    async def load_rule_rows(
        self,
        *,
        year: int,
        forecast_version: str,
        owner_names: list[str],
        subject_id: int | None,
    ) -> list[dict]:
        self.rule_owner_requests.append(owner_names)
        return [
            {
                "id": 7,
                "enabled": True,
                "owner_name": "部门A",
                "subject_id": 11,
                "subject_name": "差旅费",
                "scheme_code": "RESIDUAL_ALLOC",
                "effective_from_month": 11,
                "effective_to_month": 12,
                "params": [],
                "variables": [],
            }
        ]

    async def load_actual_cutoff_month(self, year: int) -> int:
        return 10

    async def load_actual_map(self, year: int, owner_names: list[str]) -> dict:
        return {("部门A", "差旅费", 1): 100.0}

    async def load_annual_input_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {("部门A", 11, "capital_advice"): 300.0}

    async def load_forecast_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {}

    async def load_override_map(self, *, year: int, forecast_version: str, owner_names: list[str]) -> dict:
        return {
            ("部门A", 11, 11): {
                "override_value": 120.0,
            }
        }

    async def load_metric_source_month_map(
        self,
        year: int,
        indicator_code: str,
        product_code: str | None = None,
    ) -> dict[int, float]:
        return {}

    async def save_recalculation_results(
        self,
        *,
        year: int,
        forecast_version: str,
        rows: list,
        now: str,
    ) -> int:
        self.saved_rows = rows
        self.saved_now = now
        return len(rows)


class ExpenseForecastRecalculationTests(unittest.IsolatedAsyncioTestCase):
    async def test_recalculates_enabled_rules_from_all_scope_owners_and_preserves_overrides(self) -> None:
        source = FakeRecalculationSource()

        rule_count, updated_cells = await recalculate_expense_forecast_rules(
            year=2026,
            forecast_version="V1",
            source=source,
            now="2026-06-04T12:00:00Z",
        )

        self.assertEqual(source.rule_owner_requests, [["部门A"]])
        self.assertEqual(rule_count, 1)
        self.assertEqual(updated_cells, 2)
        self.assertEqual(source.saved_now, "2026-06-04T12:00:00Z")
        self.assertEqual([row.month for row in source.saved_rows], [11, 12])
        self.assertEqual([row.calc_value for row in source.saved_rows], [100.0, 100.0])
        self.assertTrue(source.saved_rows[0].has_override)
        self.assertEqual(source.saved_rows[0].override_value, 120.0)
        self.assertFalse(source.saved_rows[1].has_override)

    async def test_recalculate_returns_zero_when_no_owners_are_available(self) -> None:
        class EmptyOwnerSource(FakeRecalculationSource):
            async def load_scope_rows(self) -> list[tuple[str, str, str]]:
                return [("微众银行", "事业群A", "")]

        source = EmptyOwnerSource()

        result = await recalculate_expense_forecast_rules(
            year=2026,
            forecast_version="V1",
            source=source,
            now="2026-06-04T12:00:00Z",
        )

        self.assertEqual(result, (0, 0))
        self.assertEqual(source.rule_owner_requests, [])

    async def test_manual_recalculation_skips_rules_that_disallow_manual_recalc(self) -> None:
        class MixedManualSource(FakeRecalculationSource):
            async def load_rule_rows(
                self,
                *,
                year: int,
                forecast_version: str,
                owner_names: list[str],
                subject_id: int | None,
            ) -> list[dict]:
                rows = await super().load_rule_rows(
                    year=year,
                    forecast_version=forecast_version,
                    owner_names=owner_names,
                    subject_id=subject_id,
                )
                rows[0]["manual_recalc_enabled"] = True
                rows.append({**rows[0], "id": 8, "manual_recalc_enabled": False})
                rows.append({**rows[0], "id": 9, "enabled": False, "manual_recalc_enabled": True})
                return rows

        manual_source = MixedManualSource()
        auto_source = MixedManualSource()

        manual_result = await recalculate_expense_forecast_rules(
            year=2026,
            forecast_version="V1",
            source=manual_source,
            now="2026-06-04T12:00:00Z",
        )
        auto_result = await recalculate_expense_forecast_rules(
            year=2026,
            forecast_version="V1",
            source=auto_source,
            now="2026-06-04T12:00:00Z",
            trigger="auto",
        )

        self.assertEqual(manual_result, (1, 2))
        self.assertEqual([row.rule_id for row in manual_source.saved_rows], [7, 7])
        self.assertEqual(auto_result, (2, 4))
        self.assertEqual([row.rule_id for row in auto_source.saved_rows], [7, 7, 8, 8])


if __name__ == "__main__":
    unittest.main()
