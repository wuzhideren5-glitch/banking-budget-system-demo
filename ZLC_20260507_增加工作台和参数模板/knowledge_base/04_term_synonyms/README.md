# 术语同义词知识库

用于把用户口语表达归一化到数据库标准维度，减少澄清轮次。

## 文件说明

- `synonyms_template.csv`：同义词映射模板

## 维护建议

- 一个业务词可以映射多个候选标准项，并设置 `confidence`。
- 模糊度较高的词条，建议 `requires_confirmation=true`，让 Agent 二次确认。
