# Architecture Deletion Report

Date: 2026-05-22

## Executed deletions

| Item | Deletion test | Action | Backup / rollback |
| --- | --- | --- | --- |
| `_codex_write_test` | No active source references; only listed as runtime smoke-test artifact in table ownership inventory; runtime row count was 0. | Deleted from `var/data/common.db` via `apps/api/scripts/delete_retired_tables.py`. | Backup: `var/data/backups/common_before_retired_delete_20260519T041913Z.db`. Restore by replacing `var/data/common.db` with that backup. |
| `report_data_mapping`, `report_account` | No active router SQL dependency found; report axes now resolve through `data_account_metric_node` / `data_account_metric_binding`; rows were historical compatibility data only. | Deleted from current schema and from `var/data/common.db` via `apps/api/scripts/delete_retired_tables.py`. | Backup: see latest `var/data/backups/common_before_retired_delete_*.db`. Restore by replacing `var/data/common.db` with that backup. |
| `driver_category`, `driver_indicator`, `driver_product`, `driver_account_mapping` | Old budget driver page is no longer in navigation/work area; simulation pages only need baseline/result/export and now read standard metric bindings instead of `driver_*`. | Removed from current schema, removed seed script/path, and deleted from `var/data/common.db` via `apps/api/scripts/delete_retired_tables.py`. | Backup: `var/data/backups/common_before_retired_delete_20260519T055028Z.db`. Restore by replacing `var/data/common.db` with that backup. |
| `forecast_workbench_layout`, `forecast_line_binding`, `scenario_catalog`, `assumption_parameter`, `assumption_value`, `assumption_rule_template` | Forecast workbench and assumption pages were hidden from navigation and only preserved a second prediction configuration language. Deleting them removes complexity instead of moving it to active callers. | Removed frontend hidden pages, WorkArea cases, backend routers, DTOs, init_db create/seed logic, and runtime tables via `apps/api/scripts/delete_retired_tables.py`. | Backup: `var/data/backups/common_before_retired_delete_20260519T062016Z.db`. Restore by replacing `var/data/common.db` with that backup. |
| `UISystemPrototypeContent`, `TabViews`, `ProductSelectorDialog`, `treeEditRules`, `ImageWithFallback` | No current navigation or source import dependency; UI prototype was only reachable through hidden dev query string. | Deleted the hidden prototype path and unused frontend files. | Source rollback only; no database backup required. |
| `/api/fee-actual/*` legacy import route | Current visible费用执行明细导入 page calls `/api/expense-actual-import/*`; the old route created a second import Interface for the same business area. | Deleted `app/fee_actual_import.py`, `routers/fee_actual_import.py`, `main.py` include, and permission branch. | Source rollback only; no database backup required. |
| `chart_template` | Empty runtime table; no active source dependency; chart pages use `/api/chart/*` request payloads and `smart_ppt_chart_config` rather than a global chart-template table. | Removed from current schema and deleted from `var/data/common.db` via `apps/api/scripts/delete_retired_tables.py`. | Backup: `var/data/backups/common_before_retired_delete_20260519T063701Z.db`. Restore by replacing `var/data/common.db` with that backup. |
| Narrow unused public routes | No frontend caller found for `/api/budget-input/cell`, `/api/agent/kb/*`, `/api/smart-ppt/scenes/{scene_id}`, or `/api/smart-ppt/template-studio/binding-suggestions`. | Deleted those public routes; kept active batch budget input, expense forecast rule configuration routes, internal Agent knowledge-base service, and Smart PPT dynamic download/chart-block routes. | Source rollback only; no database backup required. |
| `product_budget_component*` | No active API route, active frontend component, or runtime table found. | No runtime table existed; deletion script keeps DROP coverage for old local DB files. | Same script backs up before deleting if any old table exists in another local DB. |
| `smart_report_definition` + `smart_report_instance.report_id` | `smart_report_definition` had 0 rows, `smart_report_instance.report_id` was unused, and active visible flows use template/blueprint/instance APIs. | `smart_report_definition` is dropped as a retired table; old `smart_report_instance.report_id` is no longer rebuilt away and is rejected by the current Smart Report schema contract. | Runtime snapshots are under `var/data/backups/`; restore by replacing `var/data/common.db` with the chosen backup. |
| `pivot_aggregate_rule` | The table had 6 seeded rows, but no active query/export/chart route reads it; aggregate grain and field rules are code-owned constants in the multidimensional Module. | Removed schema and ensure/seed writes, moved deletion into the unified retired-table Module, and verified it is absent after copied-DB bootstrap and current runtime bootstrap. | Current post-clean snapshot: `var/data/backups/common_before_arch_slim_20260522T083021Z.db`; older pre-clean common backups remain under `var/data/backups/` if full table rollback is required. |
| `resources/download_template/report_acct_temp.xlsx` | The `report_account` surface is retired and no active template download caller uses this stem. | Deleted from the active download-template directory. | Restore from source control or archived delivery package if an old compatibility import is intentionally reintroduced. |
| `budget_report_display_item` | Budget display rows now belong only to `budget_output_display_item`; the old report-display table must not be migrated into the current display config. | Added to retired-table deletion; current bootstrap no longer upgrades `budget_report_display_item` or `report_view`. | Restore only from a database backup, then manually transform into `budget_output_display_item` if an explicit recovery plan requires it. |
| `expense_execution_monthly` | Current费用执行实际 is imported as raw detail rows in `expense_actual_detail_raw`; the monthly snapshot had 0 runtime rows and only preserved an old DataSync upload/fallback path. | Removed from current schema, removed actual-sync UI/API, and added to retired-table deletion so current bootstrap drops it from runtime DBs. | Restore only from a database backup, then reimport through **费用执行明细导入** if those amounts are still valid current evidence. |
| `control_item_subject_mapping` | BI科目维护已删除，BI-AI科目映射表是唯一 BI 科目类维护表；费用执行明细导入可用显式预算科目和 `bi_ai_subject_mapping` 完成匹配，旧管控口径到预算科目的隐藏兜底不再保留。 | Removed from current schema/context/parser/test contracts and added to retired-table deletion so current bootstrap drops it from runtime DBs. | Restore only from a database backup, then convert valid mappings into `bi_ai_subject_mapping` or explicit预算科目数据后再导入。 |
| `dept_name_alias` | 旧部门名称不应继续作为未来费用执行明细导入的兼容别名；当前部门改名通过费用私有表引用同步完成。 | Removed the remaining `expense_actual_import_context.py` read path and context test dependency; current import context now reads only current departments, budget subjects, BI-AI 科目映射 and BI部门归属映射. The retired-table deletion module still drops the old table when found. | Restore only from a database backup, then convert valid owner mappings into current `manage_dept_owner_mapping` or current department master data before importing. |

## Deliberately not deleted

| Item | Current reference check | Decision |
| --- | --- | --- |
| `budget_2025.budget_summary` | `budget_2025.budget_data` is empty while summary has rows. | Do not rebuild or delete until source snapshot is understood. |
| `smart_report_blueprint`, `smart_report_calc_metric`, `smart_ppt_*` | These are still reached by visible 智能分析报告 / 智能演示PPT pages. | Keep as Private tables; do not delete by row count. |

## Verification

- `python apps/api/scripts/delete_retired_tables.py --dry-run`
- `python apps/api/scripts/delete_retired_tables.py`
- SQLite verification after execution: `_codex_write_test` is absent from `var/data/common.db`.
- `python -m unittest test_retired_deletion`
- `PYTHONDONTWRITEBYTECODE=1 python -m py_compile apps/api/app/main.py apps/api/app/schemas.py apps/api/app/init_db.py apps/api/app/db_bootstrap/retired_deletion.py apps/api/test_retired_deletion.py`
- `PYTHONDONTWRITEBYTECODE=1 uv run python -m unittest test_retired_deletion test_db_bootstrap_schemas`
- `npm run build`
- SQLite verification after execution: `forecast_workbench_layout`, `forecast_line_binding`, `scenario_catalog`, `assumption_parameter`, `assumption_value`, and `assumption_rule_template` are absent from `var/data/common.db`.
- FastAPI route verification: `/api/forecast-workbench/*` and `/api/budget-assumptions/*` are absent; `/api/budget-simulation/result` remains present.
- SQLite verification after execution: `chart_template` is absent from `var/data/common.db`.
- Source reference verification: no active source references remain for `/api/fee-actual/*`, `UISystemPrototypeContent`, `ProductSelectorDialog`, `TabViews`, `treeEditRules`, `ImageWithFallback`, or `ui/design-system`.
- FastAPI route verification: `/api/budget-input/cell`, `/api/agent/kb/*`, `/api/smart-ppt/scenes/{scene_id}`, and `/api/smart-ppt/template-studio/binding-suggestions` are absent. `/api/expense-forecast/rules/by-id/{rule_id}` remains part of the active fee-forecast rule configuration surface.
- `python -m unittest test_db_bootstrap_schemas test_db_bootstrap_current_contracts`
- `python -m unittest test_retired_deletion test_expense_actual_import_context test_expense_actual_import_parser test_db_bootstrap_schemas`
- `python scripts/full_user_journey.py` -> 41 passed, report `var/test-runs/20260522_162730/full_user_journey_report.json`
- `npm run build`
- `npm --workspace apps/web run e2e` -> 1 passed after closing blocking upload dialogs between page clicks
- SQLite verification after current runtime bootstrap: `pivot_aggregate_rule` absent, `smart_report_definition` absent, smart report template paths no longer point at old `/data/...` roots.
