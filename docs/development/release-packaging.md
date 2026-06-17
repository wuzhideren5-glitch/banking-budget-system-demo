# Release Packaging

本文定义当前项目的两类交付包口径，并配套 `apps/api/scripts/verify_delivery_package.py` 做静态门禁。打包前先确认目标类型，不要把源码审核包和内部运行包混在一起。

## Package Profiles

| Profile | Use case | Runtime assets |
| --- | --- | --- |
| `source-only` | 组员提交、合并审核、代码审查 | 不包含 `.env`、SQLite 数据库、`apps/web/dist/` |
| `internal-runtime` | 内部完整运行交付、测试服务器恢复、本地验收 | 包含 `apps/api/.env`、`var/data/*.db`、`apps/web/dist/` |

## Internal Runtime Package

内部完整运行包必须包含：

- 当前源码：`apps/api/`、`apps/web/`
- 后端配置：`apps/api/.env`
- live 数据目录：`var/data/common.db`、`var/data/budget_2025.db`、`var/data/budget_2026.db`、`var/data/compare.db`
- 前端构建产物：`apps/web/dist/`
- 受控资源：`resources/download_template/`、`resources/knowledge_base/`
- 根目录入口：`README.md`、`AGENTS.md`、`CONTEXT.md`、`package.json`、`package-lock.json`、`start.sh`、`stop.sh`

内部完整运行包必须排除：

- `.git/`、`.venv/`、`.venv312/`、`node_modules/`
- `archive/`、`releases/`
- `var/logs/`、`var/pids/`、`var/output/`、`var/test-runs/`、`var/data/backups/`
- `apps/var/data/`；当前只允许 `var/data/` 作为 live 数据目录
- `__pycache__/`、Playwright 报告、测试结果、日志和 pid 文件

验证命令：

```bash
npm run verify:delivery
```

## Source Only Package

源码审核包必须包含当前功能相关的源码、文档、模板和说明，不能携带本机运行资产。数据库变更用文档、SQL 或初始化脚本说明，不能直接把本地 SQLite 快照当作变更交付。

源码审核包必须排除：

- `apps/api/.env`
- `var/data/`
- `apps/web/dist/`
- `.git/`、虚拟环境、依赖缓存、历史包、运行日志和生成输出

验证命令：

```bash
npm run verify:delivery:source
```

## Data Directory Rule

当前 live SQLite 只以 `var/data/` 为准。`apps/var/data/` 属于重复数据目录，会导致运行库口径不清、交付包膨胀和接收方误用旧库；发现后先核对是否仍有唯一内容，再归档或删除，不能继续作为当前运行入口。
