# Worktree Organization Report

Date: 2026-06-03

This report records the current worktree layout after the architecture cleanup
pass. It is a handoff note for maintainers; the authoritative current entry
points remain `docs/development/repo-layout.md` and
`docs/product/Banking_Budget_Files.md`. The concise current physical worktree
handoff is `docs/development/current-worktree-status.md`.

## Current root allowlist

The repository root should contain only current project entry points and the
controlled collaboration zones:

| Root item | Current role |
| --- | --- |
| `apps/` | Current frontend and backend source code. |
| `docs/` | Current product, database, development, and agent documentation. |
| `.agents/` | Current repo-local Agent skill assets; `.agents/README.md` and `.agents/skills/README.md` are the entry maps. |
| `resources/` | Current templates, business inputs, and knowledge-base assets. |
| `archive/` | Historical delivery, rollback, teammate, and generated evidence; `archive/README.md` is the entry map. |
| `var/` | Local runtime data, logs, backups, and generated reports; `var/README.md` is the entry map. |
| `AGENTS.md`, `README.md`, `CONTEXT.md`, `CHANGELOG.md` | Current project guidance and domain context. |
| `package.json`, `package-lock.json`, `skills-lock.json` | Current root tooling entry points. |
| `start.sh`, `stop.sh` | Current local operator scripts. |
| `.ignore` | Current-code search boundary; keeps `rg` focused on active source instead of archive/runtime/cache material. |

The root must not contain teammate submissions, release packages, ad hoc Excel
workbooks, old frontend roots, generated `outputs/` / `exports/`, or committed
dependency environments. Ignored local dependency/build caches such as
`node_modules/`, `.venv/`, `apps/api/.venv/`, `apps/api/.pytest_cache/`,
`apps/web/node_modules/`, and `apps/web/dist/` may be present on a developer
machine, but they are not source, handoff material, or architecture entrypoints.
`README.md` now carries an exact persistent root-entry list; missing current
root entries and stale old root names both fail the worktree organization check.
`.agents/README.md` and `.agents/skills/README.md` now carry exact local-Agent-asset
lists; missing current skill directories and stale retired skill names both fail
the worktree organization check.
Active-source Python `__pycache__/` directories should be removed before handoff; explicit
`py_compile` checks should use `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache`.

## Archived material

| Former root material | Current archive location | Reason |
| --- | --- | --- |
| `TeamSubmit_*` folders and zips | `archive/team_packages/incoming/20260601/`, `archive/team_packages/incoming/20260602/` | Historical teammate submissions; not active source. |
| Root `releases/` | `archive/releases/root_releases_20260602/` | Historical release packages and manifests. |
| Root Excel samples and duplicate BI mapping workbook | `archive/handover/legacy_import_workbooks/` | Manual evidence or old samples; not current templates. |
| Root delivery note | `archive/handover/root_delivery_docs_20260602/` | Historical handoff note. |
| Root `outputs/` and `exports/` | `archive/runtime_snapshots/generated_outputs/` | Generated artifacts; new outputs belong in `var/output/`. |
| Historical `var/exports` and old `var/output` files | `archive/runtime_snapshots/generated_outputs/var_exports_20260603/`, `archive/runtime_snapshots/generated_outputs/var_output_20260603/` | Old simulation, budget-display, template-draft, merge-validation, and product-budget generated evidence; current `var/output/` is kept empty except `.gitkeep` for new local outputs. |
| Root `var/backups` | `archive/runtime_snapshots/db_backups_legacy_20260603/root_var_backups_20260603/` | Old script-created DB backups; active backup root is now `var/data/backups/`. |
| Root `var/log` | `archive/runtime_snapshots/logs/var_log_20260603/` | Old single-name log directory; current scripts write logs to `var/logs/`. |
| Old `var/test-runs` copied DB runs | `archive/runtime_snapshots/test_runs_20260603/` | Copied-data validation output from old script runs; scripts recreate `var/test-runs/` when needed. |
| Generated-output `node_modules` cache link | Removed from `archive/runtime_snapshots/generated_outputs/root_outputs_20260602/metric_tree_import_20260527/` | Rebuildable local dependency cache, not historical evidence. |
| Historical `resources/business_inputs` drafts | `archive/handover/legacy_import_workbooks/business_inputs_legacy_20260602/` and related archive folders | Old review drafts, generated previews, and migration evidence. |
| Old `src/`, `src_from_Figma/`, root Vite/TS config | Removed from active root; Figma/reference copy exists under `archive/team_packages/src_from_Figma/` | Current frontend lives only in `apps/web/`. |
| Old `.venv312` | `archive/runtime_snapshots/venv312_legacy/` | Dependency environment; not source. |
| ZLC delivery package | `archive/team_packages/ZLC_20260507_增加工作台和参数模板/` | Historical teammate package; not active source. |
| Historical Smart Report project draft | `archive/handover/legacy_product_docs/智能报告项目梳理_20260509.md` | Historical product draft; current product docs remain in `docs/product/` and current architecture facts remain in `docs/development/current-system-map.md`. |

## Current business inputs

`resources/business_inputs/README.md` is the current exact allowlist. As of
this cleanup, only these files remain in `resources/business_inputs/`:

- `BI科目匹配表.xlsx`
- `部门架构维护模版.xlsx`
- `费用整体框架.xlsx`
- `产品树20260505v4.xlsx`
- `26年一季度全行经营简报_脱敏版.pptx`

## Current download templates

`resources/download_template/README.md` is the current exact allowlist. As of
this cleanup, only these files remain in `resources/download_template/`:

- `budget_data_temp.xlsx`
- `data_acct_temp.xlsx`
- `dept_acct_temp.xlsx`
- `pivot_export_temp.xlsx`
- `product_org_tree_import_template.xlsx`

## Git status interpretation

The large deleted-file count is expected and mostly reflects removal of
historical or generated material that should not remain active:

| Category | Current status |
| --- | --- |
| `.venv312` | Tracked dependency environment removed from active root; archived under `archive/runtime_snapshots/venv312_legacy/`. |
| root `src/` / `src_from_Figma/` | Removed old frontend roots. Current frontend is `apps/web/`. |
| root `backend/` and old ZLC package files | Removed old teammate package layout. Current backend is `apps/api/`; package evidence is in `archive/team_packages/`. |
| root `Design docs/` | Removed old product-doc duplicate. Current docs live under `docs/`; old patches are under `archive/handover/`. |
| root release/output/workbook files | Moved to the archive/runtime locations listed above. |

Do not restore these paths as compatibility entry points. If historical evidence
is needed, read it from `archive/` and rebuild the current behaviour through the
current Modules.

## Verification run

- Root physical layout checked with `find . -maxdepth 1`.
- Current `resources/business_inputs/` allowlist checked with `find`.
- Old root path search checked for `outputs/acceptance`, `TeamSubmit_*(1)`,
  root expense samples, and `docs/product/team_contributions`.
- Backend script syntax checked with `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile`
  so bytecode does not land under active source.
- Runtime DB table ownership checked across `var/data/common.db`, `budget_2025.db`,
  `budget_2026.db`, and `compare.db`; all current tables have documented owners.
- Runtime generated-output cleanup checked with `find var/exports var/output`;
  `var/output` now contains only `.gitkeep`, and `var/exports` is absent.
- Runtime backup-root cleanup checked with `find var/backups var/data/backups archive/runtime_snapshots/db_backups_legacy_20260603`;
  `var/backups` is absent and old root backups are under `archive/runtime_snapshots/db_backups_legacy_20260603/`.
- Runtime log-root cleanup checked with `find var/log var/logs`;
  `var/log` is absent and current logs stay under `var/logs/`.
- Runtime test-run cleanup checked with `find var/test-runs archive/runtime_snapshots/test_runs_20260603`;
  old copied DB runs are archived and `var/test-runs` is absent until the next validation run.
- Active-source Python bytecode cleanup checked with `find apps/api apps/web -type d -name __pycache__`;
  dependency-environment bytecode under `apps/api/.venv/` is local cache, but `__pycache__/` under active source is not allowed to remain.
- Archive entry map added at `archive/README.md`.
- Root project entry map added to `README.md`. Persistent root entries must match that exact list;
  local-only `.git/`, `.venv/`, and `node_modules/` are excluded from the handoff list.
- Local Agent asset maps added at `.agents/README.md` and `.agents/skills/README.md`.
  Missing local skill directories and stale skill names both fail the organization check.
- `archive/team_packages/README.md` now carries an exact first-level teammate package bucket list.
  Missing historical package buckets and stale package names both fail the organization check, so
  teammate submissions remain traceable without becoming current frontend/backend roots.
- `archive/releases/README.md` now carries an exact first-level historical release bucket list.
  Missing release buckets and stale package names both fail the organization check, so old zips and
  rollback packages remain reference material instead of current deployable builds.
- `archive/frontend_retired/README.md` now carries an exact first-level retired frontend bucket list.
  Missing retired frontend buckets and stale retired UI names both fail the organization check, so
  removed page prototypes cannot drift back into current `apps/web` navigation by accident.
- Each first-level retired frontend bucket must now keep its own `README.md`; the current
  `product_budget_workbench` bucket documents that its replacement is the current data-account and
  product-metric maintenance Module, not the archived TSX files.
- `archive/README.md` now carries an exact top-level directory list. Missing archive buckets and
  stale bucket names both fail the worktree organization check, so historical evidence cannot drift
  into unregistered top-level archive areas.
- `archive/handover/README.md` now carries an exact first-level handover bucket list. Missing
  historical handover buckets and stale bucket names both fail the organization check, so old
  delivery, PDD, import-workbook, and migration evidence stays traceable without becoming current
  docs or resources.
- `archive/runtime_snapshots/README.md` now carries an exact first-level runtime snapshot bucket
  list. Missing runtime-history buckets and stale bucket names both fail the organization check,
  so old DBs, logs, generated outputs, and dependency snapshots stay out of current `var/`.
- Runtime entry map added at `var/README.md`; its persistent top-level runtime directory list is
  exact, so transient `var/test-runs/` output cannot remain as handoff structure after validation.
- Controlled resource entry maps added at `resources/README.md`, `resources/download_template/README.md`,
  and `resources/knowledge_base/06_agent_prompts/README.md`; current business inputs and download
  templates are exact allowlists in their own README files, and every first-level knowledge-base
  directory must keep its own `README.md`.
- `resources/README.md` now carries an exact top-level directory list. Missing current resource
  areas and stale resource bucket names both fail the worktree organization check, so old samples
  and generated evidence cannot re-enter as unregistered current resource folders.
- `resources/knowledge_base/README.md` now carries an exact first-level knowledge-layer list.
  Missing layers and stale layer names both fail the worktree organization check, so old prompt
  drafts, obsolete semantic layers, and runtime traces cannot be advertised as current knowledge.
- Agent collaboration docs now have `docs/agents/README.md` as the current index. Missing current
  agent docs and stale entries in that index both fail the organization check.
- Product and development docs now have exact current-document lists in `docs/product/README.md`
  and `docs/development/README.md`. Missing current docs and stale PDD/development-note names in
  those indexes both fail the organization check.
- `.scratch/README.md` now carries an exact current work-area list. Missing current work areas and
  stale work-area names both fail the worktree organization check, so retired local plans cannot stay
  advertised as active issue tracker entries.
- Worktree boundary verification can now be refreshed with `apps/api/scripts/verify_worktree_organization.py`;
  the script fails if retired root entries such as `src/`, `backend/`, `data`, `knowledge_base/`,
  `download_template/`, `releases/`, `.hermes/`, any unregistered root entry, stale active-doc page
  names, stale or missing persistent root entries in `README.md`, active-source `__pycache__/`
  directories, stale or missing `.agents` local skill entries, stale or missing `archive` top-level directory
  entries, stale or missing `archive/team_packages` historical package bucket entries, stale or missing
  `archive/releases` historical release bucket
  entries, stale or missing `archive/frontend_retired` retired frontend bucket entries, stale or missing
  `archive/handover` historical bucket entries, stale or missing
  `archive/runtime_snapshots` runtime-history bucket
  entries, stale or missing `.scratch` current work-area
  entries, stale or missing `resources` top-level directory entries,
  stale or missing `resources/knowledge_base` first-level entries,
  stale or missing `docs/agents` collaboration-doc entries,
  retired or unregistered top-level `var/` entries such as `var/backups`, `var/exports`,
  `var/log`, or ad hoc temp roots, stale or missing persistent `var/` directory entries in
  `var/README.md`,
  undocumented/stale current `apps/api/scripts/*.py` maintenance script entries in
  `Banking_Budget_Files.md` or `current-system-map.md`, undocumented/stale
  non-test top-level `apps/api/*` backend config/entry files in `Banking_Budget_Files.md`
  or `current-system-map.md`, undocumented/stale `apps/api/docs/*.md` backend-local docs in
  `Banking_Budget_Files.md` or `current-system-map.md`, undocumented/stale
  `apps/api/app/routers/*.py` HTTP Interface entries in `Banking_Budget_Files.md` or
  `current-system-map.md`,
  undocumented/stale `apps/api/app/*.py` top-level Module entries, undocumented/stale
  `apps/api/app/services/*.py` Module entries, or undocumented/stale
  `apps/api/app/db_bootstrap/*.py` database-contract Module entries reappear, or when a current
  backend router file is not mounted from `apps/api/app/main.py` (except the documented
  `expense_forecast_rules.py` sub-route registered by `expense_forecast.py`). It also fails when
  a current router file or `workspaceCatalog.tsx` navigation label is missing from
  `docs/development/current-system-map.md`, or when that system map's precise router/navigation
  inventories keep stale entries that no longer exist in `apps/api/app/routers/` or
  `workspaceCatalog.tsx`. It also requires the current physical worktree and `git status`
  handoff at `docs/development/current-worktree-status.md`. It also fails when a current
  `docs/product/*.md` file is not listed in the exact list in `docs/product/README.md`, when that
  list keeps stale product document names, when a current `docs/development/*.md` file is not listed
  in the exact list in `docs/development/README.md`, when that list keeps stale development document
  names, when a current
  `.scratch/<work-area>/` directory is not listed in `.scratch/README.md`, when a current
  file in `resources/business_inputs/` or `resources/download_template/` is not listed in that
  directory's exact README inventory, when those exact inventories keep stale resource file names,
  when a first-level `resources/knowledge_base/` directory has no
  `README.md`, when a current top-level `apps/web/*` frontend app config/entry file is missing
  from the exact frontend app config list in `Banking_Budget_Files.md` or `current-system-map.md`,
  or when that list keeps a stale frontend app config file, when a current top-level
  `apps/*` application directory is missing from the exact app directory list in
  `Banking_Budget_Files.md` or `current-system-map.md`, or when that list keeps a stale app
  directory, when a current top-level
  `apps/web/e2e/*.ts` frontend acceptance script is missing from the exact frontend e2e list in
  `Banking_Budget_Files.md` or `current-system-map.md`, or when that list keeps a stale frontend
  e2e script, when a current top-level
  `apps/web/src/*.ts(x)` root entry file is missing
  from the exact frontend src list in `Banking_Budget_Files.md` or `current-system-map.md`, or when
  that list keeps a stale frontend src entry file, when a current top-level
  `apps/web/src/app/*.ts(x)` shell/catalog file is missing from the exact app entry list in
  `Banking_Budget_Files.md` or `current-system-map.md`, or when that list keeps a stale frontend
  app entry file, when a current top-level
  `apps/web/src/app/components/*.ts(x)` frontend component/model file is missing from the exact
  component list in `Banking_Budget_Files.md` or `current-system-map.md`, or when that list keeps
  a stale frontend component/model file, when a current top-level `apps/web/src/styles/*.css` file
  is missing from the exact frontend style list in `Banking_Budget_Files.md` or
  `current-system-map.md`, or when that list keeps a stale frontend style file,
  when a current `apps/web/src/lib/*Api.ts` or `*ViewModel.ts` file is missing
  from the exact frontend domain list in `Banking_Budget_Files.md` or `current-system-map.md`,
  or when that list keeps a stale frontend domain file, when a current
  `apps/web/src/lib/*.ts` shared helper file that is not a domain API/ViewModel is missing from
  the exact frontend shared helper list in `Banking_Budget_Files.md` or `current-system-map.md`,
  or when that list keeps a stale frontend shared helper file, when a current
  `workspaceCatalog.tsx` navigation label is missing from
  the System/UI PDD navigation docs, or when a `workspaceCatalog.tsx` page component import is missing
  from `Banking_Budget_Files.md`. Relative links in current `README.md`, `CONTEXT.md`, `AGENTS.md`,
  and `docs/**/*.md` must also resolve to real files, so moved or archived PDD files cannot remain
  advertised as current entrypoints. Frontend
  domain clients and view models under `apps/web/src/lib/*Api.ts` / `*ViewModel.ts` must also be
  listed in both `Banking_Budget_Files.md` and `docs/development/current-system-map.md`, and frontend
  UI files under `apps/web/src/app/` must not contain raw `/api/*` backend paths. Retired code markers
  such as old report-account tables, old BI control-item mapping, old driver contracts, old workbench
  tables, and old raw-detail field names are allowed only in explicit deletion/rejection/check modules.
- Current database inventory can now be refreshed with `apps/api/scripts/verify_current_database_inventory.py`;
  the script prints live `var/data/*.db` table counts, fails if retired tables reappear, and fails if a
  current runtime table is missing from `docs/development/current-database-inventory.md` or lacks a
  Module/owner row in that inventory document.
- Retired-table dry run checked with
  `uv run python apps/api/scripts/delete_retired_tables.py --dry-run`;
  current `common.db` has no retired table left to delete.
- Frontend strict type check passed with `npx tsc -p apps/web/tsconfig.json --noEmit`.
- Frontend build passed with `npm run build`.
- Whitespace check passed with `git diff --check`.
