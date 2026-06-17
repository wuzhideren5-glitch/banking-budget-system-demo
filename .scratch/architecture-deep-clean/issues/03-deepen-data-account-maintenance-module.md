# 加深数据科目维护表 Module

Status: completed
Type: AFK
Source: `.scratch/architecture-deep-clean/GOAL.md`

## What to build

让 **数据科目维护表** 成为唯一创建、修改、绑定和校验数据科目身份的 Module。调用方只通过它表达“我要维护某个指标口径和产品范围下的数据科目”，不需要知道历史编码、旧报告科目字段、旧工作台痕迹或绑定表细节。

## Acceptance criteria

- [x] 新建和修改数据科目时，唯一指标号码只由 **标准数据科目指标树** 与产品范围生成。
- [x] 数据科目身份、指标口径、产品范围绑定、值类型、公式和手工补录开关都通过一个清晰 Interface 维护。
- [x] 旧报告科目、旧驱动分类、旧工作台表不得参与正式数据科目身份生成。
- [x] 后端测试覆盖唯一指标号码生成、绑定校验、重复冲突和非法范围。
- [x] 前端数据科目维护页面通过收敛后的 Interface 读写，不再重复实现身份规则。
- [x] PDD 中的数据科目维护表职责与实际实现一致。

## Blocked by

- resolved: `.scratch/architecture-deep-clean/issues/01-database-table-ownership-inventory.md`
- resolved: `.scratch/architecture-deep-clean/issues/02-consolidate-pdd-authority.md`

## Result

Implemented the first data-account identity seam:

- `apps/api/app/data_account_write.py` now owns official identity resolution and import upsert through `resolve_data_account_identity()` and `upsert_data_account_with_binding()`.
- `apps/api/app/routers/data_accounts.py` no longer reimplements create/import identity SQL and rejects direct unique-number edits.
- `apps/web/src/app/components/DataAccountContent.tsx` presents the unique metric number as generated identity rather than an editable business field.
- `apps/api/test_data_account_write.py` covers identity parsing, mismatch rejection, official binding creation, upsert, and overlapping product-scope rejection.

Verification:

- `python -m py_compile app/data_account_write.py app/routers/data_accounts.py test_data_account_write.py`
- `uv run python -m unittest test_data_account_write`

## Evidence refresh 2026-06-03

- `apps/api/app/data_account_write.py` is the current write Module for product-prefixed identity resolution, official data-account code generation, metric binding, formula mode, value type, and manual-entry persistence.
- `apps/api/app/routers/data_accounts.py` calls `resolve_data_account_identity(...)` for create/import and rejects direct unique-number edits in PATCH, so callers cannot reintroduce suffix-style or free-form data-account identity.
- `apps/api/test_data_account_write.py` covers product-prefixed identity generation, legacy suffix rejection, mismatched metric/code rejection, product-scope mismatch rejection, duplicate official identity rejection, create/upsert through one Interface, and retired horizontal product formula sync.
- The active frontend path uses `apps/web/src/lib/masterDataApi.ts`, `apps/web/src/lib/dataAccountViewModel.ts`, `DataAccountContent.tsx`, and split child views. The create flow submits `metric_node_code` and the product prefix `scope_code`; the backend remains the authority for official `data_acct_code`. Frontend checks are display/input guidance only.
- Focused search found no retired `report_account`, `report_data_mapping`, `driver_*`, `product_budget_component*`, `forecast_workbench*`, or `assumption_*` dependency in the active data-account write/router/frontend/test slice.
- `CONTEXT.md`, `docs/development/current-system-map.md`, `docs/product/Banking_Budget_Database_PDD.md`, `docs/product/Banking_Budget_Files.md`, and `docs/product/Banking_Budget_System_PDD.md` now describe `data_account.data_acct_code = data_account_metric_binding.metric_node_code` and product-prefixed identity such as `A05.01.01.001`; old report/workbench identities are historical-only.
