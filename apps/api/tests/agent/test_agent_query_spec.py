from __future__ import annotations

import unittest

from app.agent.agent_query_spec import merge_current_query_specs, normalise_current_query_spec


class AgentQuerySpecTests(unittest.TestCase):
    def test_normalise_current_query_spec_keeps_only_current_contract_fields(self) -> None:
        spec = normalise_current_query_spec(
            {
                "period_description": "2026年一季度",
                "year": "Y2026",
                "metric_nodes": [{"code": "A01.01", "name": "贷款"}],
                "data_accounts": "D001",
                "departments": [{"code": "D01", "name": "总行"}],
                "products": [],
                "unknown_axis": [{"code": "X"}],
            }
        )

        self.assertEqual(spec["period_description"], "2026年一季度")
        self.assertEqual(spec["year"], "Y2026")
        self.assertEqual(spec["metric_nodes"], [{"code": "A01.01", "name": "贷款"}])
        self.assertEqual(spec["data_accounts"], [])
        self.assertEqual(spec["departments"], [{"code": "D01", "name": "总行"}])
        self.assertNotIn("unknown_axis", spec)

    def test_merge_current_query_specs_drops_non_contract_fields_after_merge(self) -> None:
        merged = merge_current_query_specs(
            {
                "metric_nodes": [{"code": "A01.01", "name": "贷款"}],
                "unused_axis": [{"code": "X001"}],
                "__require_compare_level__": True,
            },
            {
                "products": [{"code": "A01", "name": "泛微粒贷"}],
                "query_focus": "profit_loss",
                "draft_axis": [{"code": "DRAFT"}],
            },
        )

        self.assertEqual(merged["metric_nodes"], [{"code": "A01.01", "name": "贷款"}])
        self.assertEqual(merged["products"], [{"code": "A01", "name": "泛微粒贷"}])
        self.assertEqual(merged["query_focus"], "profit_loss")
        self.assertTrue(merged["__require_compare_level__"])
        self.assertNotIn("unused_axis", merged)
        self.assertNotIn("draft_axis", merged)


if __name__ == "__main__":
    unittest.main()
