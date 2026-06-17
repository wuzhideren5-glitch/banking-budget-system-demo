Status: ready-for-agent
Category: enhancement

# 统一全局壳层与普通业务页视觉底座

## What to build

Apply the global UI style to the application shell and standard non-grid business pages. The top bar, navigation tree, tab workspace, status bar, page shells, buttons, forms, cards, popovers, and dialogs should share the same modern financial enterprise look.

This slice keeps the rest of the system coherent while the grid-heavy pages evolve.

## Acceptance criteria

- [ ] The global shell uses the shared design tokens and avoids arbitrary new colors.
- [ ] Standard page shells, toolbars, panels, buttons, inputs, popovers, and status banners follow the frontend design spec.
- [ ] Non-grid pages avoid dashboard/card-wall visual patterns.
- [ ] Loading, empty, success, warning, and error states use consistent components or classes.
- [ ] The shell and standard pages remain usable at 1024px and 1366px widths.
- [ ] `npm run build` passes.

## Blocked by

- `.scratch/ui-system-governance/issues/01-lock-global-ui-style-and-governance.md`

