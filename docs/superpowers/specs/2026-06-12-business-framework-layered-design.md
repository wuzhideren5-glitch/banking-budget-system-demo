# 业务整体框架图设计稿：预算管理与部门费用

## 1. 设计目标

本设计用于整理一份面向业务方的系统框架图。最终建议做成两页：

- 第 1 页：预算管理整体框架。
- 第 2 页：部门费用整体框架。

两页采用同一套数据分层表达：**数据来源层 -> 参数规则层 -> 数据处理层 -> 事实汇总层 -> 输出分析层**。这样可以把两个业务闭环分开讲，又保持统一的阅读结构。

本设计不新增系统功能，也不调整现有代码。它只定义业务框架图、工作流脑图、数据流脑图、参数清单和先后顺序，供后续制作 PPT、Word 或详细设计文档使用。

## 2. 总体表达方式

### 2.1 两页结构

| 页码 | 主题 | 讲清楚的问题 | 推荐图形 |
| --- | --- | --- | --- |
| 第 1 页 | 预算管理整体框架 | 预算数据从哪里来，如何经过机构及产品指标体系、公式、汇总和版本管理，最终形成预算展示、预测输出、模拟测算和多维分析 | 数据分层框架图 |
| 第 2 页 | 部门费用整体框架 | 费用执行、部门科目、预算科目、BI 映射和预测规则如何形成部门费用预测、费用执行报表和投入产出专题 | 数据分层框架图 |

### 2.2 统一五层

| 层级 | 业务含义 | 图中建议写法 |
| --- | --- | --- |
| 数据来源层 | 外部报表、业务报送、人工录入、历史版本等原始输入 | “数据从哪里来” |
| 参数规则层 | 年度、版本、组织、科目、指标、映射、公式、规则等业务口径配置 | “按什么口径处理” |
| 数据处理层 | 导入、校验、匹配、写入、计算、汇总、刷新等系统动作 | “系统如何处理” |
| 事实汇总层 | 事实表、快照表、汇总表、读模型、审计日志等数据沉淀 | “沉淀到哪里” |
| 输出分析层 | 报表、预测、专题、透视、智能报告、Agent 等最终使用场景 | “最后给谁用” |

## 3. 第 1 页：预算管理整体框架

### 3.1 框架图

```mermaid
flowchart TB
  subgraph S1["1. 数据来源层"]
    A1["管会报表"]
    A2["业务报送"]
    A3["机构及产品数据录入"]
    A4["Excel 底稿"]
    A5["历史预算/实际版本"]
  end

  subgraph S2["2. 参数规则层"]
    B1["预算年度 / 预算版本"]
    B2["滚动月份 / current_month"]
    B3["机构及产品"]
    B4["机构及产品指标"]
    B5["唯一指标号码"]
    B6["预算公式 / 实际公式"]
    B7["横向汇总 / 纵向汇总 / 逻辑码"]
    B8["展示版本槽位 / 展示配置"]
  end

  subgraph S3["3. 数据处理层"]
    C1["导入预览与格式校验"]
    C2["版本确认"]
    C3["指标绑定解析"]
    C4["BudgetDataWriter 写入"]
    C5["公式标脏与重算"]
    C6["父节点派生汇总"]
    C7["预算汇总与对比库刷新"]
  end

  subgraph S4["4. 事实汇总层"]
    D1["budget_data"]
    D2["budget_summary"]
    D3["budget_pivot_aggregate"]
    D4["compare_budget_summary"]
    D5["compare_pivot_aggregate"]
    D6["operation_log"]
  end

  subgraph S5["5. 输出分析层"]
    E1["预算展示报表"]
    E2["机构及产品预测输出"]
    E3["模拟测算"]
    E4["当前年度多版本透视"]
    E5["多年度对比透视"]
    E6["智能分析报告 / 智能演示 PPT"]
    E7["Agent 分析"]
  end

  S1 --> S2 --> S3 --> S4 --> S5
```

### 3.2 工作流程脑图

```mermaid
mindmap
  root((预算管理工作流))
    第一步 数据准备
      管会报表
      业务报送
      Excel底稿
      历史版本
    第二步 参数配置
      预算年度
      预算版本
      滚动月份
      机构及产品
      机构及产品指标
      公式配置
      汇总规则
    第三步 数据录入与确认
      机构及产品数据录入
      导入预览
      数据校验
      版本确认
    第四步 系统处理
      绑定解析
      事实写入
      公式重算
      汇总刷新
      审计留痕
    第五步 输出分析
      预算展示报表
      预测输出
      模拟测算
      多维分析
      智能报告
      Agent分析
```

### 3.3 数据流脑图

```mermaid
flowchart LR
  X1["管会报表 / 业务报送 / Excel底稿"] --> X2["机构及产品数据录入"]
  X2 --> X3["版本确认"]
  X3 --> X4["绑定到唯一指标号码"]
  X4 --> X5["BudgetDataWriter 写入 budget_data"]
  X5 --> X6["公式重算 / 横纵汇总"]
  X6 --> X7["budget_summary / budget_pivot_aggregate"]
  X7 --> X8["预算展示报表 / 透视 / 模拟测算"]
  X7 --> X9["compare.db 对比汇总"]
  X9 --> X10["多年度对比透视 / Agent 分析"]
```

### 3.4 关键参数清单

| 参数类别 | 参数 | 作用 |
| --- | --- | --- |
| 版本参数 | 预算年度、预算版本、版本名称、current_month、展示版本槽位 | 决定预算/实际月份窗口、展示列组和对比口径 |
| 组织产品参数 | 机构及产品节点、产品编码、产品层级、AA 实体、全行汇总视角 | 决定数据录入和报表展示范围 |
| 指标参数 | 机构及产品指标、唯一指标号码、产品内指标码、value_type | 决定指标身份、展示精度和事实写入主键 |
| 公式参数 | 预算公式、实际公式、公式引用、allow_manual_entry、need_calc | 决定可录入性、计算依赖和重算范围 |
| 汇总参数 | horizontal_rollup、vertical_rollup、logic_code、value_source | 决定父节点派生事实和横向/纵向汇总方式 |
| 展示参数 | 展示视图、展示行、展示版本、金额单位、月份展开 | 决定预算展示报表和导出样式 |

### 3.5 先后顺序

1. 维护机构及产品和机构及产品指标，确认唯一指标号码。
2. 配置预算年度、版本、滚动月份和展示版本槽位。
3. 录入或导入机构及产品数据，系统进行格式校验和预览。
4. 用户确认版本，系统解析指标绑定并写入预算事实。
5. 系统执行公式重算、横纵汇总、预算汇总和对比库刷新。
6. 预算展示报表、预测输出、模拟测算、多维透视和 Agent 读取汇总结果。

### 3.6 当前代码实现逻辑

预算管理主线现在已经不是“多个录入口分别写事实表”，而是围绕 **机构及产品指标体系 -> 运行引用 -> 预算事实 -> 汇总读模型 -> 输出分析** 这一条链路实现。

#### 3.6.1 前端入口

| 业务动作 | 当前前端组件 / API client | 调用的后端接口 |
| --- | --- | --- |
| 维护机构及产品指标、公式、横向汇总、纵向汇总、逻辑码 | `apps/web/src/app/components/OrgProductMetricContent.tsx` | `/api/org-product-metrics/bootstrap`、`/api/org-product-metrics/table-catalog`、`/api/org-product-metrics/db-snapshot`、`/api/org-product-metrics/save-table`、`/api/org-product-metrics/save-refresh`、`/api/org-product-metrics/import-report`、`/api/org-product-metrics/export-report` |
| 录入机构及产品预算/实际/预测数据 | `apps/web/src/app/components/OrgProductDataEntryContent.tsx` | `/api/org-product-data-entry/db-snapshot`、`/api/org-product-data-entry/save-refresh`、`/api/org-product-data-entry/import-workbook`、`/api/org-product-data-entry/budget-sync/preview`、`/api/org-product-data-entry/budget-sync/apply`、`/api/org-product-data-entry/export` |
| 运行机构及产品预测输出 | `apps/web/src/app/components/OrgProductForecastOutputContent.tsx` | `/api/org-product-output/versions`、`/api/org-product-output/run`、`/api/org-product-output/export`、`/api/org-product-output/commit` |
| 预算展示报表和展示配置 | `apps/web/src/lib/budgetOutputApi.ts` | `/api/budget-output/display-report`、`/api/budget-output/display-config`、`/api/budget-output/display-report/export-full` |
| 预算事实刷新跑批 | `apps/web/src/app/components/BudgetActualBatchContent.tsx`、`apps/web/src/lib/budgetActualBatchApi.ts` | `/api/budget-actual-batch/versions`、`/api/budget-actual-batch/preview`、`/api/budget-actual-batch/run`、`/api/budget-actual-batch/history` |
| 多维透视 | `apps/web/src/app/components/PivotTableContent.tsx`、`apps/web/src/lib/pivotSummaryApi.ts` | `/api/budget-summary/aggregate`、`/api/compare-summary/aggregate`、对应导出接口 |

#### 3.6.2 后端主链路

| 层级 | 当前代码承接 | 实际实现逻辑 |
| --- | --- | --- |
| 参数规则层 | `apps/api/app/routers/org_product_metrics.py` | 统一承载机构及产品指标、数据录入、预测输出的大部分 HTTP 接口；导入指标表时会读取“横向汇总”“纵向汇总”“逻辑码”等列，并通过 `_derive_metric_logic_code()`、`_normalize_rollup_flag()` 归一化。 |
| 参数同步到运行引用 | `apps/api/app/services/org_product_metric_runtime_sync.py` | 将机构及产品指标保存结果同步到 `data_account_metric_node`、`data_account`、`data_account_metric_binding`，保持唯一指标号码、产品前缀、`logic_code`、`horizontal_rollup`、`vertical_rollup` 与运行表一致。 |
| 数据录入同步预算事实 | `apps/api/app/services/org_product_budget_sync.py` | `plan_org_product_budget_sync()` 只处理 `mapping_status=MANUAL_CONFIRMED` 且已绑定 `data_acct_code` 的行；按月读取预算/实际单元格，校验 `current_month` 窗口，生成 `BudgetDataWriteItem`。`apply_org_product_budget_sync_plan()` 再调用 BudgetDataWriter 写入事实。 |
| 事实写入约束 | `apps/api/app/budget_data_writer.py` | 预算事实写入统一由 BudgetDataWriter 承载；写入策略会控制公式科目、手工录入、冲突 upsert、`need_calc` 等约束，避免页面或导入流程直接写 `budget_data`。 |
| 横纵汇总 | `apps/api/app/services/metric_tree_rollups.py` | 读取 `data_account_metric_node` 的 `horizontal_rollup`、`vertical_rollup`、`logic_code` 和绑定关系。横向汇总按相同 `logic_code` 跨产品找来源，纵向汇总按子节点绑定找来源，结果写回父节点运行主键对应事实。 |
| 预算汇总 | `apps/api/app/services/budget_summary_rebuild.py` | `rebuild_budget_summary_for_version()` 从 `budget_data`、`data_account`、`period`、机构及产品运行产品清单、指标树路径等重建 `budget_summary`；同时按版本 `current_month` 过滤预算/实际口径。 |
| 透视聚合 | `apps/api/app/services/pivot_aggregate.py` | `rebuild_budget_pivot_aggregate_for_version()` 重建当前年度透视读模型；`list_budget_pivot_aggregate_rows()` 和 `list_compare_pivot_aggregate_rows()` 支撑前端透视查询。 |
| 对比汇总 | `apps/api/app/services/compare_summary_sync.py` | 根据展示版本槽位和预算汇总结果同步 `compare.db`，形成多年度对比透视可读的 `compare_budget_summary` 和 `compare_pivot_aggregate`。 |
| 预算展示 | `apps/api/app/routers/budget_output.py`、`apps/api/app/services/budget_output_display.py`、`apps/api/app/services/budget_output_display_config.py` | 展示配置读取 `budget_output_display_item`，展示报表读取预算汇总和展示版本，导出全套预算展示报表。展示配置可从机构及产品指标候选重建，但计算身份仍回到运行引用和预算事实。 |

#### 3.6.3 预算事实同步的实际顺序

```mermaid
sequenceDiagram
  participant UI as 机构及产品数据录入页面
  participant Router as org_product_metrics.py
  participant Sync as org_product_budget_sync.py
  participant Writer as BudgetDataWriter
  participant Rollup as metric_tree_rollups.py
  participant Summary as budget_summary_rebuild.py
  participant Pivot as pivot_aggregate.py

  UI->>Router: budget-sync/preview 或 apply
  Router->>Sync: plan_org_product_budget_sync()
  Sync->>Sync: 过滤未确认行、未绑定行、空值、非法月份窗口
  Sync->>Writer: write_budget_data_items()
  Writer->>Writer: 校验手工/公式、写入 budget_data、标记 need_calc
  Sync->>Rollup: rebuild_metric_tree_rollups()
  Rollup->>Writer: 写入 value_source=rollup 的父节点事实
  Sync->>Summary: rebuild_budget_summary_for_version()
  Sync->>Pivot: rebuild_budget_pivot_aggregate_for_version()
  Sync-->>UI: 返回写入单元格、rollup、summary、aggregate 统计
```

#### 3.6.4 预算刷新跑批逻辑

`预算事实刷新跑批` 不是录入口，而是对已有事实做集中刷新。当前由 `apps/api/app/routers/budget_actual_batch.py` 暴露接口，由 `apps/api/app/services/budget_actual_batch.py` 编排执行：

1. 选择版本、产品范围和预算/实际口径。
2. 可选执行产品公式重算。
3. 执行配置驱动的指标树横纵汇总。
4. 可选重建 `budget_summary`。
5. 可选重建 `budget_pivot_aggregate`。
6. 可选同步 `compare.db` 并重建 compare 聚合。
7. 写入 `operation_log`，记录影响行数和刷新动作。

## 4. 第 2 页：部门费用整体框架

### 4.1 框架图

```mermaid
flowchart TB
  subgraph F1["1. 数据来源层"]
    A1["费用执行明细"]
    A2["BI 报送"]
    A3["部门费用框架"]
    A4["部门费用预算报送"]
    A5["上年实际 / 本年预算"]
    A6["成本收入比实际"]
  end

  subgraph F2["2. 参数规则层"]
    B1["主体 / 事业群"]
    B2["费用责任部门"]
    B3["归口管理部门"]
    B4["部门科目"]
    B5["部门预算科目"]
    B6["BI-AI 科目映射"]
    B7["归口映射"]
    B8["费用预测规则"]
    B9["规则参数 / 指标表达式 / 人工覆盖"]
  end

  subgraph F3["3. 数据处理层"]
    C1["导入解析"]
    C2["BI 与部门映射匹配"]
    C3["费用实际 Adapter"]
    C4["预测规则计算"]
    C5["预测重算"]
    C6["人工覆盖"]
    C7["预算执行口径组装"]
    C8["成本收入比计算"]
  end

  subgraph F4["4. 事实汇总层"]
    D1["expense_actual_detail_raw"]
    D2["expense_forecast_entry"]
    D3["expense_forecast_calc_result"]
    D4["expense_forecast_override"]
    D5["budget_subject_catalog"]
    D6["dept_account"]
    D7["费用报表读模型"]
  end

  subgraph F5["5. 输出分析层"]
    E1["部门费用预测"]
    E2["费用预算执行报表"]
    E3["业务支出成本收入比维护"]
    E4["投入产出专题概览"]
    E5["Excel 导出结果文件"]
  end

  F1 --> F2 --> F3 --> F4 --> F5
```

### 4.2 工作流程脑图

```mermaid
mindmap
  root((部门费用工作流))
    第一步 数据准备
      费用执行明细
      BI报送
      部门费用框架
      费用预算报送
      成本收入比实际
    第二步 主数据与映射
      部门科目
      部门预算科目
      费用责任部门
      归口管理部门
      BI-AI科目映射
      归口映射
    第三步 预测规则配置
      费用预测规则
      规则参数
      指标表达式
      人工覆盖
    第四步 系统处理
      导入解析
      匹配校验
      实际数适配
      预测计算
      预算执行报表组装
      成本收入比计算
    第五步 输出分析
      部门费用预测
      费用预算执行报表
      成本收入比
      投入产出专题
      导出文件
```

### 4.3 数据流脑图

```mermaid
flowchart LR
  X1["费用执行明细 / BI报送"] --> X2["费用执行明细导入"]
  X2 --> X3["BI-AI 科目映射 / 归口映射"]
  X3 --> X4["expense_actual_detail_raw"]
  X4 --> X5["费用实际 Adapter"]
  X5 --> X6["部门费用预测 / 费用预测规则计算"]
  X6 --> X7["expense_forecast_entry / calc_result / override"]
  X7 --> X8["费用预算执行报表"]
  X4 --> X8
  X8 --> X9["报表导出 / 费用分析"]
  X4 --> X10["业务支出成本收入比 / 投入产出专题"]
```

### 4.4 关键参数清单

| 参数类别 | 参数 | 作用 |
| --- | --- | --- |
| 组织参数 | 主体、事业群、费用责任部门、归口管理部门 | 决定费用归属、筛选范围和报表汇总层级 |
| 科目参数 | 部门科目、部门预算科目、预算科目叶子节点 | 决定费用预测和费用执行报表的科目口径 |
| 映射参数 | BI-AI 科目映射、归口管理部门到费用归属部门映射 | 决定外部费用明细如何进入系统口径 |
| 导入参数 | import_kind、来源文件、报表月份、匹配状态、覆盖策略 | 决定费用实际、上年实际和本年预算的取数来源 |
| 预测参数 | 预测规则、规则参数、指标表达式、规则变量、重算范围 | 决定部门费用预测如何自动计算 |
| 覆盖参数 | 人工覆盖值、系统测算值、最终预测值 | 决定人工调整后如何保留测算依据 |
| 输出参数 | 报表视角、报表月份、金额单位、零值行、关键字、导出模式 | 决定费用预算执行报表展示和导出 |

### 4.5 先后顺序

1. 维护部门科目、部门预算科目和费用责任部门口径。
2. 维护 BI-AI 科目映射和归口管理部门映射。
3. 导入费用执行明细，系统解析、匹配并形成费用实际明细。
4. 配置费用预测规则、规则参数和指标表达式。
5. 系统读取实际数、规则和人工覆盖，形成部门费用预测。
6. 费用预算执行报表综合预算、实际、上年同期和预算科目树形成展示。
7. 成本收入比和投入产出专题读取各自私有状态与映射结果形成专题分析。

### 4.6 当前代码实现逻辑

部门费用主线现在是一个相对独立的费用闭环：**部门/预算科目主数据 -> BI 和归口映射 -> 费用实际导入 -> 费用预测规则与人工覆盖 -> 费用预算执行报表 / 成本收入比 / 投入产出专题**。

#### 4.6.1 前端入口

| 业务动作 | 当前前端组件 / API client | 调用的后端接口 |
| --- | --- | --- |
| 部门科目维护 | 部门科目维护页、`apps/web/src/lib/deptCatalogViewModel.ts` | 后端 `apps/api/app/routers/dept_catalog.py` 暴露部门科目接口 |
| 部门预算科目维护 | `apps/web/src/app/components/BudgetSubjectCatalogContent.tsx`、`apps/web/src/lib/budgetSubjectCatalogViewModel.ts`、`apps/web/src/lib/masterDataApi.ts` | `/api/budget-subject-catalog/*` |
| BI-AI 科目映射、归口映射 | `apps/web/src/app/components/BiMappingContent.tsx`、`BiAiSubjectMappingTab.tsx`、`ManageDeptOwnerMappingTab.tsx`、`apps/web/src/lib/biMappingApi.ts` | `/api/bi-ai-subject-mapping/*`、归口映射由 `apps/api/app/routers/bi_department_mapping.py` 承载 |
| 费用执行明细导入 | `apps/web/src/app/components/ExpenseActualImportContent.tsx`、`apps/web/src/lib/expenseActualImportApi.ts` | `/api/expense-actual-import/import-preview`、`/api/expense-actual-import/import-apply`、`/api/expense-actual-import/batches` |
| 费用预测逻辑配置 | `apps/web/src/app/components/ExpenseForecastRuleContent.tsx`、`apps/web/src/lib/expenseForecastApi.ts` | `/api/expense-forecast/rules`、`/api/expense-forecast/recalculate`、`/api/expense-forecast/rules/import-preview`、`/api/expense-forecast/rules/import-apply` |
| 部门费用预测 | `apps/web/src/app/components/ExpenseForecastContent.tsx`、`ExpenseForecast*` 子组件、`apps/web/src/lib/expenseForecastApi.ts` | `/api/expense-forecast/meta`、`/api/expense-forecast/view`、`/api/expense-forecast/cell`、`/api/expense-forecast/import-preview`、`/api/expense-forecast/import-apply`、`/api/expense-forecast/override`、`/api/expense-forecast/export` |
| 费用预算执行报表 | `apps/web/src/app/components/ExpenseBudgetExecutionContent.tsx`、`ExpenseBudgetExecution*` 子组件、`apps/web/src/lib/expenseBudgetExecutionApi.ts` | `/api/expense-budget-execution`、`/api/expense-budget-execution/export` |
| 成本收入比与投入产出专题 | `apps/web/src/app/components/BusinessCostIncomeRatioAdminContent.tsx`、`InputOutputTopicOverviewContent.tsx`、`apps/web/src/lib/businessCostIncomeApi.ts`、`apps/web/src/lib/inputOutputTopicApi.ts` | `/api/business-cost-income-ratio/*`、`/api/input-output-topic-overview/*` |

#### 4.6.2 后端主链路

| 层级 | 当前代码承接 | 实际实现逻辑 |
| --- | --- | --- |
| 部门主数据 | `apps/api/app/routers/dept_catalog.py`、`apps/api/app/services/dept_catalog.py` | 维护 `dept_account`。费用责任部门取 level=2 叶子部门，是费用导入、预测、执行报表的责任归属口径。 |
| 预算科目主数据 | `apps/api/app/routers/budget_subject_catalog.py`、`apps/api/app/services/budget_subject_catalog.py` | 维护 `budget_subject_catalog`。费用预测和费用执行报表按该预算科目树展示和聚合。 |
| BI 科目映射 | `apps/api/app/routers/bi_subject_mapping.py`、`apps/api/app/services/bi_ai_subject_mapping.py` | 维护 `bi_ai_subject_mapping`，把 BI 五/六级科目、预算发布口径、费用类别、费用大类映射到系统预算科目。 |
| 归口映射 | `apps/api/app/services/bi_department_mapping.py` | 维护 `manage_dept_owner_mapping`，把归口管理部门映射到费用归属部门；可从费用实际明细自动生成候选映射。 |
| 费用实际导入 | `apps/api/app/routers/expense_actual_import.py`、`apps/api/app/services/expense_actual_import_context.py`、`expense_actual_import_parser.py`、`expense_actual_import_apply.py` | 导入预览先加载部门、预算科目、BI 映射、归口映射上下文；解析 Excel 后生成匹配结果；应用时写入 `expense_actual_import_batch` 和 `expense_actual_detail_raw`，并写入 `operation_log`。 |
| 费用预测视图 | `apps/api/app/routers/expense_forecast.py`、`apps/api/app/services/expense_forecast_view_model.py`、`expense_forecast_data_context.py` | 按年度、版本、费用归属范围加载实际数、预算科目、手工预测、年度输入、规则结果和人工覆盖，组装部门费用预测表。 |
| 费用预测规则 | `apps/api/app/routers/expense_forecast_rules.py`、`apps/api/app/services/expense_forecast_rule_commands.py`、`expense_forecast_rule_read_model.py`、`expense_forecast_rule_calculation.py`、`expense_forecast_recalculation.py` | 规则保存到 `expense_forecast_rule*`；重算时读取实际数、年度输入、预测值、人工覆盖和指标表达式来源，逐规则计算月度结果，再保存到 `expense_forecast_calc_result`。 |
| 人工覆盖 | `apps/api/app/services/expense_forecast_override_commands.py`、`expense_forecast_write_commands.py` | 覆盖值写入 `expense_forecast_override`，并同步最终预测值；删除覆盖时恢复系统测算值。 |
| 费用预算执行报表 | `apps/api/app/routers/expense_budget_execution.py`、`apps/api/app/services/expense_budget_execution_report_resolver.py` | 路由只把 HTTP 参数转换成 report selection。resolver 负责加载运行上下文、费用实际、年度预算、上年实际、预算科目目录，再按 query/monthly/template/subject 等模式组装报表。 |
| 费用实际 Adapter | `apps/api/app/services/expense_budget_execution_actuals.py` | 只读取 `expense_actual_detail_raw` 中 `import_kind='current_year_actual'` 且 owner/subject 匹配成功的行，按主体、事业群、费用责任部门和预算科目聚合。 |
| 年度预算来源 | `apps/api/app/services/expense_budget_execution_budget_source.py` | 从年度库 `budget_summary` 读取预算/上年实际口径，并通过费用框架和预算科目口径映射到费用报表。 |
| 成本收入比 | `apps/api/app/routers/business_cost_income_ratio.py`、`apps/api/app/services/business_cost_income_ratio.py`、`business_cost_income_commands.py` | 维护和读取年度库 `business_cost_income_*` 私有表；手工录入时会校验 item 分区、item id、录入模式和金额单位，再写入 `business_cost_income_value`。 |
| 投入产出专题 | `apps/api/app/routers/input_output_topic_overview.py`、`apps/api/app/services/input_output_topic_overview.py` | 读取成本收入比当前表和机构产品运行引用，按产品模板、投入/产出/指标分区生成专题报表和 Excel 导出。 |

#### 4.6.3 费用实际导入的实际顺序

```mermaid
sequenceDiagram
  participant UI as 费用执行明细导入页面
  participant Router as expense_actual_import.py
  participant Context as expense_actual_import_context.py
  participant Parser as expense_actual_import_parser.py
  participant Apply as expense_actual_import_apply.py
  participant DB as common.db

  UI->>Router: import-preview / import-apply
  Router->>Context: load_expense_actual_import_context()
  Context->>DB: 读取 dept_account、budget_subject_catalog、bi_ai_subject_mapping、manage_dept_owner_mapping
  Router->>Parser: parse_actual_file()
  Parser->>Parser: 匹配费用责任部门、预算科目、BI口径、归口映射
  Router->>Apply: apply_expense_actual_import_rows()
  Apply->>DB: 写入 expense_actual_import_batch
  Apply->>DB: 写入 expense_actual_detail_raw
  Router->>DB: 写入 operation_log
```

#### 4.6.4 费用预测和报表的实际顺序

```mermaid
sequenceDiagram
  participant Forecast as 部门费用预测
  participant Rule as 费用预测规则
  participant Actual as 费用实际 Adapter
  participant Calc as expense_forecast_recalculation.py
  participant Report as 费用预算执行报表
  participant Summary as budget_summary

  Forecast->>Rule: 维护规则、参数、指标表达式
  Forecast->>Actual: 读取 expense_actual_detail_raw 当前实际
  Forecast->>Calc: recalculate_expense_forecast_rules()
  Calc->>Calc: 读取实际数、年度输入、预测值、人工覆盖
  Calc->>Calc: calculate_expense_forecast_rule_months()
  Calc->>Forecast: 保存 calc_result，保留覆盖状态
  Report->>Actual: 读取当前费用实际
  Report->>Summary: 读取年度预算/上年实际
  Report->>Report: 组装 query/monthly/template/subject 报表
```

## 5. 两页之间的关系

```mermaid
flowchart LR
  A["预算管理框架"] --> C["预算事实与汇总结果"]
  B["部门费用框架"] --> D["费用实际与费用预测结果"]
  C --> E["多维分析工具"]
  D --> E
  C --> F["智能分析报告 / 智能演示 PPT / Agent"]
  D --> F
```

两页是并列业务闭环，不建议合并成一张大图：

- 预算管理更强调机构及产品指标体系、预算事实、公式、版本、预测输出和预算展示。
- 部门费用更强调费用责任部门、部门预算科目、BI 映射、费用实际、费用预测和费用执行报表。
- 两者最终都可以进入多维分析、智能报告、智能演示 PPT 和 Agent 分析，但不共享同一套录入口径。

## 6. PPT 或 Word 落版建议

### 第 1 页：预算管理

标题建议：**预算管理整体框架：从指标配置到预算输出**

版式建议：

- 左侧或顶部放五层分层框架。
- 每层用 3 到 6 个关键词，避免塞满表名。
- 底部放一条工作顺序：配置 -> 录入 -> 确认 -> 写入 -> 计算 -> 输出。
- 备注区说明：机构及产品指标体系是唯一主指标体系，预算事实通过 BudgetDataWriter 写入。

### 第 2 页：部门费用

标题建议：**部门费用整体框架：从费用实际到预测与执行报表**

版式建议：

- 复用第 1 页五层结构，让业务方一眼知道两页是同一套表达。
- 每层突出“部门、科目、映射、预测、报表”。
- 底部放一条工作顺序：主数据 -> 映射 -> 导入 -> 匹配 -> 预测 -> 报表。
- 备注区说明：费用执行明细是费用实际 Adapter，不替代预算事实表。

## 7. 边界与后续详细设计

本设计只解决业务框架表达，不替代数据库设计、接口设计或页面原型。后续如果要推进到详细设计，建议按以下顺序展开：

1. 为两页分别补充可交付版 PPT 图。
2. 为每个层级列出当前页面入口和责任模块。
3. 补充每个导入流程的模板、预览、应用和结果文件要求。
4. 补充每个报表输出的取数口径、版本口径和导出血缘。
5. 如需开发变更，再拆成具体 issue 或 PRD。
