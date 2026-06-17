Status: ready-for-agent
Category: enhancement

# 建设行组与列组展开收起能力

## What to build

Extend the grid foundation with Excel-like structural controls for report organization. Users should be able to expand and collapse row groups and show or hide column groups such as month groups, version groups, and budget/actual comparison groups without losing the modern financial table look.

This slice should make report structure manageable before individual report pages are migrated.

## Acceptance criteria

- [ ] Row groups can be expanded and collapsed from the first identifying column.
- [ ] Column groups can be shown and hidden while preserving column alignment.
- [ ] Group headers visually communicate structure without heavy or noisy grid lines.
- [ ] Month, version, and budget/actual group examples are covered in a fixture or demo.
- [ ] Collapsed groups keep enough context visible for users to understand what is hidden.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/02-build-report-grid-foundation.md`

