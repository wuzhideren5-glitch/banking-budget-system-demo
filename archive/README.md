# Archive Map

`archive/` stores historical evidence only. Nothing in this directory is a
current source-code entrypoint, runtime schema owner, downloadable template, or
business-input allowlist item.

When current behaviour needs to be rebuilt, use `apps/`, `docs/`,
`resources/`, and `var/data/*.db` first. Read this archive only to understand
how an old delivery, migration, or rollback artifact looked before it was
retired.

## Directory Map

当前 `archive/` 顶层目录精确清单（工作树门禁读取）：`frontend_retired`, `handover`, `releases`, `root_excel_cleanup`, `runtime_snapshots`, `team_packages`。

| Path | Contents | Current-use rule |
| --- | --- | --- |
| `archive/team_packages/` | Teammate submissions and received package roots. | Preserve as received. First use `archive/team_packages/README.md`. Do not import code directly from here; re-implement through current `apps/web` and `apps/api` Modules. |
| `archive/releases/` | Historical release zips, rollback packages, and server handoff packages. | Recovery/reference only. First use `archive/releases/README.md`. Some packages intentionally preserve dependency folders exactly as received. |
| `archive/handover/` | Delivery notes, historical PDD patches, legacy import workbooks, historical product drafts, and old migration evidence. | Read for traceability; first use `archive/handover/README.md`. Do not treat files here as current templates or current product docs. |
| `archive/handover/legacy_hermes_plans_20260603/` | Retired Hermes planning notes for older smart report/PPT experiments and sandbox notes. | Historical planning evidence only. Current architecture notes live in `.scratch/` and `docs/development/`. |
| `archive/handover/legacy_scratch_plans_20260603/` | Retired `.scratch` PRDs and issue notes for old product budget workbench, old forecast driver input, and report-account retirement evidence. | Historical planning evidence only. Do not implement directly; rewrite against current `CONTEXT.md`, current DB inventory, and `apps/*` Modules first. |
| `archive/handover/legacy_product_docs/` | Product-design drafts and moved historical PDD merge records that are not current PDDs, including `System_PDD_historical_merge_records_20260603.md` and the 2026-05-09 Smart Report project notes. | Historical reference only. Current product facts live in `docs/product/` and `docs/development/current-system-map.md`. |
| `archive/runtime_snapshots/` | Old runtime DB snapshots, generated outputs, logs, copied test runs, temporary office files, and retired dependency/runtime snapshots. | Recovery/debug evidence only. First use `archive/runtime_snapshots/README.md`; current runtime state belongs under `var/`. |
| `archive/runtime_snapshots/db_backups_legacy_20260603/` | Historical `var/data/backups/` SQLite backups from May and early June cleanup work. | Recovery evidence only. Current backup scripts still write new backups to `var/data/backups/`. |
| `archive/runtime_snapshots/office_temp/smart_report_outputs_20260603/` | Retired Office lock/temp files copied out of `var/data/smart_report_outputs/`. | Do not restore into runtime outputs; these are not generated report artifacts. |
| `archive/frontend_retired/` | Retired frontend prototypes and removed page experiments. | Do not restore as current UI. First use `archive/frontend_retired/README.md`; rebuild any needed behaviour through `apps/web/src/app/workspaceCatalog.tsx` and current UI Modules. |

## Recovery Rules

- Copying from archive into active code requires a fresh current-design review.
- Team package buckets under `archive/team_packages/` must match the exact list
  in `archive/team_packages/README.md`.
- Historical release buckets under `archive/releases/` must match the exact
  list in `archive/releases/README.md`.
- Retired frontend buckets under `archive/frontend_retired/` must match the
  exact list in `archive/frontend_retired/README.md`.
- Historical tables and fields mentioned in archive files stay retired unless
  current PDDs and database ownership docs explicitly reintroduce them.
- Historical planning files in `archive/handover/legacy_hermes_plans_20260603/`
  must not be used as current product scope, build instructions, or runtime
  ownership docs.
- Retired `.scratch` planning files in
  `archive/handover/legacy_scratch_plans_20260603/` must not be treated as
  current issue tracker entries.
- Historical handover buckets under `archive/handover/` must match the exact
  list in `archive/handover/README.md`.
- Old Excel files in archive are evidence, not import templates. Current
  templates live in `resources/download_template/`; current business inputs live
  in `resources/business_inputs/README.md`.
- Old runtime DBs in archive are not the live system. The live local DBs are
  `var/data/common.db`, `var/data/budget_2025.db`, `var/data/budget_2026.db`,
  and `var/data/compare.db`.
- Runtime snapshot buckets under `archive/runtime_snapshots/` must match the
  exact list in `archive/runtime_snapshots/README.md`.
- Historical DB backups moved to
  `archive/runtime_snapshots/db_backups_legacy_20260603/` are no longer part of
  the current runtime backup root.
- Dependency caches inside historical release packages are package evidence.
  Do not copy them into the active root or new handoff packages.
