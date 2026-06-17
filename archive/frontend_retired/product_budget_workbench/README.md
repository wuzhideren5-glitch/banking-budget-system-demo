# Retired Product Budget Workbench

This directory preserves the removed product budget workbench page and prototype
components as historical UI evidence only.

## Files

| File | Historical role |
| --- | --- |
| `ProductBudgetWorkbenchContent.tsx` | Retired product budget workbench page component. |
| `ProductBudgetWorkbenchPrototypeContent.tsx` | Retired prototype/design comparison page component. |

## Current Replacement

Current product metric and data-account maintenance is implemented in
`apps/web/src/app/components/DataAccountContent.tsx` and its current backend
contracts. These archived components are not active routes, not migration
sources, and not current UI contracts.

## Rules

- Do not import these TSX files into current `apps/web` routes.
- If a future product-budget workflow is needed, design it against current
  product metric identity, current database inventory, and current `apps/web`
  Modules rather than reviving this page.
- Keep this README aligned with `docs/product/Banking_Budget_UI_Module_Migration_Checklist.md`.
