from __future__ import annotations

import unittest

from app.services.agent_social_signal import (
    detect_lightweight_social_signal,
    is_lightweight_social_question,
    sanitize_lightweight_reply,
)


class AgentSocialSignalTests(unittest.TestCase):
    def test_short_social_probe_is_lightweight(self) -> None:
        signal = detect_lightweight_social_signal("在吗？")

        self.assertTrue(signal["is_lightweight_social"])
        self.assertGreaterEqual(float(signal["score"]), 0.85)
        self.assertIn("exact_greeting_pattern", signal["signals"])

    def test_budget_like_query_is_not_social_even_with_greeting(self) -> None:
        signal = detect_lightweight_social_signal(
            "在吗，帮我查一下预算执行",
            budget_query_detector=lambda text: "预算" in text,
        )

        self.assertFalse(signal["is_lightweight_social"])
        self.assertIn("budget_like_query", signal["signals"])

    def test_social_question_helper_uses_same_budget_guard(self) -> None:
        self.assertTrue(is_lightweight_social_question("你开心吗"))
        self.assertFalse(
            is_lightweight_social_question(
                "你开心吗，预算数据出来了吗",
                budget_query_detector=lambda text: "预算" in text,
            )
        )

    def test_sanitize_lightweight_reply_rejects_templated_output(self) -> None:
        fallback = "我在，直接说你想查什么预算口径就行。"

        self.assertEqual(
            sanitize_lightweight_reply("关键要点：我可以帮你。", fallback),
            fallback,
        )
        self.assertEqual(
            sanitize_lightweight_reply("我在呢，随时可以开始。", fallback),
            "我在呢，随时可以开始。",
        )


if __name__ == "__main__":
    unittest.main()
