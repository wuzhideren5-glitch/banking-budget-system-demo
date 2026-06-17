# Department Expense Module Map

本文只描述当前部门费用预算管理模块的前端页面、后端 Interface、service Module 和数据库表关系。旧团队包、旧迁移脚本、旧 BI 科目维护页、旧 `control_item_*` 口径和旧费用框架主数据副本只作为 `archive/` 追溯材料，不是当前开发入口。

## Navigation

当前导航来源是 `apps/web/src/app/workspaceCatalog.tsx`，部门费用预算管理模块只包含以下页面：

| Workspace label | Frontend page Module | Frontend domain client/model |
| --- | --- | --- |
| 部门科目维护 | `DataDepartmentContent.tsx` | `deptCatalogViewModel.ts` |
| 部门预算科目维护 | `BudgetSubjectCatalogContent.tsx` | `budgetSubjectCatalogViewModel.ts` |
| BI映射维护 | `BiMappingContent.tsx`, `BiAiSubjectMappingTab.tsx`, `ManageDeptOwnerMappingTab.tsx` | `biMappingApi.ts`, `biMappingViewModel.ts`; BI部门维护同时通过 `masterDataApi.ts` 读取当前部门树 |
| 预算录入 | `ExpenseBudgetEntryContent.tsx` | `expenseBudgetEntryApi.ts`, `expenseBudgetEntryUnits.ts` |
| 费用执行明细导入 | `ExpenseActualImportContent.tsx` | `expenseActualImportApi.ts`, `expenseActualImportViewModel.ts` |
| 费用预测逻辑配置 | `ExpenseForecastRuleContent.tsx` | `expenseForecastApi.ts` |
| 部门费用预测 | `ExpenseForecastContent.tsx`, `ExpenseForecastSubjectPicker.tsx`, `ExpenseForecastSubjectCompileTable.tsx`, `ExpenseForecastScopeCompileTable.tsx`, `ExpenseForecastImportDialog.tsx`, `ExpenseForecastExportFieldsDialog.tsx` | `expenseForecastApi.ts`, `expenseForecastViewModel.ts` |
| 费用预算执行报表 | `ExpenseBudgetExecutionContent.tsx`, `ExpenseBudgetExecutionControls.tsx`, `ExpenseBudgetExecutionFilterControls.tsx`, `ExpenseBudgetExecutionTreeReport.tsx`, `ExpenseBudgetExecutionMetricTable.tsx`, `ExpenseBudgetExecutionMatrixTable.tsx` | `expenseBudgetExecutionApi.ts`, `expenseBudgetExecutionViewModel.ts` |
| 业务支出成本收入比实际导入 | `BusinessCostIncomeRatioActualImportContent.tsx` | `businessCostIncomeApi.ts`, `businessCostIncomeAdminViewModel.ts` |
| 业务支出成本收入比维护 | `BusinessCostIncomeRatioAdminContent.tsx` | `businessCostIncomeApi.ts`, `masterDataApi.ts` |
| 投入产出专题概览 | `InputOutputTopicOverviewContent.tsx` | `businessCostIncomeApi.ts` |

## API And Service Map

| Capability | HTTP Interface | Backend Module owner | Current tables |
| --- | --- | --- | --- |
| 部门科目维护 | `/api/dept-accounts*`, `/api/dept-tree/export` | `routers/dept_catalog.py`, `services/dept_catalog.py`, `services/department_expense_contracts.py` | `common.db.dept_account` |
| 部门预算科目维护 | `/api/budget-subject-catalog*` | `routers/budget_subject_catalog.py`, `services/budget_subject_catalog.py`, `services/department_expense_contracts.py` | `common.db.budget_subject_catalog` |
| BI-AI 科目维护 | `/api/bi-ai-subject-mapping/*` | `routers/bi_subject_mapping.py`, `services/bi_ai_subject_mapping.py` | `common.db.bi_ai_subject_mapping` |
| BI部门维护 | `/api/manage-dept-owner-mapping/*` | `routers/bi_department_mapping.py`, `services/bi_department_mapping.py` | `common.db.manage_dept_owner_mapping`, `common.db.dept_account` |
| 预算录入 | `/api/expense-budget-entry/*` | `routers/expense_budget_entry.py`, `services/expense_budget_entry_parser.py`, `services/expense_budget_entry_apply.py`, `services/expense_budget_entry_store.py`, `services/expense_budget_entry_export.py`, `services/expense_budget_entry_units.py`, `services/expense_budget_entry_amounts.py` | `common.db.expense_budget_entry_batch`, `common.db.expense_budget_entry`, `common.db.dept_account`, `common.db.budget_subject_catalog`, `common.db.expense_framework_*` |
| 费用执行明细导入 | `/api/expense-actual-import/*` | `routers/expense_actual_import.py`, `services/expense_actual_import_schema.py`, `services/expense_actual_import_context.py`, `services/expense_actual_import_parser.py`, `services/expense_actual_import_apply.py`, `services/expense_actual_import_batches.py` | `common.db.expense_actual_import_batch`, `common.db.expense_actual_detail_raw`, `common.db.bi_ai_subject_mapping`, `common.db.manage_dept_owner_mapping`, `common.db.budget_subject_catalog`, `common.db.dept_account` |
| 费用预测逻辑配置 | `/api/expense-forecast/rules*`, `/api/expense-forecast/recalculate`, `/api/expense-forecast/rules/simulate` | `routers/expense_forecast_rules.py`, `services/expense_forecast_rule_import.py`, `services/expense_forecast_rule_import_workflow.py`, `services/expense_forecast_rule_commands.py`, `services/expense_forecast_rule_copy.py`, `services/expense_forecast_rule_detail.py`, `services/expense_forecast_rule_read_model.py`, `services/expense_forecast_rule_save.py`, `services/expense_forecast_rule_simulation.py`, `services/expense_forecast_rule_calculation.py`, `services/expense_forecast_metric_sources.py`, `services/expense_forecast_recalculation.py`, `services/expense_forecast_recalculation_commands.py` | `common.db.expense_forecast_rule`, `common.db.expense_forecast_rule_param`, `common.db.expense_forecast_rule_variable`, `common.db.expense_forecast_calc_result`, `common.db.expense_forecast_override` |
| 部门费用预测 | `/api/expense-forecast/*` | `routers/expense_forecast.py`, `services/expense_forecast_schema.py`, `services/expense_forecast_data_context.py`, `services/expense_forecast_view_read_model.py`, `services/expense_forecast_view_model.py`, `services/expense_forecast_cell_commands.py`, `services/expense_forecast_write_commands.py`, `services/expense_forecast_import_plan.py`, `services/expense_forecast_import_preview.py`, `services/expense_forecast_import_apply.py`, `services/expense_forecast_export_plan.py`, `services/expense_forecast_export.py`, `services/expense_forecast_override_commands.py`, `services/expense_forecast_trace.py` | `common.db.expense_forecast_entry`, `common.db.expense_forecast_annual_entry`, `common.db.expense_forecast_calc_result`, `common.db.expense_forecast_override`, `common.db.expense_actual_detail_raw`, `common.db.dept_account`, `common.db.budget_subject_catalog` |
| 费用预算执行报表 | `/api/expense-budget-execution*` | `routers/expense_budget_execution.py`, `services/expense_budget_execution_report_resolver.py`, `services/expense_budget_execution_modes.py`, `services/expense_budget_execution_framework.py`, `services/expense_budget_execution_framework_sync.py`, `services/expense_budget_execution_master_sync.py`, `services/expense_budget_execution_status.py`, `services/expense_budget_execution_subject_catalog.py`, `services/expense_budget_execution_actuals.py`, `services/expense_budget_execution_budget_source.py`, `services/expense_budget_execution_report_context.py`, `services/expense_budget_execution_query_report.py`, `services/expense_budget_execution_template_report.py`, `services/expense_budget_execution_subject_report.py`, `services/expense_budget_execution_monthly_report.py`, `services/expense_budget_execution_export.py` | `common.db.dept_account`, `common.db.budget_subject_catalog`, `common.db.expense_budget_entry`, `common.db.expense_actual_detail_raw`, `common.db.expense_actual_import_batch`, `common.db.expense_framework_budget_department`, `common.db.expense_framework_product_department`, `common.db.expense_framework_subject`, `common.db.expense_sync_meta`, yearly `budget_summary` |
| 业务支出成本收入比维护/分析/实际导入 | `/api/business-cost-income-ratio/*` | `routers/business_cost_income_ratio.py`, `services/business_cost_income_ratio.py`, `services/business_cost_income_commands.py`, `services/business_cost_income_import.py`, `db_bootstrap/business_cost_income.py` | yearly `business_cost_income_indicator`, `business_cost_income_item`, `business_cost_income_source_mapping`, `business_cost_income_value` |
| 投入产出专题概览 | `/api/input-output-topic-overview/*` | `routers/input_output_topic_overview.py`, `services/input_output_topic_overview.py` | yearly `business_cost_income_*`, yearly `budget_summary` |

## Database Ownership Rules

- `dept_account` 是当前部门科目主数据，只维护事业群和费用归属部门两级树。费用发生部门留在费用框架快照或导入明细中，不反写成第三套部门主数据。
- `budget_subject_catalog` 是当前部门预算科目主数据，维护五级预算科目树。费用预测和费用预算执行报表只能消费它，不能用 `expense_framework_subject` 代替当前主数据。
- `bi_ai_subject_mapping` 是当前 BI-AI 科目映射表。旧 BI 科目维护页和旧 `control_item_subject_mapping` 不再是当前 Interface。
- `biMappingApi.ts` 和 `biMappingViewModel.ts` 是当前 BI 映射前端 Interface。`biMappingViewModel.ts` 统一承载 BI-AI 科目映射表列定义、搜索过滤、BI部门维护主体/事业群/费用归属部门分组、部门搜索过滤、其他选项判断、归口管理部门排序和映射表业务分组。旧 `controlItemMappingApi.ts`、`controlItemMappingViewModel.ts` 和 `ControlItemMappingContent.tsx` 名称已经退休，不得作为新代码或新文档入口恢复。
- `manage_dept_owner_mapping` 是 BI部门维护的归口管理部门和费用归属部门映射表。费用归属部门允许选择“其他”并手工填写，页面顺序为费用归属部门在前、归口管理部门在后。
- `expense_budget_entry_batch` 和 `expense_budget_entry` 是部门费用预算管理模块的预算录入私有表，承载 shier 0603 的“预算录入”页面、模板下载、上传预览、确认导入、批次删除和已导入预算金额/调整金额维护。费用预算执行报表的“本年预算”列直接读取 `expense_budget_entry` 中 `owner_matched=1` 且 `subject_matched=1` 的年度数据，金额取 `amount + adjustment_amount`，再按当前部门和预算科目体系聚合到主体、事业群和费用归属部门；它不恢复费用执行明细导入里的“本年预算导入”切换口径。
- `expense_actual_detail_raw` 当前字段为 `bi_ai_source_code`、`bi_ai_source_name`、`manage_department_code`、`owner_name_mapped`、`budget_subject_mapped` 等 BI-AI 和部门费用口径字段。旧 `control_item_*` 物理字段必须继续由 bootstrap 合同拒绝。
- 费用预算执行报表的“本年实际”和“上年同期”读取 `expense_actual_detail_raw` 当前有效匹配行，而不是只读取最近批次；owner 明细口径要求 `owner_matched=1` 且 `subject_matched=1`，科目汇总口径要求 `subject_matched=1`。月报格式响应会返回 `consistency_warnings`，对费用统计表、业务费用表、IT费用表、日常费用表中的同类指标做跨表一致性预警。
- `expense_forecast_rule.manual_recalc_enabled` 只控制用户在费用预测逻辑配置页显式点击重算时是否纳入计算；保存规则、单元格保存和导入应用触发的自动刷新按 `auto_refresh_enabled` 上游判断后进入自动重算口径，重算 workflow 内只要求规则处于启用状态。
- 费用预测按事业群 owner 分段视图只能在 `expense_forecast_view_read_model.py` 中复用一次预算科目树/费用归属部门/当前实际截止月静态上下文；动态上下文按 owner 列表一次加载，再按 owner 分段消费，避免新旧主数据口径在 owner 循环内重复散落。
- 费用预测按预算科目 owner 视图复用静态上下文中的当前实际截止月；归口部门过滤后只重新加载 owner 动态数据，不能重新穿透年度级 cutoff Adapter。
- `expense_framework_budget_department`、`expense_framework_product_department`、`expense_framework_subject` 是费用整体框架同步快照和状态来源，不是当前部门或预算科目维护表。
- `expense_forecast_*` 表归部门费用预测私有流程所有。写入统一通过费用预测 service Module，不从页面直接拼 SQL。
- `business_cost_income_*` 表位于年度库，归业务支出成本收入比维护、实际导入、分析和投入产出专题复用。它们不属于 `common.db` 主数据；维护页评估指标选择依赖机构及产品指标已确认并同步到 `common.db.data_account_metric_node` 的 `*.05.02` 业务支出评估指标树。

## Current Live Inventory

以 2026-06-05 当前 `var/data/*.db` 为准，详细行数和退休表检查见 `docs/development/current-database-inventory.md`。

| Database | Tables used by this module |
| --- | --- |
| `var/data/common.db` | `dept_account`, `budget_subject_catalog`, `bi_ai_subject_mapping`, `manage_dept_owner_mapping`, `expense_budget_entry_batch`, `expense_budget_entry`, `expense_actual_import_batch`, `expense_actual_detail_raw`, `expense_framework_budget_department`, `expense_framework_product_department`, `expense_framework_subject`, `expense_sync_meta`, `expense_forecast_rule`, `expense_forecast_rule_param`, `expense_forecast_rule_variable`, `expense_forecast_entry`, `expense_forecast_annual_entry`, `expense_forecast_calc_result`, `expense_forecast_override` |
| `var/data/budget_2025.db` and `var/data/budget_2026.db` | `budget_summary`, `business_cost_income_indicator`, `business_cost_income_item`, `business_cost_income_source_mapping`, `business_cost_income_value` |
| `var/data/compare.db` | Not a write owner for department expense. It may be read by analysis surfaces outside this module. |

## Extension Rules

- Add a department-expense page only through `workspaceCatalog.tsx`, a page Module, a frontend domain client/model, a router, and a service owner recorded in this document.
- Do not add raw `/api/*` calls inside page components. Put DTO/API code in `apps/web/src/lib/*Api.ts` and display shaping in `apps/web/src/lib/*ViewModel.ts`.
- Do not create a second copy of department, budget subject, BI-AI mapping, actual-import, forecast, execution-report, or business-cost-income tables.
- When changing `biMappingViewModel.ts`, run `npm run test:view-model` from the repo root, or `npm run test:view-model` from `apps/web/`, to verify BI-AI search and BI部门维护 grouping rules without starting the full browser journey.
- When a table contract changes, update this file, `current-system-map.md`, `current-database-inventory.md`, `docs/product/Banking_Budget_Files.md`, and the relevant bootstrap contract/test together.
