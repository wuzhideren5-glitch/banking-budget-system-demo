# Repository Layout

This repository is organized for multi-person development. The top-level directories are collaboration zones, not arbitrary folders.

## Active Development

- `apps/web/` contains the current frontend application. UI work, frontend state, Vite config, and web-only dependencies belong here.
- `apps/api/` contains the current backend application. FastAPI routers, backend services, DB maintenance scripts, and smoke scripts belong here.
- Root scripts and `package.json` are compatibility entrypoints. They should delegate into `apps/*` rather than accumulating product logic.
- `.ignore` is the current-code search boundary for ripgrep-style tools. It skips `archive/`, local dependencies, and runtime output so normal code review sees the active system first.
- The repository root should contain only current entrypoint/config files. Deployment notes belong under `docs/development/`; historical delivery notes and old import workbooks belong under `archive/handover/`.
- The repository root must not contain teammate packages, release zips, ad hoc Excel workbooks, generated reports, or old frontend roots. Put those under the archive or runtime locations below.
- The repository root must not contain old tool planning folders such as `.hermes/`. Retired planning notes belong under `archive/handover/`; current architecture notes belong under `.scratch/` and `docs/development/`.
- Local dependency/build caches such as root `node_modules/`, `.venv/`, `apps/api/.venv/`, `apps/api/.pytest_cache/`, `apps/web/node_modules/`, or `apps/web/dist/` may exist while developing, but they are ignored local state. They are not source, handoff material, or current architecture entrypoints.
- Python `__pycache__/` directories must not remain under active source roots. Use `PYTHONDONTWRITEBYTECODE=1` for repository execution checks, use `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache` for explicit `py_compile` syntax checks, and clean active-source bytecode caches before handoff.
- `docs/development/active-worktree-manifest.md` is the quick handoff checklist for this layout. Use it before touching a feature area, especially when distinguishing current code from historical submissions.
- `docs/development/current-worktree-status.md` is the current physical worktree and `git status` interpretation guide. Use it when old root deletions and new untracked current folders appear together.
- `.scratch/` is only for current architecture audits and still-reviewable candidate PRDs/issues. `.scratch/README.md` must list each active work area. Retired `.scratch` plans belong under `archive/handover/legacy_scratch_plans_20260603/`.

## Current Root Boundary

The active root is intentionally small: `README.md`, `AGENTS.md`, `CONTEXT.md`, `CHANGELOG.md`, `TEAM_SUBMIT_PACKAGING.md`, root package files, start/stop scripts, git/search ignore files, `apps/`, `docs/`, `resources/`, `var/`, `.scratch/`, `.agents/`, and `archive/`. Local dependency/build caches may exist while developing, but they are local state and not current source or handoff material.

`README.md` carries the exact persistent root-entry list enforced by `apps/api/scripts/verify_worktree_organization.py`. New persistent root entrypoints must be added there; retired root names must be removed. Local-only `.git/`, `.venv/`, and `node_modules/` are intentionally excluded from the exact handoff list.

`.agents/README.md` and `.agents/skills/README.md` carry exact local-Agent-asset lists enforced by `apps/api/scripts/verify_worktree_organization.py`. New local skill directories must be added to `.agents/skills/README.md`; retired skills and old prompt drafts must be moved to `archive/` or removed from the current handoff.

Root Markdown files are only for project entry, Agent collaboration, current changelog, and team submission rules. Product details, database contracts, deployment notes, and architecture maps belong under `docs/`; old delivery notes and obsolete PDD patches belong under `archive/handover/`.

`docs/product/README.md` and `docs/development/README.md` carry exact current-document lists enforced by `apps/api/scripts/verify_worktree_organization.py`. New current PDDs or development notes must be added to the matching list; retired, archived, or deleted document names must be removed from those lists.

`docs/agents/README.md` is the current Agent collaboration docs index. `docs/agents/` must contain only current Agent issue-tracker, triage, and domain-doc guidance; old Agent plans belong under `archive/` or retired `.scratch` areas.

`apps/api/scripts/verify_worktree_organization.py` enforces this root allowlist. Do not use deleted historical root entries such as `src/`, `src_from_Figma/`, `backend/`, `data/`, `knowledge_base/`, `download_template/`, `releases/`, `.hermes/`, old teammate package roots, root Excel workbooks, root delivery notes, root generated output folders, or any other unregistered root entry as current development locations.

## Controlled Resources

- `resources/README.md` is the controlled-resource entry map.
- The top-level `resources/` directory list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; new current resource areas must be added to `resources/README.md`, and historical samples must go to `archive/`.
- `resources/knowledge_base/` contains Agent knowledge, generated runtime config, prompt files, semantic dictionaries, and synonym/metric catalogs. Its first-level layer list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; every first-level knowledge layer must have its own `README.md`.
- `resources/download_template/` contains checked-in templates that users download or imports depend on. Its file list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; every current file must be listed in `resources/download_template/README.md`, and stale template names must be removed when archived.
- `resources/business_inputs/` contains business workbooks, reference decks, metric-tree initialization files, and other source materials used by the product. Its file list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; every current file must be listed in `resources/business_inputs/README.md`, and stale input names must be removed when archived.

## Local Runtime State

- `var/README.md` is the runtime-state entry map. Read it before placing files under `var/`.
- The persistent top-level `var/` directory list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; current handoff state is `data/`, `logs/`, `output/`, and `pids/`.
- `var/data/` is the default backend `data_dir`.
- The `var/data/` root should contain active SQLite DBs and runtime subdirectories only. Historical review workbooks, debug JSON, and old backup DB files belong under `archive/` or `var/data/backups/`, not beside `common.db`.
- Database backup scripts should write to `var/data/backups/`. Do not recreate `var/backups/` as a second backup root.
- `var/logs/`, `var/pids/`, and `var/output/` are local runtime directories. New generated reports should use `var/output/`; do not recreate root `outputs/` or `exports/`.
- Runtime logs belong under `var/logs/`. Do not recreate the old single-name `var/log/` directory.
- `var/test-runs/` is transient copied-data validation output created by scripts such as `apps/api/scripts/full_user_journey.py`; old runs should be archived or removed after review, not kept as current runtime state or added to the persistent `var/` exact list.
- `apps/api/scripts/verify_worktree_organization.py` enforces the top-level `var/` allowlist. Do not add ad hoc `var/tmp`, `var/exports`, `var/log`, or `var/backups` roots.
- `var/` is ignored by git except placeholder `.gitkeep` files. Do not commit local databases, logs, generated reports, or pid files.

## Archives

- `archive/README.md` is the archive entry map. Read it before using historical material.
- The top-level `archive/` directory list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`; new historical buckets must be added to `archive/README.md`, and stale bucket names must be removed from that index.
- `archive/team_packages/README.md` is the teammate-package history entry map. Its first-level bucket list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`.
- `archive/team_packages/` stores teammate delivery folders exactly as received.
- `archive/releases/README.md` is the historical release entry map. Its first-level bucket list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`.
- `archive/releases/` stores historical release packages and zips.
- `archive/frontend_retired/README.md` is the retired frontend entry map. Its first-level bucket list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`.
- `archive/frontend_retired/` stores removed frontend prototypes and is not a current UI implementation root. Each first-level retired frontend bucket must keep a `README.md` with its historical role and current replacement.
- `archive/handover/README.md` is the historical handover entry map. Its first-level bucket list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`.
- `archive/handover/` stores delivery manifests and handover notes.
- `archive/handover/legacy_hermes_plans_20260603/` stores retired Hermes planning notes and is not part of current build/runtime/product docs.
- `archive/handover/legacy_scratch_plans_20260603/` stores retired local PRDs/issues that should not appear as current issue tracker entries.
- `archive/runtime_snapshots/README.md` is the runtime-history entry map. Its first-level bucket list is exact and enforced by `apps/api/scripts/verify_worktree_organization.py`.
- `archive/runtime_snapshots/` stores migration-time runtime snapshots, old generated outputs, old logs, and dependency/runtime snapshots.
- `archive/handover/legacy_import_workbooks/` stores old Excel evidence that is not a current downloadable template or current business input.

Archive content is for reference and recovery. Do not use it as an active development location.

## Adding New Files

- New feature code: `apps/web` or `apps/api`.
- New reusable templates or prompt assets: `resources`.
- New product/architecture documentation: `docs`.
- New deployment or local-operator documentation: `docs/development`.
- New generated files: `var`.
- New delivered historical package: `archive`.
