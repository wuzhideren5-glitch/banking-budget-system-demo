# Database Table Ownership Inventory

Status: current snapshot for architecture cleanup
Date: 2026-06-03
Source: current `var/data/*.db` files and active backend schema Modules.

## Rules

- **Fact**: authoritative source of a business or system fact.
- **Projection**: rebuildable read model or snapshot derived from facts.
- **Adapter**: import, external integration, or historical bridge state. New business Modules must not depend on it as source of truth.
- **Private**: implementation detail of one Module. Other Modules must use that Module Interface, not direct SQL.
- **Retired**: removed from current schema/runtime. It may appear only in deletion scripts, tests, startup rejection checks, history, or archive notes.

## Runtime File Boundary

`var/data/` root is the active runtime data directory. It now contains only:

- active SQLite DBs: `common.db`, `budget_2025.db`, `budget_2026.db`, `compare.db`
- runtime subdirectories: `backups/`, `chart_cache/`, `smart_ppt_template_bindings/`, `smart_report_outputs/`, `smart_report_templates/`, `templates/`

Historical report-account outputs and old backup DB files were moved out of the active root:

- `archive/handover/legacy_report_account_artifacts/`: old report-account cleanup exports, mapping audits, debug JSON, and split-multi-binding workbooks.
- `archive/runtime_snapshots/db_backups_legacy_20260603/`: old May and early-June SQLite backups that had accumulated under `var/data/backups/`, including earlier root-misplaced and retired `var/backups/` consolidation folders.
- `var/data/backups/schema_contract_20260603/`: current-run live DB schema-contract backup retained in the active backup root.

New code must not write backup DBs or historical review workbooks into the `var/data/` root.

## Cross-Database Conclusions

- `common.db` owns current master data, system configuration, audit, private department-expense state, Smart Report/PPT state, and Agent-adjacent configuration state.
- `budget_YYYY.db` owns annual facts and annual projections. Writes to `budget_data` go through **BudgetDataWriter**.
- `compare.db` owns multi-year compare projections and compare sync history.
- `report_account`, `report_data_mapping`, `driver_*`, `control_item_subject_mapping`, `forecast_workbench_*`, `assumption_*`, `smart_report_definition`, `pivot_aggregate_rule`, `dept_name_alias`, and product-budget prototype tables are retired. Do not recreate them as compatibility inputs.
- Empty private tables are not deletion candidates by row count alone when their visible Module is active.

## common.db

| Table | Rows | Owner Module | Type | Dependency policy |
| --- | ---: | --- | --- | --- |
| `data_account` | 10935 | 数据科目维护表 Module | Fact | Use 数据科目写入 Module / master-data Interface. |
| `data_account_metric_node` | 14804 | 标准数据科目指标树 Module | Fact | Official metric identity tree. |
| `data_account_metric_binding` | 10935 | 数据科目维护表 Module | Fact | Official metric-node to data-account binding. |
| `product_type` | 19 | 产品科目 Module | Fact | Product names and hierarchy. |
| `dept_account` | 37 | 部门科目 Module | Fact | Current department owner tree. |
| `budget_subject_catalog` | 58 | 部门费用预算管理模块 | Private fact | Department budget-subject tree. |
| `budget_output_display_item` | 1274 | 预算输出报表 Module | Private display config | Use budget-output Interface; not a metric catalog. |
| `period` | 180 | Calendar/period Module | Fact | Shared read-only period dictionary. |
| `databases` | 3 | System version/catalog Module | Fact | Registry for active `budget_YYYY.db` files. |
| `edit_show_version` | 4 | 展示版本槽位 Module | Fact | Defines editable/show version slots. |
| `users` | 7 | Auth Module | Fact | Use Auth/System Interface. |
| `user_sessions` | 339 | Auth Module | Runtime fact | Runtime sessions only. |
| `operation_log` | 3121 | Audit Module | Fact | Append through audit Module. |
| `feishu_user_binding` | 2 | Feishu adapter | Adapter fact | Private to Feishu integration. |
| `expense_sync_meta` | 2 | 费用 Module | Private adapter fact | Current keys are `framework_import` and `master_apply`; retired `actual_import` must not be exposed as a status input. |
| `expense_framework_budget_department` | 57 | 费用 Module | Private adapter fact | Imported framework snapshot. |
| `expense_framework_product_department` | 57 | 费用 Module | Private adapter fact | Imported framework snapshot; confusing name, not product master data. |
| `expense_framework_subject` | 58 | 费用 Module | Private adapter fact | Imported subject framework snapshot. |
| `expense_actual_import_batch` | 2 | 费用执行明细 Adapter | Private adapter fact | Raw import batch metadata. |
| `expense_actual_detail_raw` | 718 | 费用执行明细 Adapter | Adapter fact | Imported actual rows; not general ledger truth. |
| `bi_ai_subject_mapping` | 68 | BI-AI科目映射 Module | Private mapping fact | Maps external BI level-6 subjects to budget release caliber, fee category, and fee major for actual import; this is the only visible BI subject mapping table. |
| `manage_dept_owner_mapping` | 29 | BI部门维护 Module | Private mapping fact | Maps external manage departments to fee owner departments; the visible UI supports choosing `其他` and manually entering a custom owner department. |
| `expense_forecast_entry` | 1248 | 费用预测表 Module | Private fact | Forecast monthly rows. |
| `expense_forecast_annual_entry` | 312 | 费用预测表 Module | Private fact | Annual business submission / capital advice rows. |
| `expense_forecast_rule` | 156 | 费用预测逻辑配置 Module | Private fact | Current rule header contract. |
| `expense_forecast_rule_param` | 936 | 费用预测逻辑配置 Module | Private fact | Rule parameters, including `metric_expr`. |
| `expense_forecast_rule_variable` | 0 | 费用预测逻辑配置 Module | Private fact | Optional metric-expression variable state. |
| `expense_forecast_calc_result` | 1248 | 费用预测表 Module | Private projection | Rule calculation results. |
| `expense_forecast_override` | 0 | 费用预测表 Module | Private fact | Optional manual override state. |
| `smart_report_template` | 5 | 智能分析报告 Module | Private fact | Report template registry. |
| `smart_report_template_variable` | 6 | 智能分析报告 Module | Private fact | Template variable binding. |
| `smart_report_blueprint` | 0 | 智能分析报告 Module | Private fact | Optional blueprint workflow state. |
| `smart_report_calc_metric` | 0 | 智能分析报告 Module | Private fact | Report-private metric definitions only; not official metric catalog. |
| `smart_report_instance` | 11 | 智能分析报告 Module | Private fact | Generated report instances. |
| `smart_report_job` | 12 | 智能分析报告 Module | Private runtime fact | Generation/refresh jobs. |
| `smart_ppt_scene` | 5 | 智能演示 PPT Module | Private fact | PPT scene definitions. |
| `smart_ppt_chart_config` | 5 | 智能演示 PPT Module | Private fact | PPT chart config; not global chart truth. |
| `smart_ppt_instance` | 9 | 智能演示 PPT Module | Private fact | Generated PPT instances. |

## budget_2025.db

| Table | Rows | Owner Module | Type | Dependency policy |
| --- | ---: | --- | --- | --- |
| `version` | 3 | Budget version Module | Fact | Annual version rows. |
| `settings` | 4 | Budget settings Module | Private fact | Annual refresh watermarks/settings. |
| `budget_data` | 0 | BudgetDataWriter Module | Fact | Current table contract, no detail rows. |
| `budget_summary` | 0 | Budget summary Module | Projection | Empty current projection. |
| `budget_pivot_aggregate` | 0 | Pivot aggregate Module | Projection | Empty current projection. |
| `business_cost_income_item` | 18 | 业务支出成本收入比 Module | Private fact | Default input/output item tree for cost-income analysis. |
| `business_cost_income_indicator` | 6 | 业务支出成本收入比 Module | Private fact | Default indicator configuration for cost-income analysis. |
| `business_cost_income_value` | 0 | 业务支出成本收入比 Module | Private fact | Annual private state. |

## budget_2026.db

| Table | Rows | Owner Module | Type | Dependency policy |
| --- | ---: | --- | --- | --- |
| `version` | 2 | Budget version Module | Fact | Current annual versions. |
| `settings` | 4 | Budget settings Module | Private fact | Annual refresh watermarks/settings. |
| `budget_data` | 158424 | BudgetDataWriter Module | Fact | Primary budget/actual detail fact; writes only through BudgetDataWriter. |
| `budget_summary` | 149778 | Budget summary Module | Projection | Rebuildable read model from `budget_data`. |
| `budget_pivot_aggregate` | 220946 | Pivot aggregate Module | Projection | Rebuildable pivot projection. |
| `business_cost_income_item` | 18 | 业务支出成本收入比 Module | Private fact | Default input/output item tree for cost-income analysis. |
| `business_cost_income_indicator` | 6 | 业务支出成本收入比 Module | Private fact | Default indicator configuration for cost-income analysis. |
| `business_cost_income_value` | 0 | 业务支出成本收入比 Module | Private fact | Active Module private state, empty by current data. |

## compare.db

| Table | Rows | Owner Module | Type | Dependency policy |
| --- | ---: | --- | --- | --- |
| `settings` | 1 | Compare settings Module | Private fact | Compare refresh watermark/settings. |
| `compare_budget_summary` | 149778 | Compare summary Module | Projection/snapshot | Written by compare sync. |
| `compare_pivot_aggregate` | 220946 | Compare pivot aggregate Module | Projection/snapshot | Written by compare sync / aggregate rebuild. |
| `compare_sync_job_log` | 541 | Compare sync Module | Runtime fact | Sync job history. |

## Retired Table Guardrails

The following table families must stay absent from active schema and runtime DBs:

- `report_account`, `report_data_mapping`
- `expense_execution_monthly`
- `control_item_subject_mapping`
- `driver_category`, `driver_indicator`, `driver_product`, `driver_account_mapping`
- `forecast_workbench_layout`, `forecast_line_binding`
- `scenario_catalog`, `assumption_parameter`, `assumption_value`, `assumption_rule_template`
- `product_budget_component`, `product_budget_component_template`, `product_budget_config_package`
- `smart_report_definition`
- `pivot_aggregate_rule`
- `dept_name_alias`

Deletion-test rule: if a future request needs one of these concepts, remodel it through the current owner Module and current tables rather than restoring the retired table.

## Current Cleanup Notes

1. `expense_framework_product_department` is private imported framework snapshot state despite the confusing name. Do not use it as product master data; product hierarchy belongs to `product_type`.
2. `smart_report_calc_metric` may hold report-private calculated metrics, but official metric identity remains in `data_account_metric_node` and `data_account_metric_binding`.
3. `business_cost_income_item` and `business_cost_income_indicator` contain default configuration rows in each current annual DB; `business_cost_income_value` may still be empty while the visible analysis/admin pages remain active.
4. Root-level historical workbooks/debug files have been moved out of `var/data/`; future scripts and services should write backups under `var/data/backups/` and review artifacts under an explicit archive/output path. `var/backups/` is retired and must not be recreated as a parallel backup root.
5. Department-expense reports combine private `common.db` fee tables with annual `budget_summary`; this is a Module read-model contract, not permission for generic modules to query fee private tables directly.
6. 2026-06-03 table-level audit found no unowned runtime table in `common.db`, `budget_2025.db`, `budget_2026.db`, or `compare.db`; retired-table dry run reported no table to delete from current `common.db`.
