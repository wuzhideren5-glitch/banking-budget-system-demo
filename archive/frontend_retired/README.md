# Retired Frontend Map

`archive/frontend_retired/` stores frontend prototypes and removed page
experiments that are no longer current UI entrypoints.

当前 `archive/frontend_retired/` 退休前端目录精确清单（工作树门禁读取）：`product_budget_workbench`。

## Current Retired Frontend Buckets

| Directory | Historical role |
| --- | --- |
| `product_budget_workbench/` | Retired product budget workbench page and prototype components removed from current navigation. Read `product_budget_workbench/README.md` first. |

## Rules

- Do not import components from this archive into current routes.
- If retired behaviour is needed again, rebuild it through current `apps/web/src/app/workspaceCatalog.tsx`, current page Modules, and current backend/database contracts.
- New retired frontend buckets must be listed in the exact list above.
- Removed retired frontend buckets must be removed from the exact list.
- Every retired frontend bucket must keep its own `README.md` explaining its historical role and current replacement.
