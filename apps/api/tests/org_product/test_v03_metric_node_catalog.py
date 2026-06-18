from __future__ import annotations

import unittest

from app.services.v03_metric_node_catalog import (
    choose_canonical_table_name,
    infer_implicit_groups_for_codes,
    is_v03_mirror_duplicate_row,
    is_v03_stale_node_code,
)


class V03MetricNodeCatalogTests(unittest.TestCase):
    def test_stale_second_segment_rules(self) -> None:
        self.assertTrue(is_v03_stale_node_code("AA.05.02"))
        self.assertTrue(is_v03_stale_node_code("A01.90.01"))
        self.assertFalse(is_v03_stale_node_code("AA.49.05"))
        self.assertFalse(is_v03_stale_node_code("A01.14.01.01.05"))

    def test_mirror_duplicate_rows(self) -> None:
        self.assertTrue(is_v03_mirror_duplicate_row("AA利息净收入表", "AA.25.05"))
        self.assertFalse(is_v03_mirror_duplicate_row("AA资产负债表（日均）", "AA.25.05"))

    def test_canonical_table_priority(self) -> None:
        self.assertEqual(
            choose_canonical_table_name("利息净收入表", "资产负债表（日均）"),
            "资产负债表（日均）",
        )

    def test_infer_implicit_groups(self) -> None:
        specs = infer_implicit_groups_for_codes({"AA.24.05", "AA.14.02.05"})
        codes = {spec.node_code for spec in specs}
        self.assertIn("AA.24", codes)
        self.assertIn("AA.14.02", codes)


if __name__ == "__main__":
    unittest.main()
