from __future__ import annotations

import unittest

from app.routers.org_product_helpers import _should_use_vertical_rollup_annual


class OrgProductAnnualPrecedenceTests(unittest.TestCase):
    def test_calc_rule_blocks_vertical_rollup_annual(self) -> None:
        self.assertFalse(
            _should_use_vertical_rollup_annual(
                {
                    "vertical_rollup": 1,
                    "annual_agg_rule": "CALC",
                    "formula_budget_annual": "AA.01.001/AA.01.002",
                    "nature": "比例",
                    "formula": "",
                }
            )
        )

    def test_sum_rule_blocks_vertical_rollup_annual(self) -> None:
        self.assertFalse(
            _should_use_vertical_rollup_annual(
                {
                    "vertical_rollup": 1,
                    "annual_agg_rule": "SUM",
                    "formula_budget_annual": "",
                    "nature": "收入",
                    "formula": "",
                }
            )
        )

    def test_annual_formula_blocks_vertical_rollup_annual(self) -> None:
        self.assertFalse(
            _should_use_vertical_rollup_annual(
                {
                    "vertical_rollup": 1,
                    "annual_agg_rule": "",
                    "formula_budget_annual": "AA.90.01+AA.90.03",
                    "nature": "支出",
                    "formula": "",
                }
            )
        )

    def test_vertical_rollup_allowed_without_rule_or_formula(self) -> None:
        self.assertTrue(
            _should_use_vertical_rollup_annual(
                {
                    "vertical_rollup": 1,
                    "annual_agg_rule": "",
                    "formula_budget_annual": "",
                    "nature": "支出",
                    "formula": "",
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
