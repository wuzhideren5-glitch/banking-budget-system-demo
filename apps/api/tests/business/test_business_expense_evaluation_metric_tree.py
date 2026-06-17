from __future__ import annotations

import unittest

from app.services.business_expense_evaluation_metric_tree import (
    BUSINESS_EXPENSE_EVALUATION_ROOTS,
    build_business_expense_evaluation_nodes,
    business_expense_evaluation_leaf_codes,
    business_expense_evaluation_metric_codes,
)


class BusinessExpenseEvaluationMetricTreeTests(unittest.TestCase):
    def test_all_roots_have_expected_structure(self) -> None:
        for root in BUSINESS_EXPENSE_EVALUATION_ROOTS:
            nodes = build_business_expense_evaluation_nodes(root)
            self.assertEqual(nodes[0].node_code, root)
            self.assertEqual(nodes[0].node_name, "业务支出评估")
            self.assertTrue(nodes[0].parent_code.endswith(".05"))
            customer_root = next(node for node in nodes if node.node_code == f"{root}.09")
            self.assertEqual(customer_root.node_name, "客户经营指标")
            self.assertEqual(customer_root.parent_code, root)
            self.assertFalse(any(node.node_code.startswith(f"{root}.10") for node in nodes))

    def test_leaf_codes_are_unique_across_products(self) -> None:
        all_codes = business_expense_evaluation_leaf_codes()
        per_root = {
            root: {
                node.node_code
                for node in build_business_expense_evaluation_nodes(root)
                if node.node_type == "METRIC"
            }
            for root in BUSINESS_EXPENSE_EVALUATION_ROOTS
        }
        self.assertEqual(len(all_codes), 18 * len(BUSINESS_EXPENSE_EVALUATION_ROOTS))
        self.assertNotIn("CORP.05.02", per_root)
        self.assertIn("AA.05.02.09.01.001", per_root["AA.05.02"])
        self.assertIn("A.05.02.09.01.001", per_root["A.05.02"])
        self.assertIn("A.05.02.09.01.004", per_root["A.05.02"])
        self.assertNotIn("A.05.02.09.01.005", per_root["A.05.02"])

    def test_business_expense_evaluation_tree_definitions_are_current_source_only(self) -> None:
        new_metric_codes = business_expense_evaluation_metric_codes()
        self.assertIn("A.05.02", new_metric_codes)
        self.assertIn("A.05.02.09", new_metric_codes)
        self.assertNotIn("A.05.02.10", new_metric_codes)
        self.assertIn("A.05.02.09.01.001", new_metric_codes)


if __name__ == "__main__":
    unittest.main()
