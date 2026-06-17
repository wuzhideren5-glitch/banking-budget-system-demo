from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.runtime_metric_identity import (
    official_runtime_metric_ref_code,
    product_code_from_runtime_metric_ref,
    product_code_from_metric_tree_node,
)


class RuntimeMetricIdentityTests(unittest.TestCase):
    def test_product_code_is_derived_from_product_prefixed_metric_key(self) -> None:
        self.assertEqual(product_code_from_runtime_metric_ref("a01.01.01.001"), "A01")
        self.assertEqual(product_code_from_metric_tree_node("A01"), "A01")
        self.assertEqual(product_code_from_metric_tree_node("A01.01.01.001"), "A01")

    def test_official_runtime_metric_ref_code_rejects_legacy_suffix_identity(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            official_runtime_metric_ref_code("01.01.001.A01", "A01")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("产品前缀指标主键", str(raised.exception.detail))

    def test_official_runtime_metric_ref_code_rejects_scope_mismatch(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            official_runtime_metric_ref_code("A01.01.01.001", "A02")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("产品编码与产品前缀指标主键不一致", str(raised.exception.detail))


if __name__ == "__main__":
    unittest.main()
