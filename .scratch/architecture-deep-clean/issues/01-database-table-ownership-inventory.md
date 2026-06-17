# 建立数据库表归属清单

Status: completed
Type: HITL
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

建立一份当前运行数据库的表归属清单，把每张表归到唯一 Module，并标注它是事实表、投影表、adapter 表还是待删除表。这个清单要覆盖 `common.db`、年度预算库和 `compare.db`，并成为后续 PDD 收敛、Module 加深、历史删除的决策入口。

## Acceptance criteria

- [x] 每张运行表都有唯一 owner Module。
- [x] 每张表都标注为事实表、投影表、adapter 表或待删除表。
- [x] 每张待删除或 adapter 表都记录当前引用点、运行数据风险和建议处理方式。
- [x] 清单明确指出哪些表不允许新业务继续直接依赖。
- [x] 清单能够支撑后续 PDD、数据科目维护表 Module、`init_db.py` 拆分和历史删除 issue。

## Blocked by

None - can start immediately.

## Result

Published table ownership inventory:

- `.scratch/architecture-deep-clean/TABLE_OWNERSHIP.md`

2026-06-02 refresh:

- Re-read `var/data/common.db`, `budget_2025.db`, `budget_2026.db`, and `compare.db`.
- Added the missing current `bi_ai_subject_mapping` table to the ownership inventory and ERD private-table list.
- Refreshed runtime row counts for `user_sessions` and `business_cost_income_*`.
- Confirmed retired `report_account`, `report_data_mapping`, `report_accounts`, and `expense_execution_monthly` are absent from active runtime DBs.
