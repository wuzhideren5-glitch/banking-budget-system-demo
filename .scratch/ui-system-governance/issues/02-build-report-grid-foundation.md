Status: ready-for-agent
Category: enhancement

# 建设 FinancialGrid / ReportGrid 基础展示体系

## What to build

Create the first reusable FinancialGrid / ReportGrid display foundation for finance-style tables. It should make a simple hierarchical report table look like a modern financial web table while supporting the core structure users expect from Excel-style reports: indentation, summary rows, detail rows, fixed header behavior, right-aligned numbers, weak grid lines, and stronger structural boundaries.

This is the baseline grid slice that future report and input modules will build on.

## Acceptance criteria

- [ ] A reusable report grid foundation can render hierarchical rows with visible indentation.
- [ ] Summary rows, detail rows, muted/read-only rows, and normal rows have distinct but calm styling.
- [ ] Table headers remain visible while scrolling within the grid container.
- [ ] Numeric cells are right-aligned and use tabular number rendering.
- [ ] Ordinary grid lines are visually soft, while structural boundaries are clearer.
- [ ] A small demo or fixture proves the grid can render at least two hierarchy levels and mixed row types.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/01-lock-global-ui-style-and-governance.md`

