Status: ready-for-agent
Category: enhancement

# 建立 UI 回归验收与截图基线

## What to build

Establish a repeatable UI regression checklist and screenshot/viewport baseline for the new UI system. The goal is to prevent future modules from drifting away from the modern financial enterprise style and Excel-grade grid behavior.

This slice should turn UI consistency into an ongoing quality gate.

## Acceptance criteria

- [ ] A UI regression checklist exists for global shell, standard pages, report grids, editable grids, AI surfaces, dialogs, and exports.
- [ ] The checklist includes 1024px and 1366px viewport review expectations.
- [ ] Core pages are identified for screenshot or manual visual baselines.
- [ ] Grid-specific checks cover hierarchy, grouping, fixed headers, numeric alignment, editable/read-only/locked/error states, and toolbar behavior.
- [ ] Build verification with `npm run build` is included in the standard UI acceptance flow.
- [ ] The baseline can be reused by future feature issues and AFK agents.

## Blocked by

- `.scratch/ui-system-governance/issues/06-migrate-budget-display-report.md`
- `.scratch/ui-system-governance/issues/07-migrate-expense-budget-execution-report.md`
- `.scratch/ui-system-governance/issues/08-migrate-budget-input-and-prediction-driver.md`
- `.scratch/ui-system-governance/issues/09-migrate-expense-forecast-grid.md`
- `.scratch/ui-system-governance/issues/10-unify-global-shell-and-standard-pages.md`
- `.scratch/ui-system-governance/issues/11-unify-ai-agent-report-ppt-surfaces.md`

