# Agent 知识库接入说明

本文只描述当前仍存在的 Agent 入口和知识库读取方式。旧公开调试接口 `/api/agent/kb/stats`、`/api/agent/kb/context` 已删除；知识库现在是 Agent 运行时内部 Module，不再作为独立外部 API 暴露。

## 1. 当前公开入口

### 聊天入口

`POST /api/agent/chat`

请求体示例：

```json
{
  "message": "请分析个人金融部一季度预算执行差异",
  "history": [
    { "role": "user", "content": "你好" },
    { "role": "assistant", "content": "你好，我是预算智能助手。" }
  ],
  "top_k": 5,
  "last_dialogue_id": 0,
  "pending_query_spec": null
}
```

返回关键字段：

- `reply`：前端展示给用户的回复文本。
- `intent_type`：`budget` / `general` 等当前意图类型。
- `next_action`：`clarify` / `plan_query` / `general_answer` 等下一步动作。
- `need_clarification`：是否还需追问。
- `missing_slots`：缺失要素列表。
- `clarification_options`：按缺失槽位返回候选补充选项。
- `assumptions`：当前问题的默认解释，不代表恢复旧假设参数表。
- `suggested_sql`：建议的只读 SQL。
- `executed`、`result_row_count`、`result_preview`：只读查询执行状态和预览结果。
- `reply_options`：可点击回复选项。
- `pivot_suggestion`：前端透视表建议。
- `pending_query_spec`：当前预算查询契约状态，只允许当前 `metric_nodes`、`data_accounts`、`departments`、`products` 与时间/对比控制字段。

### 反馈入口

`POST /api/agent/feedback`

请求体示例：

```json
{
  "memory_id": "mem_runtime_xxxxxxxx",
  "satisfied": true,
  "comment": "结论可用"
}
```

用途：

- 将用户满意度回写到当前会话记忆。
- 供后续经验筛选、回复质量调整和问题复盘使用。

### 文件解析入口

`POST /api/agent/file/parse`

用途：

- 上传文本、Excel、Word、PDF 或图片，提取可读文本、关键点和建议动作。
- 解析结果只作为当前对话辅助输入，不写入主数据、预算事实或费用私有表。

## 2. 知识库内部读取链路

`KnowledgeBaseService` 直接读取本目录内的 seed/template 文件：

- `01_data_semantics/data_dictionary_seed.csv`
- `02_metric_definitions/metric_catalog_seed.yaml`
- `03_conversation_memory/memory_record_seed.jsonl`
- `04_term_synonyms/synonyms_seed.csv`
- `05_analysis_templates/analysis_template_library.md`
- `generated/agent_runtime_config.json`

Agent 领域词库由 `apps/api/app/services/agent_domain_lexicon.py` 调用 `KnowledgeBaseService.read_current_synonym_rows()` 读取；该读取只保留仍存在于当前数据字典的实体同义词。旧报告科目、旧预算驱动、旧 BI 管控字段、旧透视规则镜像和旧事实标脏字段不是兼容输入，若出现在 seed 或 memory 资源中会直接触发当前知识资源合同错误。

## 3. 当前口径边界

- 不再恢复 `/api/agent/kb/*` 调试接口；需要验证 Agent 行为时走 `/api/agent/chat` 或服务级测试。
- 不再使用旧 `assumption_ask` 节点或旧假设参数表；需求缺口、默认解释和澄清由当前 `services/agent_requirement_*` 与 `services/agent_conversation_text.py` 承载。
- 不得把旧 `report_account`、`report_data_mapping`、旧 `driver_*`、旧 `control_item_*`、`pivot_aggregate_rule`、`needs_calc`、预测工作台或假设参数内容放入当前知识库 seed/template。
- Agent 查询契约以 `apps/api/app/agent_query_spec.py` 为准，运行时只能围绕当前机构及产品指标树、运行引用、产品、部门、时间和 compare 版本组织查询。

## 4. 维护规则

主数据或业务口径调整后，先更新 seed/template，再用 `/api/agent/chat` 做当前口径 smoke。运行 trace 写入 `var/logs/agent/`，不得放回 `resources/knowledge_base/generated/`。
