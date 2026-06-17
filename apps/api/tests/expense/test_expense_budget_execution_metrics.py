from __future__ import annotations

import unittest

from app.services.expense_budget_execution_metrics import (
    filter_tree_by_keyword,
    filter_zero_metric_tree,
    metric_payload,
    month_over_month_metrics,
)


class ExpenseBudgetExecutionMetricsTests(unittest.TestCase):
    def test_metric_payload_uses_shared_yoy_and_month_over_month_rules(self) -> None:
        self.assertEqual(month_over_month_metrics([10.0, 25.0] + [0.0] * 10, 2), (15.0, 1.5))

        payload = metric_payload([10.0, 25.0] + [0.0] * 10, 100.0, 20.0, 2)

        self.assertEqual(payload["current_actual"], 35.0)
        self.assertEqual(payload["annual_budget"], 100.0)
        self.assertEqual(payload["budget_progress"], 0.35)
        self.assertEqual(payload["last_year_actual"], 20.0)
        self.assertEqual(payload["yoy_change"], 15.0)
        self.assertEqual(payload["yoy_rate"], 0.75)
        self.assertEqual(payload["month_over_month"], 15.0)
        self.assertEqual(payload["month_over_month_rate"], 1.5)

    def test_filter_tree_by_keyword_keeps_matching_ancestors(self) -> None:
        tree = [
            {
                "subject_name": "业务及管理费",
                "level_label": "一级",
                "children": [
                    {"subject_name": "IT费用", "level_label": "二级", "children": []},
                    {"subject_name": "业务费用", "level_label": "二级", "children": []},
                ],
            }
        ]

        filtered = filter_tree_by_keyword(tree, "IT")

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["subject_name"], "业务及管理费")
        self.assertEqual([child["subject_name"] for child in filtered[0]["children"]], ["IT费用"])

    def test_filter_zero_metric_tree_keeps_nonzero_descendants(self) -> None:
        tree = [
            {
                "subject_name": "root",
                "current_actual": 0.0,
                "annual_budget": 0.0,
                "last_year_actual": 0.0,
                "yoy_change": 0.0,
                "children": [
                    {
                        "subject_name": "empty",
                        "current_actual": 0.0,
                        "annual_budget": 0.0,
                        "last_year_actual": 0.0,
                        "yoy_change": 0.0,
                        "children": [],
                    },
                    {
                        "subject_name": "actual",
                        "current_actual": 1.0,
                        "annual_budget": 0.0,
                        "last_year_actual": 0.0,
                        "yoy_change": 1.0,
                        "children": [],
                    },
                ],
            }
        ]

        filtered = filter_zero_metric_tree(tree, include_zero_rows=False)

        self.assertEqual(len(filtered), 1)
        self.assertEqual([child["subject_name"] for child in filtered[0]["children"]], ["actual"])


if __name__ == "__main__":
    unittest.main()
