from __future__ import annotations

import unittest

from app.services.expense_forecast_rule_copy import copy_expense_forecast_rules_from_version


class FakeRuleCopySource:
    def __init__(self) -> None:
        self.load_requests: list[dict] = []
        self.saved_rules: list[dict] = []

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
        if forecast_version == "SOURCE":
            return [
                {
                    "id": 7,
                    "forecast_year": 2026,
                    "forecast_version": "SOURCE",
                    "owner_name": " 部门A ",
                    "subject_id": 11,
                    "scheme_code": "METRIC_EXPR",
                    "enabled": 1,
                    "allow_manual_override": 0,
                    "auto_refresh_enabled": 1,
                    "manual_recalc_enabled": 1,
                    "metric_source_priority": "inline_first",
                    "effective_from_month": 2,
                    "effective_to_month": 12,
                    "priority": 88,
                    "remark": "规则说明",
                    "params": [{"param_key": "expression", "param_value": "a+b"}],
                    "variables": [{"variable_code": "a", "source_type": "metric_tree"}],
                },
                {
                    "id": 8,
                    "forecast_year": 2026,
                    "forecast_version": "SOURCE",
                    "owner_name": "部门B",
                    "subject_id": 12,
                    "scheme_code": "MANUAL",
                    "enabled": True,
                    "allow_manual_override": True,
                    "auto_refresh_enabled": False,
                    "manual_recalc_enabled": False,
                    "metric_source_priority": "metric_first",
                    "effective_from_month": 1,
                    "effective_to_month": 10,
                    "priority": 100,
                    "remark": None,
                    "params": [],
                    "variables": [],
                },
            ]
        if forecast_version == "TARGET" and owner_names == ["部门A"] and subject_id == 11:
            return [{"id": 17}]
        return []

    async def save_rule(self, *, rule: dict, rule_id: int | None) -> None:
        self.saved_rules.append({"rule": rule, "rule_id": rule_id})


class ExpenseForecastRuleCopyTests(unittest.IsolatedAsyncioTestCase):
    async def test_copy_rules_to_target_version_updates_existing_rule_and_inserts_missing_rule(self) -> None:
        source = FakeRuleCopySource()

        copied = await copy_expense_forecast_rules_from_version(
            year=2026,
            source_version=" SOURCE ",
            target_version=" TARGET ",
            source=source,
        )

        self.assertEqual(copied, 2)
        self.assertEqual(
            source.load_requests,
            [
                {
                    "year": 2026,
                    "forecast_version": "SOURCE",
                    "owner_names": None,
                    "subject_id": None,
                },
                {
                    "year": 2026,
                    "forecast_version": "TARGET",
                    "owner_names": ["部门A"],
                    "subject_id": 11,
                },
                {
                    "year": 2026,
                    "forecast_version": "TARGET",
                    "owner_names": ["部门B"],
                    "subject_id": 12,
                },
            ],
        )
        self.assertEqual([item["rule_id"] for item in source.saved_rules], [17, None])
        first_rule = source.saved_rules[0]["rule"]
        self.assertEqual(first_rule["forecast_year"], 2026)
        self.assertEqual(first_rule["forecast_version"], "TARGET")
        self.assertEqual(first_rule["owner_name"], "部门A")
        self.assertEqual(first_rule["subject_id"], 11)
        self.assertEqual(first_rule["scheme_code"], "METRIC_EXPR")
        self.assertTrue(first_rule["enabled"])
        self.assertFalse(first_rule["allow_manual_override"])
        self.assertEqual(first_rule["metric_source_priority"], "inline_first")
        self.assertEqual(first_rule["effective_from_month"], 2)
        self.assertEqual(first_rule["effective_to_month"], 12)
        self.assertEqual(first_rule["priority"], 88)
        self.assertEqual(first_rule["params"], [{"param_key": "expression", "param_value": "a+b"}])
        self.assertEqual(first_rule["variables"], [{"variable_code": "a", "source_type": "metric_tree"}])
        self.assertEqual(source.saved_rules[1]["rule"]["forecast_version"], "TARGET")

    async def test_copy_returns_zero_when_source_version_has_no_rules(self) -> None:
        source = FakeRuleCopySource()

        copied = await copy_expense_forecast_rules_from_version(
            year=2026,
            source_version="EMPTY",
            target_version="TARGET",
            source=source,
        )

        self.assertEqual(copied, 0)
        self.assertEqual(source.saved_rules, [])


if __name__ == "__main__":
    unittest.main()
