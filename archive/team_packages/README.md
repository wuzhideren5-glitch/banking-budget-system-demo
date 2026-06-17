# Team Packages Map

`archive/team_packages/` used to store historical teammate submissions and
received package roots. Those packages were traceability evidence only; they
were not current source code, current frontend roots, current backend roots, or
current database contracts.

2026-06-12 cleanup: the historical teammate package payloads were deleted to
reduce the development workspace size. Current frontend source lives in
`apps/web/`; current backend source lives in `apps/api/`.

## Rules

- Do not import code directly from here. Rebuild required behaviour through current `apps/web/`, `apps/api/`, `CONTEXT.md`, and current PDD/database docs.
