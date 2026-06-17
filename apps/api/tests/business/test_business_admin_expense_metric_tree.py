from __future__ import annotations

import unittest

from app.services.business_admin_expense_metric_tree import (
    BUSINESS_ADMIN_EXPENSE_ROOTS,
    build_business_admin_expense_nodes,
    business_admin_expense_leaf_codes,
    business_admin_expense_metric_codes,
)


class BusinessAdminExpenseMetricTreeTests(unittest.TestCase):
    def test_all_roots_have_twenty_two_leaves(self) -> None:
        for root in BUSINESS_ADMIN_EXPENSE_ROOTS:
            nodes = build_business_admin_expense_nodes(root)
            leaves = [node for node in nodes if node.node_type == "METRIC"]
            self.assertEqual(len(leaves), 22, root)
            self.assertEqual(nodes[0].node_name, "直接费用")
            indirect_root = next(node for node in nodes if node.node_code == f"{root}.02")
            self.assertEqual(indirect_root.node_name, "间接费用")
            self.assertEqual(indirect_root.node_type, "GROUP")
            self.assertEqual(
                next(node for node in nodes if node.node_code == f"{root}.02.03.01.001").node_name,
                "IT常规人力",
            )

    def test_leaf_codes_are_unique_across_products(self) -> None:
        all_codes = business_admin_expense_leaf_codes()
        per_root = {
            root: {node.node_code for node in build_business_admin_expense_nodes(root) if node.node_type == "METRIC"}
            for root in BUSINESS_ADMIN_EXPENSE_ROOTS
        }
        self.assertEqual(len(all_codes), 22 * len(BUSINESS_ADMIN_EXPENSE_ROOTS))
        self.assertNotIn("CORP.05.01", per_root)
        self.assertEqual(len(per_root["AA.05.01"]), 22)
        self.assertIn("AA.05.01.01.03.01.001", per_root["AA.05.01"])
        self.assertIn("AA.05.01.02.03.01.001", per_root["AA.05.01"])

    def test_business_admin_tree_definitions_are_current_source_only(self) -> None:
        new_metric_codes = business_admin_expense_metric_codes()
        self.assertIn("AA.05.01.02", new_metric_codes)
        self.assertIn("AA.05.01.02.01", new_metric_codes)
        self.assertIn("AA.05.01.02.03.01.001", new_metric_codes)
        self.assertNotIn("AA.05.01.02.01.003", new_metric_codes)
        self.assertIn("AA.05.01.01.03.02.001", new_metric_codes)


if __name__ == "__main__":
    unittest.main()
