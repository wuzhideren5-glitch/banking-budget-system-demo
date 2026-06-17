from __future__ import annotations

import unittest

from app.services.agent_conversation_text import (
    effective_agent_query,
    is_execute_only_command,
    last_budget_query_from_history,
    resolve_numeric_option_reply,
    strip_reply_markdown_stars,
)


class AgentConversationTextTests(unittest.TestCase):
    @staticmethod
    def budget_detector(text: str) -> bool:
        return "预算" in text or "收入" in text

    def test_strip_reply_markdown_stars_removes_emphasis_and_keeps_list_markers(self) -> None:
        self.assertEqual(
            strip_reply_markdown_stars("**标题**\n* 重点\n这里是*强调*"),
            "标题\n- 重点\n这里是强调",
        )

    def test_execute_only_commands_cover_default_and_query_phrases(self) -> None:
        self.assertTrue(is_execute_only_command("确认"))
        self.assertTrue(is_execute_only_command("按默认假设执行"))
        self.assertTrue(is_execute_only_command("开始查询"))
        self.assertFalse(is_execute_only_command("查询本月预算差异"))

    def test_numeric_option_reply_preserves_metric_tree_hint(self) -> None:
        history = [
            {
                "role": "assistant",
                "content": "1. 净利息收入汇总（指标节点 01.001）\n2. 净利息细项（机构及产品指标编码 A1001/A1002）",
            }
        ]

        self.assertEqual(
            resolve_numeric_option_reply("1", history),
            "我选择第1项：净利息收入汇总（指标节点 01.001）；按指标节点 01.001 汇总口径",
        )
        self.assertEqual(
            resolve_numeric_option_reply("2", history),
            "我选择第2项：净利息细项（机构及产品指标编码 A1001/A1002）；按机构及产品指标编码 A1001/A1002 细项口径",
        )

    def test_last_budget_query_skips_numeric_and_level_replies(self) -> None:
        history = [
            {"role": "user", "content": "看一下 2026 年预算收入差异"},
            {"role": "assistant", "content": "请选择版本"},
            {"role": "user", "content": "2"},
            {"role": "user", "content": "L3"},
        ]

        self.assertEqual(
            last_budget_query_from_history(history, budget_query_detector=self.budget_detector),
            "看一下 2026 年预算收入差异",
        )

    def test_effective_agent_query_uses_base_query_for_choice_replies(self) -> None:
        state = {
            "user_query": "1",
            "history": [],
            "pm_query_spec": {"__base_user_query__": "看一下本月预算执行情况"},
        }

        self.assertEqual(
            effective_agent_query(state, budget_query_detector=self.budget_detector),
            "看一下本月预算执行情况",
        )

    def test_effective_agent_query_uses_previous_budget_query_for_execute_only_turn(self) -> None:
        state = {
            "user_query": "确认执行",
            "history": [
                {"role": "user", "content": "帮我分析 2026 年预算收入"},
                {"role": "assistant", "content": "确认后执行"},
            ],
        }

        self.assertEqual(
            effective_agent_query(state, budget_query_detector=self.budget_detector),
            "帮我分析 2026 年预算收入",
        )


if __name__ == "__main__":
    unittest.main()
