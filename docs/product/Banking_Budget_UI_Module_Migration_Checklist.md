# 前端模块统一 UI 改造清单

| 项目 | 说明 |
|------|------|
| 编制日期 | 2026-05-13 |
| 依据 | `Banking_Budget_Frontend_Design_Spec.md` |
| 目标 | 将全部前端模块逐步迁移到统一设计规范 |

---

## 1. 已完成底座

- 新增前端设计规范：`docs/product/Banking_Budget_Frontend_Design_Spec.md`。
- 新增统一 UI 展示方案 PDD：`docs/product/Banking_Budget_UI_Unified_PDD.md`。
- 新增全局样式 token 与基础类：`apps/web/src/styles/design-system.css`。
- 新增金融表格组件入口：`apps/web/src/app/components/ui/financial-grid.tsx`。
- 已接入全局样式入口：`apps/web/src/styles/index.css`。
- 已初步统一全局壳层：`App.tsx`、`Header.tsx`、`StatusBar.tsx`、`NavigationTree.tsx`、`WorkArea.tsx`。
- 历史开发原型入口 `?ui-system-prototype=1` 已删除，避免生产代码保留隐藏页面。

## 2. 第一批：全局壳层与系统框架

目标：所有模块进入前先感到一致。

| 模块 | 文件 | 改造动作 | 状态 |
|------|------|----------|------|
| 应用壳层 | `apps/web/src/app/App.tsx` | 登录页、折叠按钮、分栏背景、resize handle 使用统一 token | 已完成一期 |
| 顶栏 | `apps/web/src/app/components/Header.tsx` | 使用 `bb-topbar`，统一版本选择与退出按钮视觉 | 已完成一期 |
| 底栏 | `apps/web/src/app/components/StatusBar.tsx` | 使用 `bb-statusbar` 与 `bb-popover` | 已完成一期 |
| 左导航 | `apps/web/src/app/components/NavigationTree.tsx` | 使用 `bb-tree-pane`、`bb-tree-item` | 已完成一期 |
| 工作区标签 | `apps/web/src/app/components/WorkArea.tsx` | 标签页、溢出菜单、欢迎空页使用统一 token | 已完成一期 |
| Agent 面板 | `apps/web/src/app/components/ChatBot.tsx` | AI 卡、按钮、历史弹窗、消息表格迁移到 `bb-*` | 待改造 |

## 3. 第二批：基础数据维护

目标：统一树表维护体验。

| 模块 | 文件 | 规范目标 | 优先级 |
|------|------|----------|--------|
| 数据科目运行表 | 已下线 | 前端独立页面已删除；指标配置、公式和录入口径统一进入 `OrgProductMetricContent.tsx`，`data_account*` 仅为机构产品指标运行引用表 | 已删除 |
| 报告科目维护 | 已退休 | 旧报告科目维护入口已退出 active source；预算展示配置使用 `budget_output_display_item`，业务指标身份使用机构及产品指标体系与机构产品指标运行引用 | 已删除 |
| 产品科目维护 | 已退休 | 产品维度统一从“机构及产品”维护；旧 `product_type` 对象不保留，不恢复产品树 CRUD、导入导出或编辑表单 | 已删除 |
| 部门科目维护 | `DataDepartmentContent.tsx` | 部门树、产品映射、费用引用提示统一 | 已完成一期 |
| 部门预算科目维护 | `BudgetSubjectCatalogContent.tsx` | 五级树、公式文本、导出操作统一 | 已完成一期 |

## 4. 第三批：预算管理

目标：预算配置、输入、输出形成统一闭环。

| 模块 | 文件 | 规范目标 | 优先级 |
|------|------|----------|--------|
| 产品预算工作台 | `archive/frontend_retired/product_budget_workbench/ProductBudgetWorkbenchContent.tsx` | 已下线为历史归档；不再作为迁移来源，正式维护入口统一到 `OrgProductMetricContent.tsx` 和机构及产品数据录入链路 | 已归档 |
| 产品预算工作台原型 | `archive/frontend_retired/product_budget_workbench/ProductBudgetWorkbenchPrototypeContent.tsx` | 设计对照已退出 active source，避免形成第二套维护页面 | 已归档 |
| 预算工作台配置 | `ForecastWorkbenchContent.tsx` | 隐藏残留页面已物理删除；正式规则配置不再保留第二套预测工作台 | 已删除 |
| 预算模板与规则 | `BudgetAssumptionContent.tsx` | 隐藏残留页面已物理删除；模板/参数能力收敛到专业 Module | 已删除 |
| 机构及产品数据录入 | `OrgProductDataEntryContent.tsx` | 作为预算/实际/预测事实唯一录入口，确认后通过 `BudgetDataWriter` 同步 `budget_data` | 已收口 |
| 旧预算录入 / 预算指标数据 | `BudgetInputContent.tsx` / `BudgetPredictionContent.tsx` | 已物理删除；不得恢复第二个预算事实录入入口 | 已删除 |
| 模拟测算 | `BudgetSimulationContent.tsx` | 参数区 + 结果区，避免大卡片堆叠 | 已完成一期 |
| 预算展示报表 | `BudgetDisplayReportContent.tsx` | 报表表格、单位切换、月度列折叠统一 | 已完成一期 |

## 5. 第四批：费用闭环

目标：同步、导入、录入、报表、导出同一套交互。

| 模块 | 文件 | 规范目标 | 优先级 |
|------|------|----------|--------|
| 数据同步管理 | `DataSyncManagementContent.tsx` | 操作卡、上传按钮、预览状态统一 | 已完成一期 |
| 费用执行明细导入 | `ExpenseActualImportContent.tsx` | 导入流程、预览表、未匹配预警、批次表统一 | 已完成一期 |
| 项目/费用预算输入 | `ExpenseForecastContent.tsx` | 高密度月度表、单位切换、导入导出统一 | 已完成一期 |
| 费用预算执行报表 | `ExpenseBudgetExecutionContent.tsx` | 查询模式/模板模式、报表表格、导出统一 | 已完成一期 |

## 6. 第五批：分析与智能生成

目标：分析视图、AI 审核、生成质量报告统一。

| 模块 | 文件 | 规范目标 | 优先级 |
|------|------|----------|--------|
| 当前年度透视 / 多年度透视 | `PivotTableContent.tsx` | 字段区、筛选区、透视表、导出统一 | 已完成一期 |
| 多年度数据透视图 | `PivotChartContent.tsx` | 图表控制、空态、单位、展示模式统一 | 已完成一期 |
| 智能分析报告 | `AnalysisReportContent.tsx` | 报告蓝图、审核台、生成参数、预览统一 | 已完成一期 |
| 智能演示 PPT | `AnalysisPPTContent.tsx` | 模板库、绑定工作区、生成中心、质量报告统一 | 已完成一期 |
| 智能助手右栏 | `ChatBot.tsx` | 右侧 Agent 面板、消息流、弹窗、输入工具栏统一 | 已完成一期 |
| Agent 对话测试 | `AgentDialogTestContent.tsx` | 调试页弱化样式，日志表格统一 | 已完成一期 |

## 7. 第六批：系统配置

目标：管理表格、表单和危险操作统一。

| 模块 | 文件 | 规范目标 | 优先级 |
|------|------|----------|--------|
| 用户和权限管理 | `ConfigUserContent.tsx` | 标准表单、管理表格、危险按钮统一 | 已完成一期 |
| 系统设定控制 | `ConfigSystemContent.tsx` | 标准设置表单、状态提示统一 | 已完成一期 |

## 8. 每个模块的完成定义

一个模块完成统一 UI 改造，需要满足：

- 页面根使用 `PageShell` 或等价 `bb-page`。
- 标题与工具栏使用统一结构。
- 主操作按钮使用 `bb-btn-primary`，普通操作使用 `bb-btn-secondary`。
- 表格使用 `bb-table` 或等价共享表格组件。
- 数字右对齐，缺失、只读、可编辑、锁定、错误态视觉明确。
- 空态、加载态、错误态使用统一状态块。
- 弹窗使用统一尺寸、标题、内容、页脚结构。
- 无新增随意 hex 色值；新增颜色必须进入设计规范。
- `npm run build` 通过。

## 9. 推荐执行顺序

1. 完成 `OrgProductContent.tsx`、`OrgProductMetricContent.tsx`、`DataDepartmentContent.tsx`、`BudgetSubjectCatalogContent.tsx` 等当前仍在导航中的维护页；旧 `DataProductContent.tsx` 和 `DataAccountContent.tsx` 不得作为维护入口恢复。
2. 完成 `OrgProductMetricContent.tsx` 对产品维度唯一指标号码的统一维护；旧 `ForecastWorkbenchContent.tsx`、`BudgetAssumptionContent.tsx` 不再作为规则配置入口。
3. 完成 `ExpenseActualImportContent.tsx`、`DataSyncManagementContent.tsx` 两个导入同步页。
4. 完成 `PivotTableContent.tsx`、`PivotChartContent.tsx` 两个分析透视页。
5. 完成其余维护和配置页面。
