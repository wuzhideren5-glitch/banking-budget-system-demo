# Current Worktree Status

Date: 2026-06-03

This file is the current handoff view of the physical worktree. Use it when `git status` looks noisy after the cleanup: it separates current source, historical evidence, runtime state, local caches, and the expected old-root deletions.

## Current Source

These locations are the only current product entrypoints:

| Scope | Current location | Current rule |
| --- | --- | --- |
| Frontend product | `apps/web/` | Current React/Vite UI, navigation, page Modules, frontend API clients, view models, styles, and web build config. |
| Backend product | `apps/api/` | Current FastAPI app, routers, service Modules, db bootstrap Modules, maintenance scripts, tests, and smoke scripts. |
| Product and architecture docs | `docs/`, `CONTEXT.md` | Current business terms, database ownership, page-route-service-table relationships, product PDDs, and development maps. |
| Agent collaboration docs | `docs/agents/`, `AGENTS.md` | Current Agent issue tracker, triage label, and domain-doc reading rules. `docs/agents/README.md` is the required index. |
| Local Agent skills | `.agents/` | Repo-local Agent skills that are intentionally bundled with this checkout. `.agents/README.md` and `.agents/skills/README.md` are the required indexes. |
| Controlled resources | `resources/` | Current download templates, business input allowlist, knowledge-base assets, prompts, and seed resources. `resources/README.md` is the entry map. |
| Architecture working notes | `.scratch/` | Current issue drafts and architecture audit notes that are still reviewable. `.scratch/README.md` is the required index; retired plans live in `archive/`. |

If a file is not reachable from one of these current locations, do not treat it as current implementation.
The repository root persistent entries must exactly match the precision list in `README.md`; local-only `.git/`, `.venv/`, and `node_modules/` are excluded from that current handoff list.
The current `.agents/` asset areas and `.agents/skills/` skill directories must exactly match their README precision lists; stale local skill names are treated as historical Agent asset leakage.
The current `.scratch/` work areas must exactly match the precision list in `.scratch/README.md`; stale work-area names in that index are treated as historical-plan leakage.
The current `docs/product/` and `docs/development/` Markdown files must exactly match the precision lists in their README files; stale PDD, old migration-note, or retired handoff-doc names in those indexes are treated as historical-doc leakage.
The current `resources/` top-level directories must exactly match the precision list in `resources/README.md`; historical samples or generated resource folders must be moved to `archive/` instead of added ad hoc.
The current `resources/business_inputs/` and `resources/download_template/` files must exactly match the precision lists in their README files; stale workbook/template names in those indexes are treated as historical resource leakage.
The current `resources/knowledge_base/` first-level layers must exactly match the precision list in `resources/knowledge_base/README.md`; old prompt drafts, obsolete semantic layers, and runtime traces do not belong there.

## Historical Material

Historical material is deliberately isolated under `archive/`:

| Archive location | What belongs there | Current-use rule |
| --- | --- | --- |
| `archive/team_packages/` | Teammate submissions and received project roots. | Preserve for traceability; do not import code directly. Rebuild needed behavior through current `apps/*` Modules. |
| `archive/releases/` | Old release zips, rollback packages, and server handoff packages. | Recovery/reference only. Not a source-code entrypoint. |
| `archive/handover/` | Old delivery notes, old product drafts, retired PDD patches, old Excel evidence, and retired migration scripts. | Historical evidence only. Current docs live in `docs/` and `CONTEXT.md`. |
| `archive/frontend_retired/` | Retired frontend experiments and old page prototypes. | Historical UI evidence only. First use `archive/frontend_retired/README.md`; recreate through current `apps/web` Modules if needed. |
| `archive/runtime_snapshots/` | Old DB snapshots, old generated outputs, old logs, old copied test runs, temp Office files, and retired dependency/runtime snapshots. | Debug/recovery evidence only. Current runtime state lives in `var/`. |

The top-level `archive/` directories must exactly match the precision list in `archive/README.md`; stale archive buckets and unregistered historical buckets are treated as worktree organization failures.
The current `archive/team_packages/` historical package buckets must exactly match the precision list in `archive/team_packages/README.md`; stale teammate-package names are treated as historical-package leakage.
The current `archive/releases/` historical release buckets must exactly match the precision list in `archive/releases/README.md`; stale release-package names are treated as historical-release leakage.
The current `archive/frontend_retired/` retired frontend buckets must exactly match the precision list in `archive/frontend_retired/README.md`; stale retired-UI names are treated as frontend-history leakage, and each retired frontend bucket must keep its own `README.md` explaining the current replacement.
The current `archive/handover/` historical buckets must exactly match the precision list in `archive/handover/README.md`; stale handover bucket names are treated as historical-material leakage.
The current `archive/runtime_snapshots/` runtime snapshot buckets must exactly match the precision list in `archive/runtime_snapshots/README.md`; stale snapshot bucket names are treated as runtime-history leakage.
Archive files may mention old `report_account`, old `driver_*`, old BI subject pages, old root `src/`, or retired DB paths. Those names are historical unless current `CONTEXT.md`, current database inventory, and current `apps/*` code reintroduce them.

## Runtime State

Runtime state is local and separate from source:

| Runtime location | Current role |
| --- | --- |
| `var/data/*.db` | Live local SQLite databases used by the backend. |
| `var/data/backups/` | Current backup root for schema/data changes made during development. |
| `var/logs/` | Current logs, including agent/runtime traces. |
| `var/output/` | Current generated outputs. |
| `var/pids/` | Current local process pid files. |

Old outputs, old copied validation DBs, old logs, and old backups that are no longer current belong in `archive/runtime_snapshots/`.
The top-level `var/` allowlist is enforced by `apps/api/scripts/verify_worktree_organization.py`; retired `var/backups/`, `var/exports/`, and `var/log/` must not reappear.
The persistent top-level `var/` directories must exactly match the precision list in `var/README.md`. Transient `var/test-runs/` output is allowed only while a validation run is active; archive or remove it before handoff so it does not become current runtime structure.

## Local Caches

The following may exist on a developer machine, but they are not source, handoff material, or product architecture:

- Root `node_modules/`
- Root `.venv/`
- `apps/api/.venv/`
- `apps/api/.pytest_cache/`
- `apps/web/node_modules/`
- `apps/web/dist/`

Do not use dependency caches as current implementation evidence. Reinstall or rebuild them from the current source and lock files when needed.
Python bytecode directories under active source, such as `apps/api/__pycache__/` or `apps/api/scripts/__pycache__/`, are not allowed to remain in the organized worktree. Run Python execution checks with `PYTHONDONTWRITEBYTECODE=1`; run explicit syntax compilation with `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache` if needed, and remove active-source `__pycache__` directories before handoff.

## Git Status Interpretation

This cleanup moved the active project into a small current root. As a result, `git status` can show two kinds of noise:

| Status shape | Meaning | What to do |
| --- | --- | --- |
| Old root files marked `D` | The old root entry left current worktree scope. Examples include root `src/`, `src_from_Figma/`, `backend/`, `data/`, `knowledge_base/`, `download_template/`, `releases/`, old root Excel files, and old delivery notes. | Do not restore them as compatibility entrypoints. Read equivalent historical evidence from `archive/` only. |
| New current folders marked `??` | The reorganized current layout is not yet staged in Git. Examples include `apps/`, `docs/`, `resources/`, `archive/`, `var/`, `CONTEXT.md`, `AGENTS.md`, and this documentation set. | Review current docs and validation output, then stage intentionally when ready. |

The desired physical root is intentionally small: current entry files, `apps/`, `docs/`, `resources/`, `var/`, `.scratch/`, `.agents/`, and `archive/`, plus local caches while developing.

## Verification

Run this bundle before handing the tree to another developer:

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npx tsc -p apps/web/tsconfig.json --noEmit
npm --workspace apps/web run build
```

For department-expense changes, also run the focused backend tests listed in `docs/development/active-worktree-manifest.md`.
