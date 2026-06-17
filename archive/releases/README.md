# Historical Releases Map

`archive/releases/` used to store old release zips, rollback packages, and
server handoff packages. Those packages were recovery/reference evidence only;
they were not the current deployable build or current source tree.

2026-06-12 cleanup: the historical release payloads were deleted to reduce the
development workspace size. Current source remains in `apps/`, current runtime
data remains in `var/data/`, and current handoff packages, if needed, should be
rebuilt from the current workspace instead of reused from this archive.

当前 `archive/releases/` 历史发布目录精确清单（工作树门禁读取）：`merge_notes`。
