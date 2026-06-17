Status: ready-for-agent
Category: enhancement

# 迁移预算输入与预测驱动输入到 EditableFinancialGrid

## What to build

Migrate the core budget input and prediction driver input pages to the shared editable financial grid pattern. Users should get Excel-like editing power while the UI remains modern, calm, and clearly structured. Editable budget values, read-only actual/comparison values, formula-locked rows, and validation errors should all share the same visual language.

This slice unifies the highest-frequency budget data entry experience.

## Acceptance criteria

- [ ] Budget input uses shared editable grid states for editable, read-only, locked, missing, and error cells.
- [ ] Prediction driver input uses the same editable grid behavior for current budget values and read-only comparison values.
- [ ] Key identifying columns remain visible while users work across month columns.
- [ ] Keyboard editing behavior is consistent between the two pages.
- [ ] Page toolbars follow the shared GridToolbar standard for filters, units, refresh, import, and export where applicable.
- [ ] Existing data write protections and formula-lock behavior remain intact.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/04-build-editable-financial-grid.md`
- `.scratch/ui-system-governance/issues/05-build-grid-toolbar-standard.md`

