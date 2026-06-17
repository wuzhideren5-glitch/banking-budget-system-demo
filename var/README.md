# Runtime State Map

`var/` is local runtime state, not source code. Keep only the current runtime
directories here; historical evidence belongs under `archive/`, and generated
handoff packages should not include logs, pid files, backup DBs, or copied test
runs unless a package guide explicitly asks for them.

当前 `var/` 顶层运行目录精确清单（工作树门禁读取）：`data`, `logs`, `output`, `pids`, `run`, `scripts`。

## Current Runtime Directories

| Path | Role | Git rule |
| --- | --- | --- |
| `var/data/` | Live local SQLite databases and runtime data subdirectories. | Keep `var/data/.gitkeep`; do not commit DB files, caches, templates, backups, or generated report files from here. |
| `var/data/backups/` | Current DB backup root used by maintenance scripts. | Local recovery state only; old root backup folders have been consolidated here. |
| `var/logs/` | Current startup and manual-run logs. | Keep `var/logs/.gitkeep`; do not recreate old `var/log/`. |
| `var/output/` | New local generated reports and validation outputs. | Keep `var/output/.gitkeep`; archive old generated evidence after review. |
| `var/pids/` | Local process id files written by startup scripts. | Keep `var/pids/.gitkeep`; pid files are local state. |
| `var/run/` | Runtime pid and state files created by `start.sh`. | Local state only; same role as `var/pids/` but used by newer scripts. |
| `var/scripts/` | One-off runtime utility scripts for data seeding and diagnostics. | Keep scripts here only if actively used in runtime; source scripts belong in `apps/api/scripts/`. |
| `var/test-runs/` | Transient copied-data validation runs, created by scripts such as `apps/api/scripts/full_user_journey.py`. | Archive or remove old runs after review. This directory is allowed while a validation run is active, but it is intentionally not part of the exact persistent `var/` handoff list. |

## Retired Runtime Roots

- `var/backups/` is retired. Use `var/data/backups/`.
- 2026-06-03 cleanup: old May and early-June DB backup files were moved from
  `var/data/backups/` to
  `archive/runtime_snapshots/db_backups_legacy_20260603/`; the current backup
  root now keeps only current-run backups such as `schema_contract_20260603/`.
- `var/log/` is retired. Use `var/logs/`.
- `var/exports/` is retired. Use `var/output/` for new local generated files,
  then archive historical evidence under `archive/runtime_snapshots/`.
- Office lock/temp files such as `.~*.docx` or `.~*.pptx` do not belong in
  `var/data/smart_report_outputs/`; historical temp files have been moved to
  `archive/runtime_snapshots/office_temp/`.
