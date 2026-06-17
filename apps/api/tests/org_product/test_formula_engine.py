from __future__ import annotations

import unittest

from app.services.formula_engine import (
    try_calculate_formula_value,
    validate_formula_reference_scope,
)


class FormulaEngineTests(unittest.TestCase):
    def test_calculates_formula_refs_functions_and_full_width_operators(self) -> None:
        value, error = try_calculate_formula_value(
            "（<A01.01.01.001 日均余额>＋SUM(2, 3)）×2",
            {"A01.01.01.001": 10},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 30.0)

    def test_returns_error_for_division_by_zero(self) -> None:
        value, error = try_calculate_formula_value("1 / 0", {})

        self.assertEqual(value, 0.0)
        self.assertEqual(error, "#DIV/0!")

    def test_calculates_bare_official_data_account_refs(self) -> None:
        value, error = try_calculate_formula_value(
            "A.01.01.001 + B.01.01.001",
            {"A.01.01.001": 10, "B.01.01.001": 5},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 15.0)

    def test_calculates_five_level_and_parent_data_account_refs(self) -> None:
        value, error = try_calculate_formula_value(
            "A01.01.01.001 / A01.01.01",
            {"A01.01.01.001": 20, "A01.01.01": 100},
        )

        self.assertIsNone(error)
        self.assertEqual(value, 0.2)

    def test_corp_formula_allows_child_product_refs(self) -> None:
        validate_formula_reference_scope(
            formula="A.01.01.001 + B.01.01.001",
            target_is_all=True,
            scope_by_code={"A.01.01.001": False, "B.01.01.001": False},
            formula_label="预算公式",
        )


if __name__ == "__main__":
    unittest.main()
