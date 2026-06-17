Status: ready-for-agent
Category: enhancement

# 迁移预算展示报表到 ReportGrid

## What to build

Migrate the budget display report page to the shared ReportGrid pattern so it becomes the reference implementation for financial report pages. The report should keep its business views while adopting unified hierarchy, grouped columns, fixed headers, unit switching, expand/collapse controls, and export consistency.

This slice should produce a visible benchmark for the rest of the system's report UI.

## Acceptance criteria

- [ ] The budget display report uses the shared report grid foundation for row hierarchy and numeric rendering.
- [ ] Report rows show clear indentation, summary/detail distinction, and calm financial table styling.
- [ ] Month or version column groups can be expanded/collapsed where the page currently exposes detailed columns.
- [ ] The page toolbar follows the GridToolbar standard for filters, unit switching, refresh, and export.
- [ ] Export behavior remains consistent with the currently selected page filters and units.
- [ ] The page remains usable at 1024px and 1366px widths.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/02-build-report-grid-foundation.md`
- `.scratch/ui-system-governance/issues/03-add-row-and-column-grouping.md`
- `.scratch/ui-system-governance/issues/05-build-grid-toolbar-standard.md`

