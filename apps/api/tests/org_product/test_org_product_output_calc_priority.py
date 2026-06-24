from __future__ import annotations

import unittest

from app.routers.org_product_helpers import (
    _lookup_entry_annual_value,
    _lookup_entry_month_value,
    _normalize_calc_role,
    _org_product_annual_value_from_entry,
    _org_product_month_value_from_entry,
    _org_product_should_use_annual_formula,
    _org_product_value_from_entry,
    _parse_data_entry_annual_value,
    _parse_data_entry_month_value,
)


class OrgProductOutputCalcPriorityTests(unittest.TestCase):
    def test_normalize_calc_role_defaults_to_entry_overrides(self) -> None:
        self.assertEqual(_normalize_calc_role(None), "entry_overrides_formula")
        self.assertEqual(_normalize_calc_role(""), "entry_overrides_formula")

    def test_normalize_calc_role_respects_explicit_values(self) -> None:
        self.assertEqual(_normalize_calc_role("entry"), "entry")
        self.assertEqual(_normalize_calc_role("formula"), "formula")
        self.assertEqual(_normalize_calc_role("entry_overrides_formula"), "entry_overrides_formula")

    def test_normalize_calc_role_formula_when_manual_entry_disallowed(self) -> None:
        self.assertEqual(_normalize_calc_role(None, allow_manual_entry=0), "formula")
        self.assertEqual(_normalize_calc_role("entry", allow_manual_entry=0), "entry")

    def test_month_entry_priority_for_entry_overrides_role(self) -> None:
        meta = {"calc_role": "entry_overrides_formula", "allow_manual_entry": 1}
        self.assertTrue(_org_product_month_value_from_entry(meta, 100.0))
        self.assertFalse(_org_product_month_value_from_entry(meta, None))

    def test_month_entry_skipped_for_formula_role(self) -> None:
        meta = {"calc_role": "formula", "allow_manual_entry": 1}
        self.assertFalse(_org_product_month_value_from_entry(meta, 100.0))

    def test_month_entry_always_used_for_entry_role(self) -> None:
        meta = {"calc_role": "entry", "allow_manual_entry": 0}
        self.assertTrue(_org_product_month_value_from_entry(meta, 12.5))

    def test_annual_entry_priority_for_year_forecast(self) -> None:
        meta = {"calc_role": "entry_overrides_formula", "allow_manual_entry": 1}
        self.assertTrue(_org_product_annual_value_from_entry(meta, 999.0))
        self.assertFalse(_org_product_annual_value_from_entry(meta, None))

    def test_annual_entry_skipped_for_formula_role(self) -> None:
        meta = {"calc_role": "formula", "allow_manual_entry": 1}
        self.assertFalse(_org_product_annual_value_from_entry(meta, 999.0))

    def test_lookup_entry_month_and_annual_by_metric_id(self) -> None:
        entry_months = {"AA.01": [None, 10.0, None, None, None, None, None, None, None, None, None, None]}
        entry_annual = {"metric-1": 888.0}
        meta = {"id": "metric-1", "calc_role": "entry_overrides_formula", "allow_manual_entry": 1}
        self.assertEqual(_lookup_entry_month_value(entry_months, "AA.01", meta, 2), 10.0)
        self.assertEqual(_lookup_entry_annual_value(entry_annual, "AA.01", meta), 888.0)

    def test_parse_data_entry_annual_and_month_values(self) -> None:
        values = {
            "year_forecast": "1,234.5",
            "months": {"a1": "100", "f2": "200"},
        }
        self.assertEqual(_parse_data_entry_annual_value(values), 1234.5)
        self.assertEqual(_parse_data_entry_month_value(values, 1), 100.0)
        self.assertEqual(_parse_data_entry_month_value(values, 2), 200.0)

    def test_month_and_annual_share_entry_priority_helper(self) -> None:
        meta = {"calc_role": "entry_overrides_formula", "allow_manual_entry": 1}
        self.assertTrue(_org_product_value_from_entry(meta, 1.0))
        self.assertTrue(_org_product_month_value_from_entry(meta, 1.0))
        self.assertTrue(_org_product_annual_value_from_entry(meta, 1.0))

    def test_annual_formula_skipped_for_entry_role(self) -> None:
        meta = {"calc_role": "entry", "allow_manual_entry": 1}
        self.assertFalse(_org_product_should_use_annual_formula(meta, use_formula=True))

    def test_annual_formula_allowed_for_entry_overrides_and_formula_roles(self) -> None:
        overrides = {"calc_role": "entry_overrides_formula", "allow_manual_entry": 1}
        formula_role = {"calc_role": "formula", "allow_manual_entry": 1}
        self.assertTrue(_org_product_should_use_annual_formula(overrides, use_formula=True))
        self.assertTrue(_org_product_should_use_annual_formula(formula_role, use_formula=True))
        self.assertFalse(_org_product_should_use_annual_formula(overrides, use_formula=False))


if __name__ == "__main__":
    unittest.main()
