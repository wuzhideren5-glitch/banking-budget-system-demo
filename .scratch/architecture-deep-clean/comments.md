# Codex Review Comments: Project Reorganization Audit

Date: 2026-06-17
Reviewer: Codex
Scope: Check whether the current worktree has completed the Qoder/full-project cleanup and reorganization requirements recorded in `WORKTREE_ORGANIZATION_REPORT.md`, `CODEBASE_REDUCTION_AUDIT.md`, `DELETION_REPORT.md`, and Qoder cleanup notes.

## Overall Verdict

Not complete.

The project is partially reorganized and remains buildable, but it does not yet satisfy the full-reorganization acceptance criteria. The strongest evidence is that both architecture acceptance scripts fail:

- `python apps/api/scripts/verify_worktree_organization.py` -> `worktree_organization=failed`
- `apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py` -> failed inventory / identity checks

Positive checks:

- `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile apps/api/scripts/verify_worktree_organization.py apps/api/scripts/verify_current_database_inventory.py` passed.
- `git diff --check` passed.
- `npx tsc -p apps/web/tsconfig.json --noEmit` passed.
- `npm run build` passed.

## Review Comments

| Priority | Block | Issue | Evidence | Recommendation |
| --- | --- | --- | --- | --- |
| P0 | Worktree organization | Root directory still violates the root allowlist. | The report says root should contain only controlled entries and must not keep release packages, teammate submissions, old roots, generated outputs, or unregistered entries. Current root still has `.qoder`, `.superpowers`, `.vscode`, `TEAM_SUBMIT_MANIFEST_TeamSubmit_20260606_org_product_single_metric_system.txt`, nested `kevinchen_20260507_新增预算预测驱动因素模块(2)`, `releases`, and root `scripts`. `verify_worktree_organization.py` flags all of these as `unexpected-root-entry`. | Decide which are local-only vs source/handoff. Move handoff/history into `archive/`, document allowed local-only dirs if intentionally kept, or remove them before declaring completion. Re-run `verify_worktree_organization.py` until clean. |
| P0 | Architecture acceptance | The official worktree verifier fails across many categories, so the reorganization cannot be accepted as complete. | Failures include unexpected root entries, stale README root list, missing guide file, active-source `__pycache__`, stale/missing archive indexes, stale/missing backend router/service inventories, stale/missing frontend component/lib inventories, and raw frontend API paths. | Treat verifier output as the authoritative punch list. Fix the first structural layer first: root/var/cache/docs indexes, then router/service/frontend inventory drift. |
| P0 | Database inventory / identity contract | Database inventory verifier fails even though retired tables are gone. | `verify_current_database_inventory.py` reports `inventory_doc=missing_tables` for `intelligent_budget_tasks`, `business_data_account_refs=failed`, `derived_read_model_data_code_name_refs=failed`, and `legacy_second_segment_99=failed`. | Update table ownership docs for current tables, then fix or explicitly document remaining legacy data-account references and `A02.99*` residue. Do not call the data model cleanup complete until this verifier passes. |
| P1 | Business inputs allowlist | `resources/business_inputs` contains more files than the full-reorg report allows. | Report allowlist has 5 files. Current directory also includes `产品指标.xlsx`, `机构产品数据录入_B01_业务状况表_2026 (1).xlsx`, `机构及产品指标（公式配置） - v03.xlsx`, `机构汇总指标.xlsx`, and `科目和层级表.xlsx`. Verifier flags several as `business-input-missing-from-index`. | Either archive the extra workbooks or update `resources/business_inputs/README.md` and the system docs if these are now current canonical inputs. Avoid leaving them as unindexed semi-current inputs. |
| P1 | Runtime directory contract | `var/` still contains unregistered runtime roots. | Report says `var/output` should only contain `.gitkeep`, `var/exports` absent, `var/log` absent, and transient test dirs absent. `var/output` is clean, but current `var/` still has `var/run` and `var/scripts`; verifier flags them as unexpected/missing from `var/README.md`. | Move one-off runtime scripts out of `var/`, or register them if they are intentionally current. Keep pid/run material under the documented runtime contract. |
| P1 | Frontend layering | UI components still call raw `/api/*` endpoints directly. | Verifier flags raw API paths in component files. Examples: `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx` calls `/api/org-product-metrics/*`; `OrgProductDataEntryContent.tsx` calls `/api/org-product-data-entry/*`, `/api/org-product-tree/*`, and `/api/org-product-metrics/*`. | Move endpoint strings and request functions into `apps/web/src/lib/<domain>/...Api.ts`. Components should consume typed lib functions so UI and transport stay separated. |
| P1 | Module deepening | The old giant org-product router has been split, but large modules remain. | `apps/api/app/main.py` now mounts split routers, which is good. But `apps/api/app/routers/org_product_helpers.py` is still 3106 lines and `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx` is still 5183 lines. | Continue splitting helpers by concern: Excel parsing/export, snapshot persistence, metric catalog, output calculation, and tree parsing. Split frontend into state hook, toolbar/table, formula editor, import/export, and entity/table selection modules. |
| P2 | Cache and generated files | Active-source `__pycache__` directories remain. | Verifier flags `apps/api/__pycache__`, `apps/api/app/__pycache__`, `apps/api/app/agent/__pycache__`, `apps/api/app/core/__pycache__`, `apps/api/app/db_bootstrap/__pycache__`, `apps/api/app/integrations/__pycache__`, `apps/api/app/routers/__pycache__`, `apps/api/app/services/__pycache__`, `apps/api/scripts/__pycache__`, and `apps/api/tests/org_product/__pycache__`. | Delete active-source cache directories before handoff. Continue using `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache` for compile checks. |
| P2 | Historical size cleanup | Large live/local assets remain, and Qoder's historical-size concerns are only partially addressed. | Current sizes: `.git` 949M, `var/data` 601M, `apps/api/.venv` 265M, root `node_modules` 177M. This matches Qoder's earlier concern profile. Some are expected current/local assets, but they still mean the repository is not fully slimmed from an operational handoff perspective. | Do not delete live DBs casually. For clone/package size, handle `.git` history separately with explicit approval and backup. Keep runtime DBs out of source packages unless the package explicitly requires data. |

## Completed Or Partially Completed

- Old `apps/api/app/routers/org_product_metrics.py` appears removed.
- The backend now imports and mounts split org-product routers: `org_product_tree`, `org_product_metric_config`, `org_product_report_import`, `org_product_data_entry`, and `org_product_output`.
- Download template allowlist matches the report: `budget_data_temp.xlsx`, `data_acct_temp.xlsx`, `dept_acct_temp.xlsx`, `pivot_export_temp.xlsx`, and `product_org_tree_import_template.xlsx`.
- `var/output` is currently empty except no visible generated files.
- Frontend TypeScript and production build both pass.

## Recommended Completion Order

1. Make `verify_worktree_organization.py` pass for root, `var/`, cache directories, and exact README inventories.
2. Make `verify_current_database_inventory.py` pass, especially current table ownership and legacy identity references.
3. Move raw `/api/*` calls out of frontend components into typed lib API modules.
4. Continue the org-product module split where the largest files remain.
5. Re-run `py_compile`, both verifiers, `tsc`, `npm run build`, and `git diff --check`.

## Commands Run

```bash
ls -1A
find resources/business_inputs -maxdepth 1 -type f -print | sort
find resources/download_template -maxdepth 1 -type f -print | sort
find var -maxdepth 2 -mindepth 1 -print | sort
du -sh .git var/data apps/api/.venv node_modules releases research_papers common.db .qoder .vscode 2>/dev/null
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile apps/api/scripts/verify_worktree_organization.py apps/api/scripts/verify_current_database_inventory.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python apps/api/scripts/verify_worktree_organization.py
apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npx tsc -p apps/web/tsconfig.json --noEmit
npm run build
git diff --check
```

---

# Codex Second Review: After Qoder Follow-up

Date: 2026-06-17
Scope: Re-check whether Qoder's follow-up actually completed the full project cleanup / reorganization work.

## Updated Verdict

Substantially complete by the current repository acceptance gates.

Compared with the first review, Qoder fixed the important blockers:

- `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python apps/api/scripts/verify_worktree_organization.py` -> `worktree_organization=ok`
- `PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py` -> all checked sections `ok`
- `npx tsc -p apps/web/tsconfig.json --noEmit` passed
- `npm run build` passed
- `git diff --check` passed
- active-source `__pycache__` directories are clean after the verification run
- direct raw `/api/*` calls were removed from `apps/web/src/app/**`

## Resolved Since First Review

| Previous issue | Current result | Review judgment |
| --- | --- | --- |
| Worktree verifier failed | Now `worktree_organization=ok` | Resolved |
| Database inventory / identity verifier failed | Now all inventory, owner, metric identity, runtime refs, business refs, derived read model refs, legacy `99`, canonical expense tree, runtime catalog, and retired menu checks are `ok` | Resolved |
| Active-source `__pycache__` remained | Clean after rerun with `PYTHONPYCACHEPREFIX` and cache cleanup | Resolved |
| Frontend components had raw `/api/*` calls | `rg` over `apps/web/src/app` returns no raw API paths | Resolved |
| Root still had old release/team manifest/nested project entries | Current root no longer has `releases`, nested same-name project dir, or `TEAM_SUBMIT_MANIFEST...` | Resolved |
| Download template allowlist | Still matches expected current files | Resolved |

## Remaining Review Notes

| Priority | Block | Issue | Evidence | Recommendation |
| --- | --- | --- | --- | --- |
| P1 | Documentation source of truth | `WORKTREE_ORGANIZATION_REPORT.md` still states the old 5-file business-input allowlist, while `resources/business_inputs/README.md` now lists 10 current business inputs and the verifier accepts that newer list. | Old report lists only `BI科目匹配表.xlsx`, `部门架构维护模版.xlsx`, `费用整体框架.xlsx`, `产品树20260505v4.xlsx`, and `26年一季度全行经营简报_脱敏版.pptx`; current README additionally lists `产品指标.xlsx`, `机构产品数据录入_B01_业务状况表_2026 (1).xlsx`, `机构及产品指标（公式配置） - v03.xlsx`, `机构汇总指标.xlsx`, and `科目和层级表.xlsx`. | Update or supersede `WORKTREE_ORGANIZATION_REPORT.md` so future reviewers do not read the old 5-file list as still authoritative. |
| P2 | Module depth | The high-risk architecture gates pass, but the largest org-product modules are still large. | `apps/api/app/routers/org_product_helpers.py` is 3106 lines; `apps/web/src/app/components/org-product/OrgProductMetricContent.tsx` is 5191 lines. | Not a completion blocker if the goal is worktree cleanup and acceptance gates, but keep this as the next maintainability target. Split helpers and the metric component by concern in a separate refactor. |
| P2 | Local hidden tooling dirs | Root still contains local hidden directories such as `.qoder`, `.superpowers`, and `.vscode`; they are not in the persistent README root list, and the verifier currently accepts the worktree. | `ls -1A` shows these dirs; `README.md` persistent root list does not include them; verifier still returns `ok`. | Treat them as local tooling state. If a source package is prepared, ensure packaging excludes them unless explicitly needed. |

## Second Review Commands Run

```bash
ls -1A
find resources/business_inputs -maxdepth 1 -type f -print | sort
find resources/download_template -maxdepth 1 -type f -print | sort
find var -maxdepth 1 -mindepth 1 -print | sort
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile apps/api/scripts/verify_worktree_organization.py apps/api/scripts/verify_current_database_inventory.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python apps/api/scripts/verify_worktree_organization.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npx tsc -p apps/web/tsconfig.json --noEmit
npm run build
git diff --check
rg -n '("/api/|`/api/|\x27/api/)' apps/web/src/app apps/web/src/main.tsx -g '*.tsx' -g '*.ts'
find apps/api -path 'apps/api/.venv' -prune -o -type d -name '__pycache__' -print | sort
```
