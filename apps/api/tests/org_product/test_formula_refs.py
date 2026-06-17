from __future__ import annotations

import unittest

from app.formula_refs import extract_formula_codes, extract_runtime_metric_ref_code


class FormulaRefsTests(unittest.TestCase):
    def test_extracts_only_product_prefixed_data_account_codes(self) -> None:
        formula = "A01.01.01.001 + 01.01.001.A01 + <A02.02.01.002:贷款收益率>"

        self.assertEqual(
            extract_formula_codes(formula),
            {"A01.01.01.001", "A02.02.01.002"},
        )

    def test_extract_runtime_metric_ref_code_prefers_whole_product_prefixed_key(self) -> None:
        self.assertEqual(
            extract_runtime_metric_ref_code("指标 A01.01.01.001 本月值"),
            "A01.01.01.001",
        )


if __name__ == "__main__":
    unittest.main()
