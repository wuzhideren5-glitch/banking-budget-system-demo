# Agent 知识库总览

本目录用于支撑预算智能体的长期记忆、查询规划和提示资产，按职责拆分为当前知识资源与运行配置：

当前 `resources/knowledge_base/` 一级目录精确清单（工作树门禁读取）：`01_data_semantics`, `02_metric_definitions`, `03_conversation_memory`, `04_term_synonyms`, `05_analysis_templates`, `06_agent_prompts`, `generated`。

1. `01_data_semantics/`：数据语义层（主数据、维度、映射关系）
2. `02_metric_definitions/`：指标口径层（同比、环比、预实对比等）
3. `03_conversation_memory/`：历史问答经验层（结构化 + 向量素材）
4. `04_term_synonyms/`：术语归一化层（业务口语 -> 标准编码）
5. `05_analysis_templates/`：分析表达模板层（报告结构与文本模板）
6. `06_agent_prompts/`：产品经理意图分类、组织提示、指标规则和提示词资产
7. `generated/`：当前 Agent 运行配置和运行库统计快照，不保存运行 trace
8. `API_QUICKSTART.md`：当前 Agent 公开入口和内部知识库读取链路说明

## 推荐维护顺序

1. 先补 `01_data_semantics`（确保“问什么能查到什么”）
2. 再补 `02_metric_definitions`（确保“怎么算”口径统一）
3. 逐步沉淀 `03_conversation_memory`（确保“越用越聪明”）
4. 最后扩展 `04/05/06`（提升理解速度、输出质量和意图路由稳定性）

## 更新机制建议

- 主数据变更（科目/部门/产品/映射）后，先更新 `01_data_semantics`。
- 新增分析口径时，先更新 `02_metric_definitions`，再发布到 Agent。
- 每次真实问答后，把有效记录写入 `03_conversation_memory`。
- 每周对低质量历史经验做清洗，避免错误经验被重复召回。

## 当前加载机制

当前 `KnowledgeBaseService` 直接读取本目录内的 seed/template 文件，不再依赖已删除的 `apps/api/scripts/build_knowledge_base.py` 构建脚本。运行时会读取：

- `01_data_semantics/data_dictionary_seed.csv`
- `02_metric_definitions/metric_catalog_seed.yaml`
- `03_conversation_memory/memory_record_seed.jsonl`
- `04_term_synonyms/synonyms_seed.csv`
- `05_analysis_templates/analysis_template_library.md`
- `06_agent_prompts/*`
- `generated/agent_runtime_config.json`

主数据大规模调整后，先更新上述 seed 文件，再用 API smoke 或 Agent 查询验证当前口径。`generated/kb_build_report.json` 仅保留当前运行库快照说明，不得把其中不存在于当前 schema 的历史表作为新业务来源。

运行时调试日志写入 `var/logs/agent/`，不得回到 `resources/knowledge_base/generated/`，避免历史问答原文、旧提示词或旧口径混入当前知识资源。

每个一级目录都必须保留自己的 `README.md`，说明当前用途、文件清单和不得混入的历史/运行态材料；工作树门禁会检查这一点。
