# 机构产品指标表稳定性整改方案

## 现状诊断

| 指标 | 数值 |
|------|------|
| 测试失败率 | 19%（15 failed / 79 total） |
| 阻断问题 | 4 个 |
| 后端核心文件 | org_product_metric_runtime_sync.py (1391行) |
| 前端核心文件 | OrgProductMetricContent.tsx (5191行) |

### 4 个阻断问题

1. **旧表未清理** — `org_product_metric_table` 仍有 46 行残留数据，与新表 `data_account_metric_node` 并存，部分代码仍读旧表
2. **字段语义混淆** — `functional_group_code` 字段混用"指标表名"和"功能族编码"两个含义，导致伪表（如 `01`）出现
3. **同步规则不稳定** — 隐式父节点在导入时自动生成但保存时校验失败（名称为空），15 个测试因此报错
4. **Schema 不一致** — 数据库实际列与代码假设（`allow_manual_entry`、`value_type`等字段）不匹配，导致 500 错误

---

## Task 1：紧急止血 — 修复 Schema 与旧表问题

**目标**: 消除 500 错误和数据源冲突

### 1.1 清理旧表引用

- 检查 `org_product_metric_runtime_sync.py` 中是否仍在读取 `org_product_metric_table`
- 将所有数据源统一指向 `data_account_metric_node`
- 删除或标记废弃旧表的查询代码

### 1.2 修复 Schema 不一致

- 在 `apps/api/app/services/org_product_metric_runtime_sync.py` 中检查所有 SELECT/INSERT 语句
- 确保 `data_account_metric_node` 表实际包含代码引用的所有字段
- 补齐缺失字段的 ALTER TABLE 或修正代码中的字段引用

### 涉及文件

- `apps/api/app/services/org_product_metric_runtime_sync.py`
- `apps/api/app/routers/org_product_metric_config.py`
- `apps/var/data/common.db`（Schema 修复）

---

## Task 2：修复字段语义混淆

**目标**: `functional_group_code` 不再承担双重含义

### 2.1 新增 `metric_table_name` 字段

- 在 `data_account_metric_node` 表增加 `metric_table_name TEXT` 字段
- 迁移：将当前 `functional_group_code` 中属于表名的值（如"存款"、"贷款"）移入新字段
- 将误用为表名的编码值（如 `01`）清理为 NULL

### 2.2 更新查询逻辑

- 后端服务层：所有按"表名"筛选的查询改用 `metric_table_name`
- 前端 API 层：`orgProductMetricApi.ts` 中适配新字段
- 保持 `functional_group_code` 仅用于功能族编码

### 涉及文件

- `apps/api/app/services/org_product_metric_runtime_sync.py`
- `apps/api/app/services/org_product_metric_runtime_snapshot.py`
- `apps/web/src/lib/org-product/orgProductMetricApi.ts`
- `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx`

---

## Task 3：修复同步规则（隐式父节点）

**目标**: 导入和保存的校验规则一致，不再出现"导入成功但保存失败"

### 3.1 统一校验逻辑

- 在 `org_product_metric_runtime_sync.py` 中找到导入逻辑和保存逻辑
- 导入时自动生成的隐式父节点必须赋予有效名称（如"[自动生成]-{子节点名}"）
- 保存前校验：遍历所有节点，任何 `name` 为空的节点自动修补或报错提示

### 3.2 修复测试

- 运行 `apps/api/tests/` 下 org_product 相关测试
- 修复 15 个失败用例，确保测试 100% 通过

### 涉及文件

- `apps/api/app/services/org_product_metric_runtime_sync.py`（核心逻辑）
- `apps/api/tests/test_org_product_metric_runtime_refs.py`（测试修复）

---

## Task 4：精简数据传递链路

**目标**: 按需求文档标准，减少不必要的中间层

### 当前链路（问题）
```
Excel导入 → org_product_metric_table(旧) → data_account_metric_node → snapshot → 前端
                                          ↗ binding → 前端另一条链路
```

### 目标链路（精简后）
```
Excel导入 → data_account_metric_node → 前端 (指标配置)
                                     → snapshot (版本快照，仅预测输出时生成)
                                     → binding (仅数据录入时关联)
```

### 4.1 移除冗余传递

- bootstrap API 和 db-snapshot API 合并为单一数据源接口
- 前端不再需要两次请求来获取完整指标树

### 涉及文件

- `apps/api/app/routers/org_product_metric_config.py`（API 合并）
- `apps/web/src/lib/org-product/orgProductMetricApi.ts`（调用链简化）
- `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx`（数据加载逻辑）

---

## Task 5（后续）：前端组件拆分

**目标**: OrgProductMetricContent.tsx 从 5191 行拆分为可维护的模块

- 提取 `useOrgProductMetricTree` hook（树操作逻辑）
- 提取 `useFormulaEditor` hook（公式编辑状态）
- 拆分 `MetricTableToolbar`、`MetricTreePanel`、`MetricDetailPanel` 子组件
- 此项为长期优化，不阻塞当前稳定性修复

---

## 执行顺序与依赖

```
Task 1 (Schema修复) ──→ Task 2 (字段拆分) ──→ Task 4 (链路精简)
       └──→ Task 3 (同步规则) ──┘
                                        ──→ Task 5 (前端重构，后续)
```

Task 1 是基础，必须先做；Task 2 和 Task 3 可并行；Task 4 依赖前三项完成；Task 5 独立于稳定性修复，可后续安排。

---

## 风险控制

- 每个 Task 完成后运行全量 org_product 测试，确认不引入回归
- Schema 变更前备份 `common.db`
- 字段迁移采用"新增-迁移-验证-清理"四步法，不直接删除旧字段