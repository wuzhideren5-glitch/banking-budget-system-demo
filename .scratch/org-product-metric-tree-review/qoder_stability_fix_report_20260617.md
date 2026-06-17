# 机构及产品指标表稳定性整改工作汇报

**执行者**: Qoder AI
**执行日期**: 2026-06-17
**整改范围**: 机构及产品指标表模块（前后端）

---

## 一、整改背景

机构及产品指标表模块由 Codex 开发，因需求描述不够清晰及多次重复合并，导致：
- 数据库旧表残留与新表并存，部分代码仍读旧表
- 字段语义混淆（functional_group_code 混用"表名"和"编码"两个含义）
- 隐式父节点导入时自动创建但保存时因名称为空而失败
- Schema 不一致导致 500 错误
- 数据传递链路冗余，前端需多次请求才能加载完整数据

整改前测试状态：**15 failed / 79 total（19% 失败率）**

---

## 二、整改内容

### Task 1：紧急止血 — Schema 与旧表清理

| 项目 | 内容 |
|------|------|
| 修改文件 | `org_product_metric_runtime_sync.py`、`metric_tree_rollups.py`、`schemas.py`、`runtime_metric_tree.py` |
| 主要动作 | 清除 `org_product_metric_table` 旧表的活跃读取；统一数据源为 `data_account_metric_node`；补齐 `annual_agg_rule` 缺失字段 |
| 验证结果 | 83/83 通过 |

### Task 2：字段语义拆分

| 项目 | 内容 |
|------|------|
| 修改文件 | `schemas.py`、`runtime_metric_tree.py`、`org_product_metric_runtime_sync.py`、`org_product_metric_runtime_snapshot.py`、`runtime_metric_refs.py`、`budget_simulation_metrics.py`、`expense_forecast_metric_sources.py`、`expense_budget_execution_master_sync.py`、`budget_output_display.py`、`budget_output_display_config.py`、`agent_product_intent.py` 及相关测试 |
| 主要动作 | 新增 `metric_table_name` 字段；将中文表名从 `functional_group_code` 迁移至新字段；所有"按表名筛选"的查询改用 `metric_table_name`；含自动迁移逻辑 |
| 设计原则 | `functional_group_code` 保留不删除，仅用于功能族编码；向后兼容 |

### Task 3：隐式父节点命名修复

| 项目 | 内容 |
|------|------|
| 修改文件 | `org_product_metric_runtime_sync.py`、`org_product_helpers.py` 及 4 个测试文件 |
| 主要动作 | 改进 `_node_name` 函数，支持从子节点名称派生父节点名；新增 `_ensure_metric_node_has_name` 保存前自动补名函数；命名优先级：显式名称 → code → 子节点派生 → 兜底"(未命名)" |
| 验证结果 | 104/104 通过 |

### Task 4：数据传递链路精简

| 项目 | 内容 |
|------|------|
| 修改文件 | `org_product_metric_config.py`（后端路由）、`OrgProductMetricContent.tsx`（前端组件） |
| 主要动作 | `bootstrap` API 合并 `db-snapshot` 数据（新增 `entities` 字段）；前端初始化请求从 3 次减为 2 次；`db-snapshot` 保留作为向后兼容别名 |
| 确认结果 | snapshot/binding 表仅在预测输出和数据录入时按需生成，符合精简目标 |

---

## 三、整改成果

| 指标 | 整改前 | 整改后 |
|------|--------|--------|
| 测试通过率 | 81%（64/79） | **100%（104/104）** |
| 阻断问题数 | 4 | **0** |
| 前端初始化请求数 | 3 次 | **2 次** |
| 字段语义歧义 | functional_group_code 混用 | **拆分为独立字段** |
| 隐式父节点错误 | 导入成功/保存失败 | **全链路一致** |

---

## 四、数据库备份

- 备份文件：`apps/var/data/common.db.bak.20260617`
- 备份时间：2026-06-17 整改开始前

---

## 五、后续建议

1. **前端组件拆分**：`OrgProductMetricContent.tsx`（5191 行）建议拆分为独立 hooks 和子组件
2. **全链路集成测试**：覆盖 导入 → 编辑 → 保存 → 预测输出 完整流程
3. **数据血缘文档**：建立从指标树到预算汇总的完整数据血缘图
4. **自动化门禁**：CI 中加入 org_product 测试作为合并门禁

---

*本次整改由 Qoder AI 于 2026-06-17 自动完成，所有修改均通过完整测试验证。*
