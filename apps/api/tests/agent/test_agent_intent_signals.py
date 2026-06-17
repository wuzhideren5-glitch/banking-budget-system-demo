from __future__ import annotations

import unittest

from app.services.agent_intent_signals import (
    has_pending_budget_plan,
    is_brief_acknowledgement,
    is_budget_analysis_intent,
    is_budget_knowledge_question,
    is_budget_metadata_query,
    is_contextual_budget_followup,
    is_followup_constraint_like,
    is_general_chitchat,
    is_greeting_then_budget_query,
    is_layout_adjust_request,
    is_pivot_view_request,
    is_simple_greeting_query,
    looks_like_budget_query,
)


class AgentIntentSignalsTests(unittest.TestCase):
    def test_budget_and_general_signals_do_not_confuse_plain_greeting(self) -> None:
        self.assertTrue(is_simple_greeting_query("你好呀"))
        self.assertTrue(is_general_chitchat("今天天气怎么样"))
        self.assertFalse(is_simple_greeting_query("你好，帮我看预算执行差异"))
        self.assertTrue(looks_like_budget_query("帮我看预算执行差异"))

    def test_greeting_then_budget_query_is_budget_domain(self) -> None:
        self.assertTrue(is_greeting_then_budget_query("早上好，帮我看企业金融近三个月净利息收入"))
        self.assertFalse(is_greeting_then_budget_query("早上好，今天怎么样"))

    def test_budget_query_kinds_and_followups(self) -> None:
        self.assertTrue(is_budget_analysis_intent("按部门分析预算与实际差异"))
        self.assertTrue(is_budget_metadata_query("系统里有多少个部门的数据"))
        self.assertTrue(is_contextual_budget_followup("把刚才这些部门列出来"))
        self.assertTrue(is_followup_constraint_like("按刚才口径看一季度同比"))
        self.assertTrue(is_layout_adjust_request("预算和实际分两列展示"))
        self.assertTrue(is_pivot_view_request("打开数据透视表"))
        self.assertTrue(is_budget_knowledge_question("预算编制有哪些注意事项"))

    def test_brief_acknowledgement_and_pending_plan(self) -> None:
        self.assertTrue(is_brief_acknowledgement("确认"))
        self.assertTrue(
            has_pending_budget_plan(
                [
                    {"role": "assistant", "content": "分析口径规划如下，请回复确认执行。"},
                    {"role": "user", "content": "确认"},
                ]
            )
        )
        self.assertFalse(
            has_pending_budget_plan(
                [
                    {"role": "assistant", "content": "已执行只读查询，返回 3 行结果。"},
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()
