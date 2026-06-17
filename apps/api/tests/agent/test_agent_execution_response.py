from __future__ import annotations

import unittest

from app.services.agent_execution_response import (
    build_execution_fallback_reply,
    build_execution_rewrite_payload,
    normalize_agent_analysis_reply_units,
    recent_assistant_context_for_execution,
    should_allow_repeat_analysis,
)


class AgentExecutionResponseTests(unittest.TestCase):
    def test_repeat_analysis_detection(self) -> None:
        self.assertTrue(should_allow_repeat_analysis("请再次分析一遍"))
        self.assertTrue(should_allow_repeat_analysis("完整分析"))
        self.assertFalse(should_allow_repeat_analysis("看一下本月预算"))

    def test_recent_assistant_context_only_when_repeat_allowed(self) -> None:
        history = [
            {"role": "assistant", "content": "旧回复1"},
            {"role": "user", "content": "追问"},
            {"role": "assistant", "content": "旧回复2"},
            {"role": "assistant", "content": "旧回复3"},
            {"role": "assistant", "content": "旧回复4"},
        ]

        self.assertEqual(recent_assistant_context_for_execution(history, allow_repeat=False), [])
        self.assertEqual(
            recent_assistant_context_for_execution(history, allow_repeat=True),
            ["旧回复2", "旧回复3", "旧回复4"],
        )

    def test_fallback_reply_summarizes_row_count_quality_and_preview(self) -> None:
        reply = build_execution_fallback_reply(
            {
                "row_count": 12,
                "data_quality_note": "当前版本",
                "display_preview_rows": [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}],
            }
        )

        self.assertIn("返回 12 行结果", reply)
        self.assertIn("数据说明：当前版本", reply)
        self.assertIn("样例前3行", reply)
        self.assertNotIn("{'a': 4}", reply)

    def test_rewrite_payload_limits_preview_and_context(self) -> None:
        payload = build_execution_rewrite_payload(
            query="请再次分析",
            history=[{"role": "assistant", "content": "上一轮摘要"}],
            result={
                "row_count": 9,
                "display_columns": ["部门", "金额"],
                "display_preview_rows": [{"i": i} for i in range(10)],
                "data_quality_note": "ok",
            },
        )

        self.assertEqual(payload["row_count"], 9)
        self.assertEqual(payload["显示字段"], ["部门", "金额"])
        self.assertEqual(len(payload["样例数据"]), 8)
        self.assertEqual(payload["recent_assistant_context"], ["上一轮摘要"])
        self.assertTrue(payload["allow_repeat_analysis"])

    def test_normalize_units_keeps_budget_tool_unit_contract(self) -> None:
        self.assertEqual(normalize_agent_analysis_reply_units("金额为 12 万元"), "金额为 12 亿元")


if __name__ == "__main__":
    unittest.main()
