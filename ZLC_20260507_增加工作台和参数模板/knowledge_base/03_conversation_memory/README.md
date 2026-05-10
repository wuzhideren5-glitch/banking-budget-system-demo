# 历史问答经验知识库

用于沉淀“问题 -> 澄清 -> 查询 -> 结论 -> 反馈”的完整经验闭环。

## 文件说明

- `conversation_memory_schema.json`：结构化记录的字段规范。
- `memory_record_template.jsonl`：JSONL 样例，便于后续批量追加。

## 维护建议

- 一次会话一条主记录，必要时追加多条“修订记录”。
- 推荐保留字段：问题意图、关键维度、最终 SQL、分析结论、用户满意度。
- 向量化时使用 `embedding_text` 字段作为主语义文本。
