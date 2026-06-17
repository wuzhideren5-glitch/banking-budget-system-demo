from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.agent.agent_graph import AgentGraphService


class AgentRuntimeConfigTests(unittest.TestCase):
    def test_missing_runtime_config_ignores_retired_intent_router_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "generated"
            root.mkdir(parents=True)
            (root / "intent_router_config.json").write_text(
                json.dumps(
                    {
                        "semantic_budget_threshold_high": 0.11,
                        "semantic_budget_threshold_mid": 0.10,
                        "trace_enabled": False,
                    }
                ),
                encoding="utf-8",
            )
            service = AgentGraphService.__new__(AgentGraphService)
            service.runtime_config_path = root / "agent_runtime_config.json"

            cfg = AgentGraphService._load_runtime_config(service)

            self.assertEqual(cfg["intent_router"]["semantic_budget_threshold_high"], 0.78)
            self.assertEqual(cfg["intent_router"]["semantic_budget_threshold_mid"], 0.65)
            self.assertTrue(cfg["intent_router"]["trace_enabled"])
            written = json.loads(service.runtime_config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["intent_router"]["semantic_budget_threshold_high"], 0.78)


if __name__ == "__main__":
    unittest.main()
