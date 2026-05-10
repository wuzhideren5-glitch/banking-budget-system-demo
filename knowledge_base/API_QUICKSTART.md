# Agent 知识库 API 快速使用

## 1) 查看知识库状态

`GET /api/agent/kb/stats`

用途：

- 查看知识库是否就绪
- 查看各类记录量（语义、术语、指标、经验）
- 查看最近一次构建报告

## 2) 检索问题上下文

`POST /api/agent/kb/context`

请求体示例：

```json
{
  "query": "请分析个人金融部一季度预算执行差异",
  "top_k": 5
}
```

返回结构：

- `matches.data_semantics`
- `matches.synonyms`
- `matches.metrics`
- `matches.conversation_memories`
- `analysis_template_excerpt`

## 3) 推荐接入位置（LangGraph）

- 在 `requirement_check` 节点调用：补齐槽位判定
- 在 `assumption_ask` 节点调用：生成默认假设
- 在 `analysis_gen` 节点调用：统一口径和表达模板

## 4) 聊天入口（已提供）

`POST /api/agent/chat`

请求体示例：

```json
{
  "message": "请分析个人金融部一季度预算执行差异",
  "history": [
    { "role": "user", "content": "你好" },
    { "role": "assistant", "content": "你好，我是预算智能助手。" }
  ],
  "top_k": 5
}
```

返回关键字段：

- `intent_type`：`budget` / `general`
- `next_action`：`clarify` / `plan_query` / `general_answer`
- `need_clarification`：是否还需追问
- `missing_slots`：缺失要素列表
- `clarification_options`：按缺失槽位返回候选补充选项（可直接点击/回填）
- `assumptions`：默认假设
- `suggested_sql`：建议的只读 SQL（首版）
- `executed`：是否已执行只读 SQL
- `result_row_count`：结果行数
- `result_preview`：结果预览（最多前 30 行）
- `memory_id`：自动沉淀的会话记忆 ID

执行提示：

- 若上一轮返回 `clarify`，可直接回复“按默认假设执行”触发只读查询执行。

## 5) 反馈入口（已提供）

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

- 将用户满意度回写到 `memory_runtime.jsonl` 对应记录，供后续经验筛选与优化。
- 当用户点“不满意”后，前端会自动触发二次澄清请求，帮助补充条件后重跑查询。
- 前端提供“按当前口径重跑”快捷动作，会继承上轮预算问题上下文执行只读查询。
- 前端将候选项按槽位分组显示，支持多项选择后“一次发送已选条件”。
