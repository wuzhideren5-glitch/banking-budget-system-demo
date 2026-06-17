from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.services.agent_compare_clarification import (
    map_pm_missing_aspects,
    resolve_compare_version_clarification,
)


class AgentCompareClarificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.common_db = root / "common.db"
        self.compare_db = root / "compare.db"
        with sqlite3.connect(self.compare_db) as conn:
            conn.executescript(
                """
                CREATE TABLE compare_budget_summary(
                    show_level INTEGER,
                    source_year INTEGER,
                    source_version_id INTEGER,
                    source_version_name TEXT
                );

                INSERT INTO compare_budget_summary VALUES (1, 2026, 101, 'base');
                INSERT INTO compare_budget_summary VALUES (2, 2025, 202, 'last_year');
                """
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_yoy_without_level_returns_clarification_options_and_pending_spec(self) -> None:
        decision = resolve_compare_version_clarification(
            "2026年和2025年对比净利息收入",
            route="data_query_ready",
            pm={
                "missing_aspects": ["comparison_type", "time", "metric_scope"],
                "query_spec": {"metric_nodes": [{"code": "A03.03", "name": "净利息收入"}]},
            },
            pending_query_spec={},
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(decision["action"], "clarify")
        self.assertIn("请先选择 compare 版本", decision["reply"])
        self.assertEqual(decision["clarification_options"], {"comparison_version": ["L2（2025年 / V202 last_year）"]})
        self.assertEqual(decision["missing_slots"], ["comparison_version", "time_period", "metric_scope"])
        pending = decision["pending_query_spec"]
        self.assertTrue(pending["__require_compare_level__"])
        self.assertEqual(pending["__base_user_query__"], "2026年和2025年对比净利息收入")
        self.assertEqual(pending["metric_nodes"], [{"code": "A03.03", "name": "净利息收入"}])

    def test_selected_level_updates_pending_and_preserves_base_query(self) -> None:
        decision = resolve_compare_version_clarification(
            "L3",
            route="data_query_incomplete",
            pm={"query_spec": {"year": "Y2026", "comparison_type": "yoy"}},
            pending_query_spec={
                "__require_compare_level__": True,
                "__base_user_query__": "原始同比问题",
                "departments": [{"code": "Y103", "name": "汽车金融部"}],
            },
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

        self.assertEqual(decision["action"], "selected")
        query_spec = decision["query_spec"]
        self.assertFalse(query_spec["__require_compare_level__"])
        self.assertEqual(query_spec["__selected_compare_level__"], 3)
        self.assertEqual(query_spec["__base_user_query__"], "原始同比问题")
        self.assertEqual(query_spec["year"], "Y2026")
        self.assertEqual(query_spec["departments"], [{"code": "Y103", "name": "汽车金融部"}])

    def test_non_yoy_or_non_data_route_does_not_interrupt_pm_flow(self) -> None:
        self.assertEqual(
            resolve_compare_version_clarification(
                "看预算实际差异",
                route="data_query_ready",
                pm={"query_spec": {}},
                pending_query_spec={},
                compare_db=self.compare_db,
                common_db=self.common_db,
            ),
            {"action": "none"},
        )
        self.assertEqual(
            resolve_compare_version_clarification(
                "看同比",
                route="off_topic",
                pm={"query_spec": {}},
                pending_query_spec={},
                compare_db=self.compare_db,
                common_db=self.common_db,
            ),
            {"action": "none"},
        )

    def test_missing_aspect_mapping_is_current_slot_contract(self) -> None:
        self.assertEqual(
            map_pm_missing_aspects(["time", "org_product", "metric_scope", "time", "unknown"]),
            ["time_period", "business_scope", "metric_scope"],
        )


if __name__ == "__main__":
    unittest.main()
