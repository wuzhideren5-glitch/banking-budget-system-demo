# Current Database Inventory

Last verified: 2026-06-10

本文记录当前 `var/data/*.db` 的运行库事实，用于后续开发判断表是否属于当前 Module、是否只是空的私有状态、以及哪些退休表不得恢复。行数是本机当前快照，不代表业务完整性验收结果；表归属和退休边界以 `CONTEXT.md`、`docs/development/current-system-map.md` 和 Database PDD 为准。

## Database Files

| Database | Current role | Table count | Current-use rule |
| --- | --- | ---: | --- |
| `var/data/common.db` | 主数据、用户/会话、审计、费用闭环私有状态、智能报告/PPT 配置、机构产品指标树配置 | 46 | 当前主数据和配置事实源。不得把历史 release DB 或 archive DB 当作当前库。 |
| `var/data/budget_2025.db` | 2025 年度库 | 9 | 当前可保留年度库；事实和派生读模型为空不等于表退休。 |
| `var/data/budget_2026.db` | 2026 年度预算事实和当前年度读模型 | 9 | 当前预算事实、汇总和透视派生读模型的主要年度库。 |
| `var/data/compare.db` | 多年度对比读模型 | 4 | 对比透视和 Agent compare 读模型使用；不写主数据。 |

## Common DB Table Groups

| Module / private state | Tables | Current row counts |
| --- | --- | --- |
| 机构产品指标运行引用 | `data_account`, `data_account_metric_binding`, `data_account_metric_node` | 11212, 11212, 15344 |
| 部门/预算科目主数据 | `dept_account`, `budget_subject_catalog` | 37, 59 |
| 预算展示报表配置 | `budget_output_display_item` | 1276 |
| BI 映射维护 | `bi_ai_subject_mapping`, `manage_dept_owner_mapping` | 66, 31 |
| 费用执行明细导入 | `expense_actual_import_batch`, `expense_actual_detail_raw` | 2, 718 |
| 部门预算导入 | `expense_budget_entry_batch`, `expense_budget_entry` | 1, 355 |
| 费用预测表/规则 | `expense_forecast_entry`, `expense_forecast_annual_entry`, `expense_forecast_calc_result`, `expense_forecast_rule`, `expense_forecast_rule_param`, `expense_forecast_rule_variable`, `expense_forecast_override` | 1248, 312, 1248, 156, 936, 0, 0 |
| 费用预算执行框架快照 | `expense_framework_budget_department`, `expense_framework_product_department`, `expense_framework_subject`, `expense_sync_meta` | 57, 57, 58, 2 |
| 机构产品指标树体系 | `org_product_metric_table_catalog`, `org_product_metric_table`, `org_product_data_entry_draft`, `org_product_data_entry_snapshot`, `org_product_data_entry_snapshot_v2`, `org_product_output_snapshot_v1`, `org_product_tree_snapshot` | 12, 44, 0, 0, 0, 0, 1 |
| 智能报告/PPT | `smart_report_template`, `smart_report_template_variable`, `smart_report_instance`, `smart_report_job`, `smart_report_blueprint`, `smart_report_calc_metric`, `smart_ppt_scene`, `smart_ppt_chart_config`, `smart_ppt_instance` | 5, 6, 11, 12, 0, 0, 5, 5, 9 |
| 智能预算模拟 | `intelligent_budget_tasks` | 2 |
| 系统配置/用户/会话/审计 | `databases`, `edit_show_version`, `period`, `users`, `user_sessions`, `operation_log`, `feishu_user_binding` | 3, 4, 180, 7, 372, 3131, 2 |

`product_type` 已退出物理表清单，也不再保留同名运行视图；当前运行产品清单由服务直接从 `org_product_tree_snapshot.payload_json` 展开，供预算展示和批处理读取产品名称/层级，不再作为主数据维护表。

`data_account` 当前 11212 条运行引用编码必须全部由 `org_product_metric_table` 中 `MANUAL_CONFIRMED` 的机构及产品指标引用；它不是配置入口，也不再作为前端独立菜单展示。库存校验和启动链路都会拒绝孤立运行编码，不再把 `data_account`、预算事实或派生读模型反向写回机构及产品指标主表。预算事实、预算展示配置、业务支出成本收入比私有表中的 `data_acct_code`，以及预算汇总/透视/对比派生读模型的 `data_code_name` 编码部分，也必须指向同一批机构及产品指标确认主键。旧 `CORP.*` 全行运行编码已归一到 `AA.*` 微众银行实体编码，不再作为机构及产品指标实体保留。05 费用指标中 `AA.05.01` 业务及管理费和 `AA.05.02` 业务支出评估的规范节点由库存门禁校验，不得缺失或回退到旧保护状态。

空表不自动删除。`expense_forecast_rule_variable`、`expense_forecast_override`、`smart_report_blueprint`、`smart_report_calc_metric` 当前为 0 行，但它们属于可见 Module 的私有状态或可选功能状态；删除前必须先确认对应页面/接口整体退休。

`expense_actual_detail_raw` 已按当前 BI-AI 源字段合同验证：物理列为 `bi_ai_source_code`、`bi_ai_source_name`、`manage_department_code`，不再保留旧 `control_item_*` 字段。2026-06-03 字段重命名前已备份 `var/data/common.db` 到 `var/data/backups/schema_contract_20260603/common_before_bi_ai_source_column_rename.db`；重命名后仍为 718 条明细、2 个批次。

## Annual DB Tables

| Database | Table | Rows | Current owner |
| --- | --- | ---: | --- |
| `budget_2025.db` | `version` | 3 | 年度版本配置 |
| `budget_2025.db` | `budget_data` | 0 | 年度预算事实 |
| `budget_2025.db` | `budget_summary` | 0 | 年度预算汇总派生读模型 |
| `budget_2025.db` | `budget_pivot_aggregate` | 0 | 当前年度透视派生读模型 |
| `budget_2025.db` | `business_cost_income_item` | 554 | 业务支出成本收入比私有配置 |
| `budget_2025.db` | `business_cost_income_indicator` | 260 | 业务支出成本收入比私有配置 |
| `budget_2025.db` | `business_cost_income_source_mapping` | 108 | 业务支出成本收入比来源映射 |
| `budget_2025.db` | `business_cost_income_value` | 0 | 业务支出成本收入比月度值 |
| `budget_2025.db` | `settings` | 4 | 年度库设置 |
| `budget_2026.db` | `version` | 2 | 年度版本配置 |
| `budget_2026.db` | `budget_data` | 138180 | 年度预算事实 |
| `budget_2026.db` | `budget_summary` | 11208 | 年度预算汇总派生读模型 |
| `budget_2026.db` | `budget_pivot_aggregate` | 16812 | 当前年度透视派生读模型 |
| `budget_2026.db` | `business_cost_income_item` | 554 | 业务支出成本收入比私有配置 |
| `budget_2026.db` | `business_cost_income_indicator` | 260 | 业务支出成本收入比私有配置 |
| `budget_2026.db` | `business_cost_income_source_mapping` | 108 | 业务支出成本收入比来源映射 |
| `budget_2026.db` | `business_cost_income_value` | 0 | 业务支出成本收入比月度值 |
| `budget_2026.db` | `settings` | 4 | 年度库设置 |

## Compare DB Tables

| Table | Rows | Current owner |
| --- | ---: | --- |
| `compare_budget_summary` | 133464 | 多年度对比汇总 read model |
| `compare_pivot_aggregate` | 198208 | 多年度对比透视派生读模型 |
| `compare_sync_job_log` | 543 | 对比同步运行记录 |
| `settings` | 1 | 对比库设置 |

## Retired Table Check

2026-06-10 检查结果：`budget_2025.db`、`budget_2026.db`、`common.db`、`compare.db` 均未发现当前退休表。

当前退休表清单由 `apps/api/app/db_bootstrap/retired_deletion.py` 维护，包括：

- `report_account`, `report_data_mapping`, `report_accounts` 相关旧报告科目入口。
- `driver_category`, `driver_indicator`, `driver_product`, `driver_account_mapping` 等旧预算驱动页面表。
- `control_item_subject_mapping` 旧 BI 科目维护表。
- `forecast_workbench_layout`, `forecast_line_binding`, `scenario_catalog`, `assumption_parameter`, `assumption_value`, `assumption_rule_template` 等旧预测工作台/假设参数表。
- `chart_template`, `smart_report_definition`, `pivot_aggregate_rule`, `dept_product_mapping`, `dept_name_alias`, `expense_execution_monthly`, `product_budget_*`, `product_type` 物理维护表等已退休表。

若旧库或外部导入包重新出现这些表，处理方式是运行当前删除脚本或按当前 Module 重建数据，不得作为兼容输入继续读取：

```bash
apps/api/.venv/bin/python apps/api/scripts/delete_retired_tables.py --dry-run
apps/api/.venv/bin/python apps/api/scripts/delete_retired_tables.py
```

## Verification Commands

```bash
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
```

该脚本不仅打印当前 `var/data/*.db` 表和行数，还会执行十二类 gate：

- `retired_tables=none`：确认当前运行库没有重新出现退休表。
- `inventory_doc=ok`：确认每一张当前运行表都能在本文档中找到；新增当前表时必须同步更新本文，否则脚本失败。
- `inventory_owner_doc=ok`：确认每一张当前运行表都在本文的 Module / owner 表格中出现；只在散文或退休表清单里提到表名不算完成数据库关系维护。
- `metric_identity_contract=ok`：确认机构产品指标运行引用表的物理约束和当前数据仍满足产品前缀指标身份合同：`data_account.data_acct_code = data_account_metric_binding.metric_node_code`，`scope_code` 只能由 `metric_node_code` 产品前缀派生，`data_account_metric_node.product_code` / `local_metric_code` / `level` 必须由 `node_code` 派生，旧后缀式 `metric_node_code + scope_code` 身份不得回流。
- `org_product_metric_guard=ok`：确认机构及产品指标表 payload 不再含旧保护状态，运行引用和预算事实均直接引用机构及产品指标主键。
- `org_product_metric_runtime_refs=ok`：确认机构及产品指标表中每条已填写的 `metric_node_code` / `data_acct_code` 都是一套同码产品前缀主键，并且已经同步落到 `data_account`、`data_account_metric_node`、`data_account_metric_binding` 三张运行表。
- `business_data_account_refs=ok`：确认预算事实、预算展示配置和业务支出成本收入比私有表的 `data_acct_code` 均指向机构及产品指标已确认主键。
- `derived_read_model_data_code_name_refs=ok`：确认预算汇总、透视和多年度对比派生读模型的 `data_code_name` 编码部分均指向机构及产品指标已确认主键，且没有旧 `CORP.*` 编码。
- `legacy_second_segment_99=ok`：确认机构及产品指标 payload、机构产品指标运行引用、预算事实、成本收入比私有表和预算/对比读模型中均没有第二段为 `99` 的旧保护编码；普通叶子末段 `99` 不受影响。
- `canonical_expense_metric_tree=ok`：确认 `AA.05.01` 业务及管理费和 `AA.05.02` 业务支出评估的规范费用指标节点已经进入当前运行树，且旧 `CORP.05.01/05.02` 节点没有回流。
- `org_product_runtime_catalog=ok`：确认旧 `product_type` 对象不存在，并且可以从 `org_product_tree_snapshot` 展开非空运行产品清单。
- `retired_workspace_menus=ok`：确认前端规则配置台没有恢复 `data-account` / “数据科目运行表” / “数据科目投影”等已退休配置入口，旧 `DataAccount*` / `OrgProductPanpan99ExpenseContent` / `dataAccountViewModel` 文件没有回流，同时确认前端 client 和 FastAPI 入口没有恢复 `/api/data-accounts*`、旧 `panpan99-page` 或旧 `data-account-projection` 外部接口。
