from __future__ import annotations

import unittest

from app.services.expense_forecast_rule_detail import (
    ExpenseForecastRuleDetailNotFound,
    load_expense_forecast_rule_detail,
)


class FakeRuleDetailSource:
    def __init__(self) -> None:
        self.load_requests: list[dict] = []
        self.identity_requests: list[int] = []

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
        if year == 2026 and forecast_version == "V1" and owner_names is None:
            return [{"id": 7, "forecast_version": "V1"}]
        if year == 2025 and forecast_version == "ARCHIVE" and owner_names == ["部门A"] and subject_id == 11:
            return [{"id": 8, "forecast_version": "ARCHIVE"}]
        return []

    async def load_rule_identity(self, *, rule_id: int) -> dict | None:
        self.identity_requests.append(rule_id)
        if rule_id == 8:
            return {
                "forecast_year": 2025,
                "forecast_version": " ARCHIVE ",
                "owner_name": " 部门A ",
                "subject_id": 11,
            }
        if rule_id == 9:
            return {
                "forecast_year": 2025,
                "forecast_version": "MISSING_ROW",
                "owner_name": "部门B",
                "subject_id": 12,
            }
        return None


class ExpenseForecastRuleDetailTests(unittest.IsolatedAsyncioTestCase):
    async def test_detail_returns_rule_from_default_version_without_identity_lookup(self) -> None:
        source = FakeRuleDetailSource()

        detail = await load_expense_forecast_rule_detail(
            rule_id=7,
            default_year=2026,
            default_version="V1",
            source=source,
        )

        self.assertEqual(detail, {"id": 7, "forecast_version": "V1"})
        self.assertEqual(source.identity_requests, [])
        self.assertEqual(source.load_requests, [{"year": 2026, "forecast_version": "V1", "owner_names": None, "subject_id": None}])

    async def test_detail_uses_identity_to_load_cross_version_rule(self) -> None:
        source = FakeRuleDetailSource()

        detail = await load_expense_forecast_rule_detail(
            rule_id=8,
            default_year=2026,
            default_version="V1",
            source=source,
        )

        self.assertEqual(detail, {"id": 8, "forecast_version": "ARCHIVE"})
        self.assertEqual(source.identity_requests, [8])
        self.assertEqual(
            source.load_requests[-1],
            {"year": 2025, "forecast_version": "ARCHIVE", "owner_names": ["部门A"], "subject_id": 11},
        )

    async def test_detail_raises_when_identity_or_target_row_is_missing(self) -> None:
        source = FakeRuleDetailSource()

        with self.assertRaisesRegex(ExpenseForecastRuleDetailNotFound, "预测规则不存在"):
            await load_expense_forecast_rule_detail(
                rule_id=404,
                default_year=2026,
                default_version="V1",
                source=source,
            )
        with self.assertRaisesRegex(ExpenseForecastRuleDetailNotFound, "预测规则不存在"):
            await load_expense_forecast_rule_detail(
                rule_id=9,
                default_year=2026,
                default_version="V1",
                source=source,
            )


if __name__ == "__main__":
    unittest.main()
