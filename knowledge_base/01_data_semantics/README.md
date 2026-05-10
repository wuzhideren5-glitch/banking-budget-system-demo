# 数据语义知识库

用于把“用户自然语言”映射到“数据库可查询字段和编码”。

## 文件说明

- `data_dictionary_template.csv`：主数据字典模板（科目/产品/部门/报告）
- `dimension_mapping_template.json`：分析维度映射模板（透视行列页建议）

## 填充原则

- 编码必须以 `Banking_Budget_Database_PDD.md` 为准。
- 每条记录尽量包含：业务名、标准编码、所属表、可用过滤条件。
- 同义词不放在这里，统一维护在 `04_term_synonyms/`。
