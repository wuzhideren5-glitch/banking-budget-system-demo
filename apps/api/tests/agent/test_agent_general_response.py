from __future__ import annotations

import unittest

from app.services.agent_general_response import (
    build_general_fallback_answer,
    shorten_general_reply,
)


class AgentGeneralResponseTests(unittest.TestCase):
    def test_empty_query_fallback_prompts_for_budget_goal(self) -> None:
        reply = build_general_fallback_answer("")

        self.assertIn("核心结论", reply)
        self.assertIn("控成本", reply)

    def test_budget_fallback_contains_budget_management_points(self) -> None:
        reply = build_general_fallback_answer("银行预算编制要关注哪些问题")

        self.assertIn("业务与战略一致性", reply)
        self.assertIn("执行监控机制", reply)

    def test_weather_fallback_uses_non_database_guidance(self) -> None:
        reply = build_general_fallback_answer("今天会下雨吗")

        self.assertIn("手机天气应用", reply)
        self.assertIn("无法联网", reply)

    def test_bank_count_fallback_requires_statistical_scope(self) -> None:
        reply = build_general_fallback_answer("中国有多少家银行")

        self.assertIn("统计口径", reply)
        self.assertIn("法人机构", reply)

    def test_shorten_general_reply_keeps_complete_sentence_when_possible(self) -> None:
        reply = shorten_general_reply(
            "第一句很重要。第二句也很重要。第三句需要截断。",
            target_ratio=0.45,
            min_chars=8,
            max_chars=16,
        )

        self.assertEqual(reply, "第一句很重要。")

    def test_shorten_general_reply_adds_terminal_punctuation_for_fragment(self) -> None:
        reply = shorten_general_reply(
            "这是一段没有标点但很长很长的文字用于截断",
            target_ratio=0.2,
            min_chars=6,
            max_chars=8,
        )

        self.assertTrue(reply.endswith("。"))
        self.assertLessEqual(len(reply), 9)


if __name__ == "__main__":
    unittest.main()
