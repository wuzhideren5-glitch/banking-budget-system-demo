from __future__ import annotations

import unittest

from app.services.agent_memory_payload import (
    build_agent_final_requirement,
    build_agent_memory_append_payload,
    build_agent_pivot_memory_config,
)


class AgentMemoryPayloadTests(unittest.TestCase):
    def test_final_requirement_copies_requirement_fields(self) -> None:
        requirement = build_agent_final_requirement(
            {
                "slot_status": {"time_period": True},
                "missing_slots": ["business_scope"],
                "clarified_slots": {"time_period": "Y2026"},
                "assumptions": ["默认按当前预算年度 Y2026 分析"],
            }
        )

        self.assertEqual(requirement["slot_status"], {"time_period": True})
        self.assertEqual(requirement["missing_slots"], ["business_scope"])
        self.assertEqual(requirement["clarified_slots"], {"time_period": "Y2026"})
        self.assertEqual(requirement["assumptions"], ["默认按当前预算年度 Y2026 分析"])

    def test_pivot_memory_config_uses_department_row_for_department_query(self) -> None:
        config = build_agent_pivot_memory_config(
            {"user_query": "按部门看预算", "clarified_slots": {"time_period": "Y2026 M05"}},
            budget_year=2027,
        )

        self.assertEqual(config["rows"], ["dept_level1"])
        self.assertEqual(config["filters"]["year"], "Y2026 M05")

    def test_pivot_memory_config_defaults_to_metric_row_and_configured_budget_year(self) -> None:
        config = build_agent_pivot_memory_config(
            {"user_query": "看贷款收入", "clarified_slots": {}},
            budget_year=2027,
        )

        self.assertEqual(config["rows"], ["data_code_name"])
        self.assertEqual(config["filters"]["year"], "Y2027")

    def test_memory_append_payload_matches_store_append_contract(self) -> None:
        payload = build_agent_memory_append_payload(
            {
                "user_query": "按部门看预算",
                "intent_type": "budget_analysis",
                "next_action": "execute_query",
                "suggested_sql": "SELECT 1",
                "reply": "已查询",
                "executed_result": {"row_count": 1},
                "clarification_rounds": "2",
                "slot_status": {"time_period": True},
                "missing_slots": [],
                "clarified_slots": {"time_period": "Y2026"},
                "assumptions": [],
            },
            budget_year=2027,
        )

        self.assertEqual(payload["user_query"], "按部门看预算")
        self.assertEqual(payload["intent_type"], "budget_analysis")
        self.assertEqual(payload["next_action"], "execute_query")
        self.assertEqual(payload["suggested_sql"], "SELECT 1")
        self.assertEqual(payload["analysis_summary"], "已查询")
        self.assertEqual(payload["executed_result"], {"row_count": 1})
        self.assertEqual(payload["clarification_rounds"], 2)
        self.assertEqual(payload["final_requirement"]["slot_status"], {"time_period": True})
        self.assertEqual(payload["pivot_config"]["filters"]["year"], "Y2026")


if __name__ == "__main__":
    unittest.main()
