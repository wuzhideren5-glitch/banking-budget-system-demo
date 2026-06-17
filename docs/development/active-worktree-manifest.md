# Active Worktree Manifest

本文是当前工作树的入口清单。后续开发先按本文定位文件，避免把历史交付包、旧前端根目录、旧 Excel 或旧迁移脚本重新混进当前产品代码。开发文档阅读顺序见 `docs/development/README.md`。

## Current Source Of Truth

| Area | Current location | What belongs here |
| --- | --- | --- |
| Frontend application | `apps/web/` | 当前 Vite + React 前端、页面组件、前端 API client、view model、样式和前端构建配置。 |
| Backend application | `apps/api/` | 当前 FastAPI 路由、service Module、db bootstrap、维护脚本、后端测试和 smoke 脚本。 |
| Product and architecture docs | `docs/`, `CONTEXT.md` | 当前业务语言、数据库合同、前后端关系、产品规则、部署说明和代码目录说明。 |
| Controlled business resources | `resources/` | 当前可复用下载模板、业务输入底稿、Agent 知识库和受控提示词资源。 |
| Local runtime state | `var/` | 本机数据库、日志、pid、运行输出和数据库备份；默认不提交。 |
| Architecture work notes | `.scratch/` | 当前仍可继续评审、拆分或验证的重构审计、issue 草稿、局部设计记录和验证备注。已退休 PRD 不放在这里。 |

当前必需材料的细分入口见 `docs/development/worktree-organization-20260603.md#current-required-inventory`；当前物理工作树和 `git status` 的解释见 `docs/development/current-worktree-status.md`；部门费用预算管理模块的页面、API、service 和数据库表关系见 `docs/development/department-expense-module-map.md`。如果一个文件无法归入这些清单，先按历史材料处理，放入 `archive/` 或运行态 `var/`，不要直接放回当前源码、当前文档或当前模板目录。

## Current Entry Decision Checklist

整理工作树时先按下列顺序判断，不要把历史材料和当前实现混在一起：

1. 能被当前导航、后端路由、数据库 inventory 或模板 allowlist 直接引用的，保留在当前入口：`apps/`、`docs/`、`resources/`、`.scratch/`。
2. 仅本机运行需要、可重新生成或随环境变化的，保留在运行态：`var/`。
3. 只用于追溯旧交付、旧迁移、旧样例、旧运行快照或旧团队提交的，保留在历史区：`archive/`。
4. 如果一个文件提到旧 `report_account`、旧 `report_accounts`、旧 `BI科目维护`、旧 `driver_*`、旧预测工作台或旧根目录 `src/` / `backend/` / `data/`，默认按历史材料处理；确需恢复功能时，必须先按当前 `CONTEXT.md`、当前 DB inventory 和 `apps/*` Module 重写，再接回当前入口。

验收时优先检查当前入口是否完整、文档是否与 `apps/web/src/app/workspaceCatalog.tsx` 和当前数据库一致；不要把 `archive/` 里的旧包、旧说明或旧库表当作当前功能缺失。

## 2026-06-03 Worktree Boundary

当前工作树已按“现行产品 / 受控资源 / 本机运行态 / 历史归档”分开：

- 现行产品代码只看 `apps/web/` 和 `apps/api/`。
- 当前产品、数据库、前后端关系和测试服务器说明只看 `docs/` 与 `CONTEXT.md`。
- 当前运行库表和行数盘点看 `docs/development/current-database-inventory.md`；不要凭旧包或 archive DB 判断当前表是否还有效。
- 当前可下载模板、业务底稿和 Agent 知识资源只看 `resources/`。
- 当前本机数据库、日志、pid 和导出输出只看 `var/`；其中 live SQLite 以 `var/data/*.db` 为准。
- 历史同事包、旧 release、旧交付说明、旧迁移脚本、旧 Hermes 计划材料、旧 `.scratch` 方案和旧运行快照只看 `archive/`，不能作为当前开发入口。
- 现场数据库结构改造先备份到 `var/data/backups/<topic>/`，再修改 live DB。2026-06-03 的费用执行明细 BI-AI 源字段重命名前备份为 `var/data/backups/schema_contract_20260603/common_before_bi_ai_source_column_rename.db`；当前 `common.db.expense_actual_detail_raw` 已使用 `bi_ai_source_code` / `bi_ai_source_name` / `manage_department_code`。

`git status` 中大量旧根目录文件显示为 deleted，是因为旧结构已经退出当前工作树边界；这些历史材料已按类型进入 `archive/`。在验收前不要把旧 `src/`、`backend/`、`data/`、`knowledge_base/`、`download_template/`、`releases/` 或 `.hermes/` 恢复到根目录。

## Current Root Files

| File | Role |
| --- | --- |
| `README.md` | 仓库总入口和常用命令。 |
| `AGENTS.md` | Agent 协作规则和本仓 issue/domain 文档位置。 |
| `CONTEXT.md` | 当前业务词汇、数据库口径和退休口径约束。 |
| `CHANGELOG.md` | 当前主线变更日志；只记录已合入或本轮确认的主线变更，不作为历史交付包入口。 |
| `TEAM_SUBMIT_PACKAGING.md` | 当前团队源码提交包规则；用于合并审核，不是部署包或历史包入口。 |
| `package.json`, `package-lock.json` | 根级兼容命令入口；产品逻辑不得继续堆在根目录。 |
| `start.sh`, `stop.sh` | 本地启动/停止脚本。 |
| `.gitignore`, `.ignore` | 提交边界和当前代码搜索边界。 |
| `skills-lock.json`, `.agents/` | 本仓 Agent skill 配置。 |

根目录白名单由 `apps/api/scripts/verify_worktree_organization.py` 执行校验；除上表、`.scratch/`、`apps/`、`archive/`、`docs/`、`resources/`、`var/`、以及本机开发缓存 `.venv/` / `node_modules/` 外，新的根目录文件或文件夹必须先归入当前文档、当前源码、运行态或历史归档位置，不能直接留在根目录。

## Historical Material

| Historical material | Storage location | Rule |
| --- | --- | --- |
| Team submission folders | `archive/team_packages/` | 原样保存，只作追溯。需要功能时按当前 `apps/*` Module 重新接入。 |
| Release zips and rollback packages | `archive/releases/` | 只用于恢复或核对，不是当前源码入口。 |
| Delivery notes and old PDD patches | `archive/handover/` | 只能作为历史证据；当前需求以 `docs/product/`、`CONTEXT.md` 和 `current-system-map.md` 为准。 |
| Retired frontend prototypes | `archive/frontend_retired/` | 不直接恢复为当前 UI。需要时通过 `apps/web` 当前页面和 view model 重建。 |
| Old runtime databases/logs/generated files | `archive/runtime_snapshots/` | 只用于排查和恢复。当前运行库只看 `var/data/`。 |
| Legacy data-account migration scripts | `archive/handover/legacy_data_account_migrations/` | 已退休脚本，不能作为当前启动、导入或修复路径。 |
| Legacy report-account artifacts | `archive/handover/legacy_report_account_artifacts/` | 旧报告科目证据；不得恢复 `report_account` 或兼容读取入口。 |
| Legacy Hermes planning files | `archive/handover/legacy_hermes_plans_20260603/` | 旧智能报告/PPT 计划材料；不属于当前运行、构建或产品文档入口。 |
| Legacy scratch plans | `archive/handover/legacy_scratch_plans_20260603/` | 旧产品预算工作台、旧预测驱动输入和旧报告科目退役依赖材料；不得作为当前 issue tracker 入口直接实施。 |

## Do Not Recreate In Root

以下内容不应回到仓库根目录：

- `src/`、`src_from_Figma/`、旧同事项目根目录和旧前端原型。
- `backend/`、`data/`、`knowledge_base/`、`download_template/` 这些旧根目录形态。
- `.hermes/` 旧工具计划目录；当前架构审计与开发记录放 `.scratch/` 和 `docs/development/`。
- `releases/`、交付说明、TeamSubmit 包、zip 包、旧 Excel 工作簿。
- 根目录 `output/`、`outputs/`、`exports/`、日志、pid 和临时文件。
- 根目录虚拟环境或依赖缓存作为交付内容。

## Verification Rule

工作树整理后，至少执行：

```bash
git diff --check
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_worktree_organization.py
PYTHONDONTWRITEBYTECODE=1 apps/api/.venv/bin/python apps/api/scripts/verify_current_database_inventory.py
npm run verify:delivery
npx tsc -p apps/web/tsconfig.json --noEmit
npm --workspace apps/web run build
```

涉及后端服务或数据库合同时，还要执行对应 `py_compile` 和聚焦 pytest。部门费用模块当前优先看 `apps/api/test_dept_catalog_service.py`、`apps/api/test_budget_subject_catalog_service.py`、`apps/api/test_bi_department_mapping_service.py`、`apps/api/test_expense_actual_import_context.py`、`apps/api/test_expense_forecast_data_context.py` 和 `apps/api/test_expense_budget_execution_master_sync.py`。
