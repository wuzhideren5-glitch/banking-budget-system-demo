# Patch Inventory

This file tracks patch-like logic to prevent long-term compatibility debt.

## Status Definitions

- `active`: currently required by business/runtime compatibility.
- `sunset-ready`: exit condition met, waiting for removal window.
- `removed`: patch has been removed.

## Patch Records

| id | type | location | intent | introduced_by | exit_condition | status |
|---|---|---|---|---|---|---|
| PATCH-API-001 | http-patch | `backend/app/main.py` (`/api/system/databases/{data_file_id}/versions/{version_id}`) | Partial update for system version metadata | current | API contract replaced by full `PUT` flow | active |
| PATCH-API-002 | http-patch | `backend/app/main.py` (`/api/system/users/{user_id}` and related user PATCH endpoints) | Partial update for user maintenance | current | User profile flow unified under single update command model | active |
| PATCH-COMPAT-001 | compatibility | `backend/app/agent_graph.py` (`_load_runtime_config`) | Merge legacy `intent_router_config.json` into new runtime config | historical | No legacy config file in all deployed environments for 2 releases | active |
| PATCH-COMPAT-002 | compatibility | `backend/app/main.py` (template/year compatibility branches) | Accept historical template/year formats | historical | Legacy template usage rate drops below agreed threshold | active |
| PATCH-MIGRATION-001 | migration | `backend/app/init_db.py` (dept-product mapping dedupe + unique index) | Normalize historical mapping data to current uniqueness rule | historical | Schema migration framework introduced and migration replay verified | active |

## Governance Rules

1. Every new patch must add one record with `exit_condition`.
2. Every release review checks whether any `active` patch can move to `sunset-ready`.
3. Removal PR must update status to `removed` and include rollback notes.
