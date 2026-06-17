# Runtime Snapshots Map

`archive/runtime_snapshots/` used to store old local runtime state that had
been moved out of active `var/`. Those snapshots were recovery/debug evidence
only, not live databases, generated outputs, or dependency state.

2026-06-12 cleanup: the historical snapshot payloads were deleted to reduce the
development workspace size. This included old DB backup snapshots, copied test
runs, generated-output evidence, logs, Office temp files, and the retired
`venv312_legacy` environment.

The current runtime state remains under `var/`; current live SQLite databases
remain under `var/data/`. Do not restore historical DBs into active runtime
paths unless there is a current recovery plan.

当前 `archive/runtime_snapshots/` 运行快照目录精确清单（工作树门禁读取）：`misplaced_apps_runtime_20260617`。

## Current Snapshot Buckets

| Directory | Historical role |
| --- | --- |
| `misplaced_apps_runtime_20260617/` | Misplaced `apps/var` and `apps/resources` runtime copies moved out of the active `apps/` tree. |
