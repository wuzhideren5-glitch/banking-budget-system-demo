# 收敛 PDD 权威关系

Status: done
Type: HITL
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

把当前 PDD 从多轮合并流水账收敛为“当前权威架构 + 历史记录归档”的文档体系。读者应能从 PDD 直接判断某个业务事实、表、Module 或页面入口是否属于当前主线；已退休历史内容只作为归档记录，不作为 adapter、迁移来源或兼容入口。

## Acceptance criteria

- [x] Database PDD 明确当前目标表结构、表归属、表类型和禁止依赖事项。
- [x] Database ERD 与运行库清单和目标库结构一致，且标注事实表、投影表、adapter 表或待删除表。
- [x] System PDD 删除或归档与当前主线冲突的历史合并说明。
- [x] System PDD 顶部建立“当前阅读入口与权威边界”，并把后续 dated merge 段落标明为仅追溯的历史合并记录。
- [x] PDD 中明确旧 `report_account` / `report_data_mapping` 已删除，不能作为兼容入口或新业务主事实源。
- [x] PDD 中明确 **数据科目维护表** 与 **标准数据科目指标树** 的主事实源地位。
- [x] 历史补丁记录仍可追溯，但不再与当前权威条款同级。

## Blocked by

- Resolved by `.scratch/architecture-deep-clean/TABLE_OWNERSHIP.md`, Database PDD, ERD, and the System PDD history archive.

## Result

PDD authority supplements added to:

- `docs/product/Banking_Budget_Database_PDD.md`
- `docs/product/Banking_Budget_System_PDD.md`
- `docs/product/Banking_Budget_Database_ERD.md`
- `docs/product/Banking_Budget_Files.md`

2026-06-02 continuation:

- `docs/product/Banking_Budget_System_PDD.md` now opens with a current-reading gate that points developers to `CONTEXT.md`, `current-system-map.md`, `Banking_Budget_Files.md`, and Database PDD before dated merge notes.
- The dated merge-note area is explicitly labeled historical/trace-only, so old tables, routes, or module claims there are not current authority unless restated in current sections.
- `docs/product/README.md` now tells readers to treat System PDD historical merge records as trace material only.
- `docs/product/Banking_Budget_System_PDD.md`, `docs/product/Banking_Budget_Database_PDD.md`, and `CONTEXT.md` now state that old `report_account` / `report_data_mapping` tables are deleted and must not be restored as compatibility entries or main fact sources.

2026-06-03 continuation:

- `docs/product/Banking_Budget_System_PDD.md` no longer embeds dated merge notes before the current正文. It now links to `archive/handover/legacy_product_docs/System_PDD_historical_merge_records_20260603.md`.
- `docs/product/README.md` and `archive/README.md` register that archive as historical evidence only.
- `TABLE_OWNERSHIP.md`, `CODEBASE_REDUCTION_AUDIT.md`, `HIDDEN_MODULE_AUDIT.md`, and `WORKTREE_ORGANIZATION_REPORT.md` now point old backup DB evidence to `archive/runtime_snapshots/db_backups_legacy_20260603/` instead of stale `var/data/backups/root_*` runtime folders.
