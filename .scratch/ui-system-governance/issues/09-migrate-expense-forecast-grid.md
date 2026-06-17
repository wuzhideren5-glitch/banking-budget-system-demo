Status: ready-for-agent
Category: enhancement

# 迁移费用预测表到 EditableFinancialGrid

## What to build

Migrate the expense forecast table to the shared editable financial grid pattern. The page should preserve its monthly editing workflow, organization perspectives, import/export behavior, and analysis columns while adopting the unified grid states and toolbar language.

This slice aligns expense forecasting with the same Excel-grade editing standard as budget input.

## Acceptance criteria

- [ ] Monthly forecast cells use shared editable grid styling and behavior.
- [ ] Read-only actual/comparison values and summary analysis columns are visually distinct from editable cells.
- [ ] Entity, group, and expense-owner perspectives retain their current behavior while sharing one table language.
- [ ] Import/export actions follow the shared toolbar and state feedback patterns.
- [ ] Unit switching remains visible and consistent between page display and exported files.
- [ ] The page remains usable at 1024px and 1366px widths.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/04-build-editable-financial-grid.md`
- `.scratch/ui-system-governance/issues/05-build-grid-toolbar-standard.md`

