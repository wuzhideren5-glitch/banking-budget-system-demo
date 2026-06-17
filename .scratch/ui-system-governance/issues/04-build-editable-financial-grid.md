Status: ready-for-agent
Category: enhancement

# 建设可编辑 FinancialGrid 能力

## What to build

Extend the financial grid pattern for high-density budget input and adjustment workflows. The editable grid should distinguish editable cells, read-only comparison cells, formula-locked cells, missing editable cells, missing read-only cells, and error cells. It should support keyboard-friendly editing behavior aligned with users' Excel habits.

This slice prepares the shared editing behavior needed by budget input, prediction driver input, and expense forecast modules.

## Acceptance criteria

- [ ] Editable, read-only, locked, missing, and error cells have distinct visual states.
- [ ] Editable numeric cells preserve right alignment and tabular-number readability.
- [ ] Keyboard navigation behavior is predictable for row/column movement.
- [ ] Validation errors are visible at the cell or row level without overwhelming the table.
- [ ] The implementation leaves room for paste/bulk input behavior even if full paste support is deferred.
- [ ] A demo or fixture shows editable budget cells alongside read-only actual/comparison cells.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/02-build-report-grid-foundation.md`

