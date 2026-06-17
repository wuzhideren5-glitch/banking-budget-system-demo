# Codex Review Comments: Qoder Stability Fix Report

Date: 2026-06-17
Reviewer: Codex
Reviewed report: `.scratch/org-product-metric-tree-review/qoder_stability_fix_report_20260617.md`

## Overall Verdict

Not complete.

Qoder fixed a meaningful part of the org-product metric runtime path, and the narrower org-product related test subset passed. However, the work is not ready to accept as "completed" because the report overclaims full test success and the change reintroduced worktree/package artifacts that violate the project organization gates.

## What Passed

- Org-product focused subset passed: `73 passed, 36 warnings`.
- Current live DB inventory passed: `verify_current_database_inventory.py` reported all checks `ok`.
- Frontend typecheck passed: `npx tsc -p apps/web/tsconfig.json --noEmit`.
- Frontend production build passed: `npm run build`.
- Python compile check for the main modified backend files passed.
- `git diff --check` passed.
- Bootstrap request reduction is implemented in code: `/api/org-product-metrics/bootstrap` returns `entities`, and the frontend init now awaits only bootstrap + table catalog.

## Findings

| Priority | Block | Issue | Evidence | Recommendation |
| --- | --- | --- | --- | --- |
| P0 | Verification claim | The report claims 100% test success, but the modified DB/schema and inventory tests fail. | Report says `104/104` and "所有修改均通过完整测试验证". Re-running the modified DB/schema and inventory tests gives `22 failed, 61 passed`. The broader modified-test run gives `22 failed, 141 passed`. | Do not accept the report as complete until Qoder provides a reproducible test command that passes, or fixes the failing tests and code contracts. |
| P0 | Worktree stability | The stability fix reintroduced retired/root artifacts and fails the worktree organization gate. | `verify_worktree_organization.py` fails with root `.DS_Store`, root `releases`, root `scripts`, `apps/resources`, `apps/var`, and unindexed `.agents/skills/qoder-deploy-package`. | Remove or archive root release artifacts, move or delete root scripts, remove retired `apps/var` and `apps/resources`, update skill index or remove the local skill. Then rerun the verifier. |
| P0 | Runtime data path regression | Qoder created live DB copies under retired `apps/var/data`. | Current files include `apps/var/data/common.db`, `apps/var/data/budget_2026.db`, `apps/var/data/compare.db`, and `apps/var/data/common.db.bak.20260617`. The report itself names the backup path as `apps/var/data/common.db.bak.20260617`. | This project's current runtime DB root is `var/data`, not `apps/var/data`. Move any truly needed backup to the correct archive/runtime location and delete the retired path from active worktree. |
| P1 | Schema migration robustness | `metric_table_name` migration assumes `functional_group_code` exists after adding missing columns, which breaks old/minimal schemas. | `runtime_metric_tree.py` adds `metric_table_name` and immediately executes `SET metric_table_name = functional_group_code`; tests with old metric-node schemas fail with `sqlite3.OperationalError: no such column: functional_group_code`. | Guard the migration on the pre/post column set, or add `functional_group_code` before referencing it. Preserve the intended "reject old schema" behavior with a controlled RuntimeError instead of raw SQLite errors. |
| P1 | Test maintenance | Some updated tests have broken source-file paths. | `test_verify_current_database_inventory_script.py` sets `SCRIPT = Path(__file__).resolve().parent / "scripts" / "verify_current_database_inventory.py"`, which resolves to `tests/scripts/scripts/...`. `test_db_bootstrap_schemas.py` reads `tests/db/app/...` instead of the real `app/...`. | Fix test path anchors to repo/API root, for example `Path(__file__).resolve().parents[2]`, before using the tests as evidence. |
| P1 | Field semantic split incomplete | Some consumers still include `functional_group_code` in runtime matching paths. | `expense_forecast_metric_sources.py` still matches indicator against `n.functional_group_code`; `budget_simulation_metrics.py` still loads and returns `functional_group_code`. This may be okay as compatibility, but it contradicts the report's statement that all table-name filtering moved to `metric_table_name`. | Either narrow `functional_group_code` to function-family matching only and document it, or remove it from table-name/indicator matching paths. Add tests distinguishing table name vs functional group code. |
| P2 | Local skill index | New `.agents/skills/qoder-deploy-package` is unindexed. | `.agents/skills/README.md` exact skill list does not include `qoder-deploy-package`; verifier flags `agents-skill-missing-from-index`. | Add it to the exact list only if it is a deliberate repo-local skill; otherwise remove it from the source worktree. |

## Commands Run

```bash
nl -ba .scratch/org-product-metric-tree-review/qoder_stability_fix_report_20260617.md
git status --short --untracked-files=normal
find apps/var apps/resources scripts -maxdepth 3 -type f -print
find releases scripts apps/var apps/resources .agents/skills/qoder-deploy-package -maxdepth 3 -print
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python apps/api/scripts/verify_worktree_organization.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache PYTHONPATH=. .venv/bin/python -m pytest -q tests/org_product/test_org_product_metric_runtime_refs.py tests/org_product/test_org_product_single_metric_entry_labels.py tests/org_product/test_runtime_metric_refs.py tests/org_product/test_runtime_ref_export.py tests/agent/test_agent_product_intent_catalog.py tests/budget/test_budget_simulation.py tests/expense/test_expense_forecast_metric_sources.py
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache PYTHONPATH=. .venv/bin/python -m pytest -q tests/db/test_db_bootstrap_schemas.py tests/scripts/test_verify_current_database_inventory_script.py
npx tsc -p apps/web/tsconfig.json --noEmit
npm run build
PYTHONPYCACHEPREFIX=/tmp/banking-budget-pycache python -m py_compile apps/api/app/db_bootstrap/runtime_metric_tree.py apps/api/app/services/org_product_metric_runtime_sync.py apps/api/app/services/org_product_metric_runtime_snapshot.py apps/api/app/routers/org_product_metric_config.py
git diff --check
```
