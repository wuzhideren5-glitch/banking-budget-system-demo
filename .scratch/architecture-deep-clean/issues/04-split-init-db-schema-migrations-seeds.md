# 拆分 init_db.py 的 schema、contract check、seed 和 retired cleanup

Status: completed
Type: AFK
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

把初始化路径从单个混合 Module 拆成清晰的运行入口：schema bootstrap 只负责当前表结构，contract check 只负责拒绝旧物理合同，seed data 只负责当前必要种子，retired-table cleanup 只负责删除已下线表。启动系统时仍能幂等创建和校验运行库，但维护者不再需要在一个巨大文件里理解所有历史。

## Acceptance criteria

- [x] 启动时仍能幂等准备运行数据库。
- [x] 当前 schema、当前合同校验、默认种子、退休表删除逻辑分属不同 Module。
- [x] 已退休旧口径不再作为兼容输入；启动校验发现旧字段/旧表时失败或进入统一删除脚本。
- [x] 当前主线建表不依赖历史补丁顺序才能理解。
- [x] 迁移执行有最小回归测试或可重复的验证命令。
- [x] PDD 中的表结构与 schema bootstrap 对齐。

## Result

- `apps/api/app/db_bootstrap/schemas.py` owns current SQLite schema constants.
- `apps/api/app/db_bootstrap/current_contracts.py` owns current-contract checks for existing DB files.
- `apps/api/app/db_bootstrap/seeds.py` owns current default seed routines.
- `apps/api/app/db_bootstrap/retired_deletion.py` owns retired-table cleanup; the old standalone `legacy.py` module has been deleted.
- `apps/api/app/db_bootstrap/runner.py` owns startup registry synchronization that is not schema definition.
- `apps/api/app/init_db.py` now composes those modules and keeps the historical entrypoint import-compatible.

## Verification

- `python -m py_compile app/db_bootstrap/retired_deletion.py app/db_bootstrap/current_contracts.py app/db_bootstrap/runner.py app/db_bootstrap/schemas.py app/db_bootstrap/seeds.py app/init_db.py test_db_bootstrap_runner.py test_db_bootstrap_current_contracts.py test_db_bootstrap_seeds.py test_db_bootstrap_schemas.py`
- `python -m unittest test_db_bootstrap_runner test_db_bootstrap_current_contracts test_db_bootstrap_seeds test_db_bootstrap_schemas`

## Blocked by

- `.scratch/architecture-deep-clean/issues/01-database-table-ownership-inventory.md`
- `.scratch/architecture-deep-clean/issues/02-consolidate-pdd-authority.md`
