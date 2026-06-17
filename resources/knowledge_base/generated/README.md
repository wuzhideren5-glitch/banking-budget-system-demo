# Generated Runtime Artifacts

本目录保存 Agent 运行配置和当前运行库统计快照。历史构建脚本 `apps/api/scripts/build_knowledge_base.py` 已不存在；不要再按该脚本说明重建知识库。

- `agent_runtime_config.json`：Agent 当前运行配置。
- `kb_build_report.json`：当前运行库表记录量快照。

Agent 运行时调试日志不再放在知识资源目录。当前写入位置是 `var/logs/agent/agent_llm_events.jsonl` 和 `var/logs/agent/intent_router_trace.jsonl`；旧日志快照归档在 `archive/runtime_snapshots/logs/`。

正式查询口径以 `06_agent_prompts/`、`01_data_semantics/`、`data_account_metric_node`、`data_account_metric_binding` 和 `data_account` 为准。
