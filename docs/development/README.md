# Development Docs Index

本目录只放当前开发、架构、部署、工作树和数据库运行事实文档。历史交付说明、旧迁移过程、旧产品方案和旧运行快照不放在这里；需要追溯时去 `archive/` 或 `.scratch/architecture-deep-clean/`。

当前 `docs/development/` 开发文档精确清单（工作树门禁读取）：`active-worktree-manifest.md`, `current-database-inventory.md`, `current-system-map.md`, `current-worktree-status.md`, `department-expense-module-map.md`, `org-product-data-account-alignment.md`, `release-packaging.md`, `repo-layout.md`, `test-server-deployment.md`, `worktree-organization-20260603.md`。

## Reading Order

1. [`active-worktree-manifest.md`](active-worktree-manifest.md): 当前工作树入口清单，先判断一个文件属于现役、历史、运行态还是本地缓存。
2. [`current-worktree-status.md`](current-worktree-status.md): 当前物理工作树和 `git status` 解释，专门处理旧根目录 deleted 与新入口 untracked 同时存在的状态。
3. [`repo-layout.md`](repo-layout.md): 仓库目录规则，新文件应该放到哪里、不应该恢复哪些旧根目录。
4. [`current-system-map.md`](current-system-map.md): 当前前端导航、后端路由、service、db bootstrap、数据库和验证规则的事实地图。
5. [`department-expense-module-map.md`](department-expense-module-map.md): 部门费用预算管理模块的页面、API、service 和数据库表关系图。
6. [`current-database-inventory.md`](current-database-inventory.md): 当前 live SQLite 表、行数、归属 Module 和退休表检查结果。
7. [`worktree-organization-20260603.md`](worktree-organization-20260603.md): 2026-06-03 工作树整理规则、现役入口和历史隔离标准。
8. [`release-packaging.md`](release-packaging.md): 内部完整运行包和源码审核包的包含/排除规则与交付门禁。
9. [`test-server-deployment.md`](test-server-deployment.md): 本地/测试服务器部署、端口和启动验证说明。

## Rules

- 新增开发文档时，必须在本文精确清单登记；归档或删除开发文档时，必须从该清单移除旧文件名。
- 当前开发事实以 `apps/`、`docs/`、`resources/`、`var/data/*.db` 和 `CONTEXT.md` 为准，不以 `archive/` 中的旧包或旧说明为准。
- 数据库、前后端关系或工作树边界变化时，同步更新 `current-system-map.md`、`department-expense-module-map.md`、`current-database-inventory.md`、`repo-layout.md` 或 `active-worktree-manifest.md` 中对应的当前事实。
- 本目录文档中的相对链接必须指向真实文件；移动或归档文档时同步修正入口链接。
