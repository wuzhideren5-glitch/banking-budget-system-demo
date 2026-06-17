# Historical Handover Map

`archive/handover/` stores historical delivery notes, old migration evidence,
retired product docs, and team-contribution traces. It is not a current product
doc directory, import-template directory, or runtime source.

当前 `archive/handover/` 历史交接目录精确清单（工作树门禁读取）：`legacy_product_docs`, `retired_product_budget_workbench`, `root_delivery_docs_20260602`, `team_contributions`。

## Current Historical Buckets

| Directory | Historical role |
| --- | --- |
| `legacy_data_account_migrations/` | Old data-account migration evidence. |
| `legacy_hermes_plans_20260603/` | Retired Hermes planning notes and sandbox plans. |
| `legacy_import_workbooks/` | Old Excel evidence that is not a current template or business input. |
| `legacy_pdd_patches/` | Historical PDD patch material. |
| `legacy_product_docs/` | Retired product drafts and moved historical merge records. |
| `legacy_report_account_artifacts/` | Old report-account retirement and compatibility evidence. |
| `legacy_scratch_plans_20260603/` | Retired `.scratch` PRDs and issue notes. |
| `retired_product_budget_workbench/` | Retired product-budget-workbench material. |
| `root_delivery_docs_20260601/` | Root delivery notes moved during the 2026-06-01 cleanup. |
| `root_delivery_docs_20260602/` | Root delivery notes moved during the 2026-06-02 cleanup. |
| `team_contributions/` | Historical team contribution validation and handoff evidence. |

## Root Files

The remaining files directly under `archive/handover/` are historical delivery
notes, package manifests, or preserved archives. They are evidence only. Do not
copy them into `docs/`, `resources/`, `apps/`, or `var/` without rebuilding the
current behaviour against `CONTEXT.md`, `docs/development/current-system-map.md`,
and the live database inventory.

## Rules

- New historical handover buckets must be listed in the exact list above.
- Retired or moved bucket names must be removed from the exact list.
- Current product docs live in `docs/product/`; current development docs live in `docs/development/`.
- Current download templates live in `resources/download_template/`; current business inputs live in `resources/business_inputs/`.
