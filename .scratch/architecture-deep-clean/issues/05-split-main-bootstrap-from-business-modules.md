# 拆分 main.py 的启动装配与业务 Module

Status: completed
Type: AFK
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

让应用入口只负责 app bootstrap、middleware、服务实例装配和 router wiring。当前混在入口里的预算版本上下文、公式计算、汇总重建、对比同步、导出任务、引用计数等业务行为，应下沉到具名专业 Module。该 slice 不做 **预算展示报表 read-model 收敛**，只移动职责并保持现有行为。

## Acceptance criteria

- [x] 应用启动、认证中间件、服务实例装配和 router 注册仍正常工作。
- [x] 入口文件不再承载大段业务计算、跨库同步、导出任务或引用计数实现。
- [x] 被下沉的业务行为有明确 Module 名称和小 Interface。
- [x] 现有路由调用保持兼容，外部行为不变。
- [x] 预算展示报表行为保持现状，不在本 issue 中重写 read model。
- [x] 至少覆盖健康检查、会话、汇总重建或对比同步中的关键回归路径。

## Result

- `apps/api/app/services/budget_summary_rebuild.py` owns budget summary projection rebuild.
- `apps/api/app/services/compare_summary_sync.py` owns cross-year compare summary synchronization and its lock.
- `apps/api/app/services/formula_engine.py` owns formula parsing, validation, AST evaluation, and reference normalization.
- `apps/api/app/services/data_account_usage.py` owns data-account row mapping and usage/reference counts.
- `apps/api/app/services/global_refresh_status.py` owns annual/compare refresh-watermark `settings` reads/writes and last-calculation fallback lookup.
- `apps/api/app/main.py` remains the app composition surface for lifespan, middleware, service instances, and router wiring.

## Verification

- `python -m py_compile app/services/data_account_usage.py app/services/formula_engine.py app/services/compare_summary_sync.py app/services/budget_summary_rebuild.py app/services/global_refresh_status.py app/main.py`
- `uv run python -m unittest test_formula_engine test_data_account_usage test_db_bootstrap_runner test_db_bootstrap_current_contracts test_db_bootstrap_seeds test_db_bootstrap_schemas test_budget_summary_rebuild test_compare_summary_sync test_data_account_write`
- `uv run python -m pytest test_global_refresh_status.py test_compare_summary_sync.py test_budget_summary_rebuild.py`

## Blocked by

- `.scratch/architecture-deep-clean/issues/01-database-table-ownership-inventory.md`
- `.scratch/architecture-deep-clean/issues/02-consolidate-pdd-authority.md`
- `.scratch/architecture-deep-clean/issues/04-split-init-db-schema-migrations-seeds.md`
