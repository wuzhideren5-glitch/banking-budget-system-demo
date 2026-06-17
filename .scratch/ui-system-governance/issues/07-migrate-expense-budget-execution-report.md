Status: ready-for-agent
Category: enhancement

# 迁移费用预算执行报表到 ReportGrid

## What to build

Migrate the expense budget execution report to the shared ReportGrid pattern. Query mode and template/monthly report mode should share the same financial table language for hierarchy, grouping, unit switching, export, and readable report structure.

This slice should make expense reporting feel like part of the same financial workspace as budget output reports.

## Acceptance criteria

- [ ] Expense budget execution report tables use the shared report grid styling and structure.
- [ ] Department/subject tree report rows show indentation and expand/collapse behavior consistently.
- [ ] Unit switching uses the shared toolbar pattern and remains consistent with export output.
- [ ] Query mode and template/monthly report mode use consistent table, filter, and export controls.
- [ ] Empty states and loading/error states follow the frontend design spec.
- [ ] The page remains usable at 1024px and 1366px widths.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/02-build-report-grid-foundation.md`
- `.scratch/ui-system-governance/issues/03-add-row-and-column-grouping.md`
- `.scratch/ui-system-governance/issues/05-build-grid-toolbar-standard.md`

