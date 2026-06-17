# 执行历史表和旧入口删除

Status: completed
Type: HITL
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

在前置清单、PDD 和核心 Module 收敛完成后，执行历史表、旧入口、旧 adapter 的最终删除决策。目标是让已经退出主线的产品预算工作台、旧报告主事实依赖、旧驱动身份定义和历史兼容字段不再污染正式业务 Module，同时保留必要备份和可回滚迁移路径。

## Acceptance criteria

- [x] 每个删除项都有 deletion test 结论、当前引用检查和数据迁移/备份方案。
- [x] 旧产品预算工作台不再存在 active source、路由或导航入口。
- [x] 新业务不再依赖旧报告科目表定义身份。
- [x] 重复表达数据科目身份的旧驱动或工作台表已删除或纳入退休表清理，不再降级为只读 adapter。
- [x] 删除动作有可执行迁移脚本、回滚说明和验收命令。
- [x] 删除后 PDD、ERD、文件地图和运行库一致。

## Result

- Created executable deletion support:
  - `apps/api/app/db_bootstrap/retired_deletion.py`
  - `apps/api/scripts/delete_retired_tables.py`
  - `apps/api/test_retired_deletion.py`
- Deleted `_codex_write_test` from `var/data/common.db`.
- Confirmed product-budget retired tables are absent from current runtime DB and covered by the deletion script for old local DB copies.
- Deleted `report_account` / `report_data_mapping` from current schema and runtime DB; no active adapter remains.
- Superseded 2026-06-01: old driver and assumption tables were later retired from active schema/runtime; product-budget workbench tables remain only in retired-table cleanup for old DB copies.
- Wrote deletion evidence and rollback details to `.scratch/architecture-deep-clean/DELETION_REPORT.md`.

## Backup

- `var/data/backups/common_before_retired_delete_20260519T041913Z.db`

## Verification

- `python -m py_compile app/db_bootstrap/retired_deletion.py scripts/delete_retired_tables.py test_retired_deletion.py`
- `python -m unittest test_retired_deletion`
- `python apps/api/scripts/delete_retired_tables.py --dry-run`
- `python apps/api/scripts/delete_retired_tables.py`
- SQLite check confirmed `_codex_write_test` is absent after execution.

## Blocked by

- `.scratch/architecture-deep-clean/issues/01-database-table-ownership-inventory.md`
- `.scratch/architecture-deep-clean/issues/02-consolidate-pdd-authority.md`
- `.scratch/architecture-deep-clean/issues/03-deepen-data-account-maintenance-module.md`
- `.scratch/architecture-deep-clean/issues/04-split-init-db-schema-migrations-seeds.md`
- `.scratch/architecture-deep-clean/issues/05-split-main-bootstrap-from-business-modules.md`
