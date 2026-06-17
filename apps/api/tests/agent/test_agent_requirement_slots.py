from __future__ import annotations

from datetime import date
import unittest

from app.services.agent_requirement_slots import (
    contextual_agent_slots_from_history,
    extract_agent_slot_status,
    extract_structured_agent_slots,
    slot_status_from_structured_agent_slots,
)


class AgentRequirementSlotsTests(unittest.TestCase):
    def test_extract_slot_status_detects_query_requirements(self) -> None:
        status = extract_agent_slot_status("看 2026 年个人金融部收入同比明细")

        self.assertEqual(
            status,
            {
                "time_period": True,
                "business_scope": True,
                "comparison_type": True,
                "granularity": True,
            },
        )

    def test_structured_slots_extract_current_budget_terms(self) -> None:
        slots = extract_structured_agent_slots("看 2026 年个人金融部预算实际差异，按月汇总，L2")

        self.assertEqual(slots["time_period"], "Y2026")
        self.assertEqual(slots["business_scope"], "个人金融部")
        self.assertEqual(slots["comparison_type"], "budget_vs_actual")
        self.assertEqual(slots["comparison_show_level"], 2)
        self.assertEqual(slots["granularity"], "month")

    def test_recent_month_slot_is_testable_with_fixed_today(self) -> None:
        slots = extract_structured_agent_slots("看最近一个月部门收入", today=date(2026, 6, 2))

        self.assertEqual(slots["time_period"], "Y2026 M05")
        self.assertEqual(slots["business_scope"], "部门维度")

    def test_explicit_year_comparison_sets_yoy(self) -> None:
        slots = extract_structured_agent_slots("2026年和2025年对比，按年")

        self.assertEqual(slots["comparison_type"], "yoy")
        self.assertEqual(slots["granularity"], "year")

    def test_slot_status_from_structured_slots_keeps_comparison_optional(self) -> None:
        self.assertEqual(
            slot_status_from_structured_agent_slots({"time_period": "Y2026", "business_scope": "部门维度"}),
            {
                "time_period": True,
                "business_scope": True,
                "comparison_type": True,
                "granularity": False,
            },
        )

    def test_contextual_slots_use_latest_user_mention(self) -> None:
        history = [
            {"role": "user", "content": "看 2025 年个人金融部收入，按年"},
            {"role": "assistant", "content": "好的"},
            {"role": "user", "content": "改看企业金融部，按月"},
        ]

        slots = contextual_agent_slots_from_history(history)

        self.assertEqual(slots["time_period"], "Y2025")
        self.assertEqual(slots["business_scope"], "企业金融部")
        self.assertEqual(slots["granularity"], "month")


if __name__ == "__main__":
    unittest.main()
