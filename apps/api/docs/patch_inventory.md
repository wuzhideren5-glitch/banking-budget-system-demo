# Patch Inventory

This file tracks patch-like logic to prevent long-term compatibility debt.

## Status Definitions

- `active`: currently required by business/runtime compatibility.
- `sunset-ready`: exit condition met, waiting for removal window.
- `removed`: patch has been removed.

## Patch Records

| id | type | location | intent | introduced_by | exit_condition | status |
|---|---|---|---|---|---|---|
| PATCH-API-001 | http-patch | `apps/api/app/main.py` (`/api/system/databases/{data_file_id}/versions/{version_id}`) | Partial update for system version metadata | current | API contract replaced by full `PUT` flow | active |
| PATCH-API-002 | http-patch | `apps/api/app/main.py` (`/api/system/users/{user_id}` and related user PATCH endpoints) | Partial update for user maintenance | current | User profile flow unified under single update command model | active |
| PATCH-COMPAT-001 | compatibility | `apps/api/app/agent_graph.py` (`_load_runtime_config`) | Merged legacy `intent_router_config.json` into new runtime config | historical | Removed on 2026-06-01; runtime now reads only `agent_runtime_config.json` and ignores retired `intent_router_config.json` files | removed |
| PATCH-COMPAT-002 | compatibility | `apps/api/app/main.py`, `apps/api/app/routers/templates.py` (template/year compatibility branches) | Accepted historical template names and fallback budget-year formats | historical | Removed on 2026-06-01; `/api/templates/{template_name}` accepts only registered current template stems, and database sync accepts only `budget_YYYY.db` files | removed |
| PATCH-MIGRATION-001 | migration | `apps/api/app/init_db.py` (dept-product mapping dedupe + unique index) | Normalized historical dept-product mapping data to a uniqueness rule | historical | Removed before 2026-06-01; `dept_product_mapping` is retired by `db_bootstrap.retired_deletion`, and current product grouping is derived from `org_product_tree_snapshot` | removed |

## Governance Rules

1. Every new patch must add one record with `exit_condition`.
2. Every release review checks whether any `active` patch can move to `sunset-ready`.
3. Removal PR must update status to `removed` and include rollback notes.
