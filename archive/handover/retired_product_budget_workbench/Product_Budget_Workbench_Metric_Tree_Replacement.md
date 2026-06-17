# 产品预算工作台指标树替换数据架构

## 目标

产品预算工作台改为直接围绕数据科目指标树工作。业务人员维护和查看的是一套产品化工作台视图，但底层指标语义保持全局一致：同一个 `metric_node_code` 在任何产品下都代表同一个业务指标口径。

正式指标节点编码采用 `0X.0X.00X` 形态，例如 `01.01.001`。`01` 和 `01.01` 只作为一级/二级分组节点；`01.01.05` 这类两位叶子码属于历史导入残留，不能作为产品预算工作台主轴。

## 核心表分工

| 表 | 定位 | 产品维度 | 说明 |
| --- | --- | --- | --- |
| `data_account_metric_node` | 全局标准数据科目指标树 | 不直接绑定产品 | 维护 `00` 根节点、`01-08` 一级业务大类、业务子类、标准指标节点。 |
| `product_budget_component` | 产品预算工作台状态表 | 绑定产品 | 表达某产品工作台里启用了哪些指标、配置状态、公式、试算、是否已绑定数据科目。 |
| `data_account_metric_binding` | 正式指标-产品-数据科目绑定表 | 绑定产品/范围 | 只在已经绑定到 `data_account` 后写入，只解释唯一指标号码对应的指标节点和产品范围。 |
| `data_account` | 数据科目维护主表 | 通过唯一指标号码表达 | 保存真正参与预算取数、公式、计算和落库的数据科目，主键固定为 `metric_node_code + "." + scope_code`。 |
| `report_account` / `report_data_mapping` | 报告展示层 | 不定义产品范围 | 只维护报告科目展示与 `data_acct_code` 映射，不作为产品预算工作台主维护入口，也不定义数据科目身份。 |

## 不新增产品指标初始化表

产品指标初始化状态放在 `product_budget_component`。原因是工作台已经需要保存产品、配置状态、公式、试算结果、AI 建议、是否绑定数据科目等草稿状态；这些状态天然属于工作台，不应再单独拆一张初始化表。

`data_account_metric_binding` 不承担未绑定状态，因为它的语义是“正式绑定”，且现有字段 `data_acct_code` 为 `NOT NULL`。

## `product_budget_component` 目标字段演进

保留现有字段，新增指标树主轴字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `metric_node_code` | TEXT, nullable | 指向 `data_account_metric_node.node_code`，作为工作台指标口径主轴。 |
| `data_acct_code` | TEXT, nullable | 指向 `data_account.data_acct_code`；绑定后必须等于 `metric_node_code + "." + product_code` 或 `metric_node_code + ".CORP"`。 |
| `report_acct_code` | TEXT | 报告展示行引用；不参与数据科目身份判定。 |

导入时如果工作台行尚未挂到正式数据科目，`data_acct_code` 为空，状态保留为 `draft` 或 `warning`；完成绑定后写入同一套唯一指标号码。

建议索引：

```sql
CREATE INDEX IF NOT EXISTS idx_product_budget_component_metric
ON product_budget_component(product_code, metric_node_code);

CREATE INDEX IF NOT EXISTS idx_product_budget_component_data_account
ON product_budget_component(data_acct_code);
```

不建议对 `(product_code, metric_node_code)` 加唯一约束，因为一个指标节点未来可能拆多个计算组件。导入初始化时可以先保证每个产品每个指标默认生成一条组件行。

## 导入分层

### 1. 标准指标树导入

目标表：`data_account_metric_node`

来源：指标树 Excel 中的业务分类树，但必须先去产品化并消除同码不同名冲突。

导入字段：

| Excel 字段 | 目标字段 |
| --- | --- |
| 节点编码 | `node_code` |
| 节点名称 | `node_name` |
| 父级完整编码去产品后的节点编码 | `parent_code` |
| 层级 | `level` |
| 节点类型 | `node_type` |
| 来源指标数/排序 | `sort_order` |

当前导入候选文件为 `统一业务指标树全貌_20260514_全局语义编号版.xlsx`。该版本已把编码生成规则从“产品内顺序号”调整为“全局语义号”：第三段编码按业务子类下的规范化语义路径全局分配，保证同一个 `metric_node_code` 在所有产品下语义唯一。

上一版 `统一业务指标树全貌_20260514_无09业务定稿版.xlsx` 不能直接作为标准树导入源。校验发现 `业务分类树_分产品` 去产品化后存在同一节点编码多个名称的情况，例如 `01.01.01` 同时出现“管理贷款日均”和“管理资产日均”。新版全局语义编号已消除该类同码不同名冲突。

### 2. 产品工作台初始化导入

目标表：`product_budget_component`

来源：`指标树全貌_分产品` 中 `是否纳入业务树 = 是` 的记录。

导入字段：

| Excel 字段 | 目标字段 |
| --- | --- |
| 范围代码 | `product_code` |
| 系统指标编码 | `metric_node_code` |
| 指标名称 | `component_name` |
| 业务性质/Excel 科目性质 | `value_type` 或辅助判断 |
| Excel展示路径 | `ai_reason` 或 remark-like trace 字段 |
| 排序 | `sort_order` |

初始化时 `data_acct_code` 允许为空，`status` 置为 `warning` 或 `draft`，表达“工作台已有指标，但尚未绑定数据科目”。

### 3. 正式绑定导入

目标表：`data_account_metric_binding`

触发条件：工作台行已经绑定到具体 `data_account`。

导入字段：

| 来源 | 目标字段 |
| --- | --- |
| `metric_node_code + "." + product_code` | `data_acct_code` |
| 工作台 `metric_node_code` | `metric_node_code` |
| 产品编码 | `scope_code` |
| 绑定的数据科目 | `data_acct_code` |

导入后回填 `product_budget_component.data_acct_code`。

## 迁移顺序

1. 备份 `common.db`。
2. 给 `product_budget_component` 增加 `metric_node_code`、`data_acct_code` 和索引；物理表中不得保留历史绑定码字段。
3. 使用“全局语义编号版”标准指标树 Excel，确保去产品化后 `node_code -> node_name` 唯一。
4. 导入 `data_account_metric_node`，包括 `00 统一业务指标树` 根节点。
5. 按产品导入 `product_budget_component` 工作台初始化行。
6. 对已有可匹配的数据科目生成或更新 `data_account_metric_binding`。
7. 工作台接口读取 `metric_node_code` 和 `data_acct_code`；`report_acct_code` 只用于报告展示定位。
8. 预算展示报表从产品工作台和指标绑定派生展示行，减少对报告科目映射的身份依赖。

## 导入前必须通过的校验

| 校验项 | 要求 |
| --- | --- |
| 标准树同码不同名 | 0 |
| 标准树父级断裂 | 0 |
| 产品工作台重复初始化 | 同一产品同一指标默认不重复；多组件场景必须有明确组件名 |
| 已绑定数据科目重复 | 同一 `data_acct_code + product_code` 不应绑定多个业务指标 |
| 源 Excel 重码 | 允许存在，但只能作为来源码追溯，不能影响系统编码 |

## 当前结论

这次替换不是新增一套报告树，而是把产品预算工作台从 `report_acct_code` 主轴迁到 `metric_node_code` 主轴。`product_budget_component` 就是工作台状态表，承接产品初始化；`data_account_metric_binding` 只承接正式绑定；`data_account_metric_node` 只承接全局标准指标语义。
