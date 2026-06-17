from __future__ import annotations

from datetime import date
import re
import unittest

from app.services.agent_time_context import (
    last_completed_calendar_month,
    parse_requested_year,
    resolve_agent_analysis_time_anchor,
)


class AgentTimeContextTests(unittest.TestCase):
    @staticmethod
    def extract_month_index(text: str) -> int | None:
        match = re.search(r"(\d{1,2})月", text or "")
        if not match:
            return None
        return int(match.group(1))

    def resolve(self, query: str, state: dict | None = None) -> dict:
        return resolve_agent_analysis_time_anchor(
            state or {},
            effective_query=query,
            budget_year=2026,
            extract_month_index=self.extract_month_index,
            today=date(2026, 6, 2),
        )

    def test_parse_requested_year(self) -> None:
        self.assertEqual(parse_requested_year("看 2025 年预算"), 2025)
        self.assertIsNone(parse_requested_year("看今年预算"))

    def test_last_completed_calendar_month_handles_january(self) -> None:
        self.assertEqual(
            last_completed_calendar_month(date(2026, 1, 8)),
            {"calendar_year": 2025, "year_tag": "Y2025", "month_tag": "M12"},
        )

    def test_pm_structured_year_month_wins_over_query_text(self) -> None:
        anchor = self.resolve(
            "看 1 月预算",
            {"pm_query_spec": {"year": "Y2025", "month": "M09"}},
        )

        self.assertEqual(anchor, {"calendar_year": 2025, "year_tag": "Y2025", "month_tag": "M09"})

    def test_recent_month_uses_last_completed_calendar_month(self) -> None:
        self.assertEqual(
            self.resolve("看最近一个月预算"),
            {"calendar_year": 2026, "year_tag": "Y2026", "month_tag": "M05"},
        )

    def test_month_span_keeps_month_unanchored(self) -> None:
        self.assertEqual(
            self.resolve("看 2025 年 1-2月预算"),
            {"calendar_year": 2025, "year_tag": "Y2025", "month_tag": None},
        )

    def test_explicit_month_and_year_anchor_to_single_month(self) -> None:
        self.assertEqual(
            self.resolve("看 2025 年 3月预算"),
            {"calendar_year": 2025, "year_tag": "Y2025", "month_tag": "M03"},
        )

    def test_month_without_year_uses_budget_year(self) -> None:
        self.assertEqual(
            self.resolve("看 4月预算"),
            {"calendar_year": 2026, "year_tag": "Y2026", "month_tag": "M04"},
        )

    def test_clarified_year_fallback(self) -> None:
        self.assertEqual(
            self.resolve("看预算", {"clarified_slots": {"time_period": "Y2024"}}),
            {"calendar_year": 2024, "year_tag": "Y2024", "month_tag": None},
        )


if __name__ == "__main__":
    unittest.main()
