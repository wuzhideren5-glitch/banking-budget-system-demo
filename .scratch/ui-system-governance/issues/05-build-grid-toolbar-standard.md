Status: ready-for-agent
Category: enhancement

# 建设 GridToolbar 与报表操作标准

## What to build

Create a standard toolbar pattern for report and input grids. It should provide consistent locations and styling for filters, unit switching, expand all, collapse all, refresh, import, export, and search actions. The toolbar should feel compact and enterprise-grade, not like a dashboard control panel.

This slice gives all grid-based modules one operation language.

## Acceptance criteria

- [ ] A reusable grid toolbar can host filters, unit selectors, refresh, expand/collapse controls, search, and export actions.
- [ ] The toolbar remains compact and readable at 1366px width.
- [ ] The toolbar can wrap gracefully at narrower widths without covering the grid.
- [ ] Primary and secondary actions follow the frontend design spec button hierarchy.
- [ ] Unit switching is represented as a first-class toolbar control.
- [ ] A demo or fixture shows the toolbar connected to row/column group controls.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/02-build-report-grid-foundation.md`
- `.scratch/ui-system-governance/issues/03-add-row-and-column-grouping.md`

