from __future__ import annotations

from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app.services.agent_requirement_check import build_agent_requirement_check


class AgentRequirementCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.common_db = Path(self.tmp.name) / "common.db"
        self.compare_db = Path(self.tmp.name) / "compare.db"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def create_compare_db(self) -> None:
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

    def check(
        self,
        *,
        query: str,
        state: dict | None = None,
        query_kind: str = "analysis",
        history: list[dict] | None = None,
        inherit_history_slots: bool = False,
        pm_query_spec: dict | None = None,
    ) -> dict:
        return build_agent_requirement_check(
            state or {},
            query=query,
            query_kind=query_kind,
            history=history or [],
            inherit_history_slots=inherit_history_slots,
            pm_query_spec=pm_query_spec or {},
            budget_year=2026,
            compare_db=self.compare_db,
            common_db=self.common_db,
        )

    def test_metadata_query_does_not_need_clarification(self) -> None:
        result = self.check(query="有哪些部门", query_kind="metadata")

        self.assertFalse(result["need_clarification"])
        self.assertEqual(result["missing_slots"], [])
        self.assertTrue(all(result["slot_status"].values()))

    def test_pm_requirement_override_is_returned_as_current_decision(self) -> None:
        override = {
            "slot_status": {"time_period": True},
            "clarified_slots": {"time_period": "Y2026"},
            "missing_slots": ["granularity"],
            "assumptions": ["默认按月汇总粒度展示"],
            "need_clarification": True,
            "clarification_rounds": 2,
        }

        self.assertEqual(
            self.check(query="确认", state={"pm_requirement_override": override}),
            override,
        )

    def test_missing_time_and_granularity_use_budget_year_assumption(self) -> None:
        result = self.check(query="看个人金融部收入")

        self.assertTrue(result["need_clarification"])
        self.assertEqual(result["missing_slots"], ["time_period", "granularity"])
        self.assertIn("默认按当前预算年度 Y2026 分析", result["assumptions"])

    def test_execute_with_missing_optional_slots_uses_defaults_without_clarification(self) -> None:
        result = self.check(
            query="确认执行",
            state={"wants_execute": True},
            history=[{"role": "assistant", "content": "请确认默认假设"}],
        )

        self.assertFalse(result["need_clarification"])
        self.assertIn("time_period", result["missing_slots"])
        self.assertEqual(result["clarification_rounds"], 1)

    def test_yoy_requires_compare_level_and_returns_version_options(self) -> None:
        self.create_compare_db()

        result = self.check(query="看 2026 年个人金融部收入同比，按月")

        self.assertTrue(result["need_clarification"])
        self.assertIn("comparison_version", result["missing_slots"])
        self.assertEqual(
            result["comparison_version_options"],
            ["L1（2026年 / V101 base）", "L2（2025年 / V202 last_year）"],
        )

    def test_history_slots_are_merged_when_requested(self) -> None:
        result = self.check(
            query="改成按月",
            history=[{"role": "user", "content": "看 2026 年企业金融部收入"}],
            inherit_history_slots=True,
        )

        self.assertFalse(result["need_clarification"])
        self.assertEqual(result["clarified_slots"]["business_scope"], "企业金融部")
        self.assertEqual(result["clarified_slots"]["granularity"], "month")


if __name__ == "__main__":
    unittest.main()
