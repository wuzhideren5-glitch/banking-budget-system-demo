# 知识库总览（测试阶段）

本目录用于支撑预算智能体的长期记忆与查询规划，按职责拆分为 5 类知识库：

1. `01_data_semantics/`：数据语义层（主数据、维度、映射关系）
2. `02_metric_definitions/`：指标口径层（同比、环比、预实对比等）
3. `03_conversation_memory/`：历史问答经验层（结构化 + 向量素材）
4. `04_term_synonyms/`：术语归一化层（业务口语 -> 标准编码）
5. `05_analysis_templates/`：分析表达模板层（报告结构与文本模板）

## 推荐维护顺序

1. 先补 `01_data_semantics`（确保“问什么能查到什么”）
2. 再补 `02_metric_definitions`（确保“怎么算”口径统一）
3. 逐步沉淀 `03_conversation_memory`（确保“越用越聪明”）
4. 最后扩展 `04/05`（提升理解速度和输出质量）

## 更新机制建议

- 主数据变更（科目/部门/产品/映射）后，先更新 `01_data_semantics`。
- 新增分析口径时，先更新 `02_metric_definitions`，再发布到 Agent。
- 每次真实问答后，把有效记录写入 `03_conversation_memory`。
- 每周对低质量历史经验做清洗，避免错误经验被重复召回。

## 一键构建命令

在项目根目录执行：

`backend/.venv/bin/python backend/scripts/build_knowledge_base.py`

该命令会自动：

- 检查并初始化 `data/common.db`、`data/budget_{year}.db`
- 抽取主数据并生成 `*_seed.*` 文件
- 输出构建报告 `generated/kb_build_report.json`
