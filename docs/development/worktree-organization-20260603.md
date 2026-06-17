# Worktree Organization Guide

本文记录当前工作树组织规范和目录结构约定。工作树门禁脚本 `apps/api/scripts/verify_worktree_organization.py` 依据本文和 `docs/product/Banking_Budget_Files.md`、`docs/development/current-system-map.md` 中的精确清单行验证目录合规性。

## 核心规则

1. 根目录只保留 ALLOWED_ROOT_ENTRIES 中的持久入口；本地工具目录（`.git`, `.qoder`, `.superpowers`, `.vscode`, `.venv`, `node_modules`）标记为 LOCAL_ONLY。
2. `var/` 只保留 ALLOWED_VAR_ENTRIES 中的运行时目录；非运行时产物归入 `archive/`。
3. 后端 `apps/api/app/` 顶层模块按职责拆入 `agent/`、`core/`、`integrations/` 子包；路由、服务和 db_bootstrap 保持扁平。
4. 前端 `apps/web/src/app/components/` 按业务域分子目录（`agent/`, `analysis/`, `budget/`, `business/`, `common/`, `expense/`, `org-product/`, `system/`）；`apps/web/src/lib/` 按业务域分子目录（`agent/`, `budget/`, `business/`, `expense/`, `org-product/`, `shared/`, `system/`）。
5. 所有"精确文件清单"行必须与磁盘实际文件同步；重组代码后必须同步更新文档清单。
6. 退休根入口（如 `releases/`、旧 `src/`、旧 `backend/`）不得作为活仓入口恢复。
