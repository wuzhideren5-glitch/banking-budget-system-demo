# Banking Budget Monorepo

银行预算系统采用 monorepo 结构，按多人协作职责拆分当前产品代码、受控业务资源、本地运行状态和历史交付归档。

当前仓库根目录持久入口精确清单（工作树门禁读取）：`.agents`, `.gitignore`, `.ignore`, `.scratch`, `AGENTS.md`, `CHANGELOG.md`, `CONTEXT.md`, `README.md`, `apps`, `archive`, `docs`, `package-lock.json`, `package.json`, `resources`, `skills-lock.json`, `start.sh`, `stop.sh`, `var`。

## Directory Layout

- `apps/web/`: 前端 Vite + React 应用。
- `apps/api/`: 后端 FastAPI 应用、维护脚本和 smoke 验证脚本。
- `resources/knowledge_base/`: Agent 知识库、提示词、语义映射等受控资源。
- `resources/download_template/`: Web 下载和导入使用的 Excel 模板。
- `resources/business_inputs/`: 业务底稿、一次性导入材料和参考文件；运行时业务配置以数据库和显式上传导入为准，不应从该目录自动读取。
- `var/`: 本地数据库、日志、pid 和生成输出；默认不提交。
- `docs/product/`: 当前产品、数据库、规则和 UI 文档。
- `docs/product/README.md`: 产品文档阅读顺序、当前辅助文档和历史文档状态。
- `docs/development/active-worktree-manifest.md`: 当前工作树入口清单，明确哪些目录是当前开发入口，哪些只作历史归档。
- `docs/development/current-system-map.md`: 当前代码、数据库、前后端入口和退休口径的事实地图。
- `docs/development/test-server-deployment.md`: 测试服务器部署和排查说明。
- `.agents/`: 当前随仓库保留的本地 Agent skill 资产；清单见 `.agents/README.md` 和 `.agents/skills/README.md`。
- `archive/`: 历史交付包、release 包、旧运行快照、团队提交 patch 和迁移前产物。

## Common Commands

```bash
npm install
npm run dev
npm run build
npm run verify:delivery
npm run verify:delivery:source
npm run dev:backend:lan
npm run api:smoke
```

```bash
bash start.sh
bash stop.sh
```

固定端口：测试服务器前端端口 `8443`，后端开发端口 `8009`；前端 `/api` 代理固定指向 `http://127.0.0.1:8009`。`start.sh` 在支持 `screen` 的环境中使用 `banking-budget-api` / `banking-budget-web` 两个 detached screen 会话托管服务；`stop.sh` 会停止对应 screen，并兜底清理占用 `8009` / `8443` 的孤儿监听进程。

Playwright 端到端验收默认复用已启动的 `8009` / `8443`：

```bash
npx --prefix apps/web playwright test full-user-journey.spec.ts --config apps/web/playwright.config.ts
```

仅在需要 Playwright 自己拉起服务时设置 `E2E_START_SERVERS=1`；已有服务运行时不要打开该开关。

交付前按目标包类型执行交付门禁：内部完整运行包使用 `npm run verify:delivery`，源码审核包使用 `npm run verify:delivery:source`。内部完整运行包只允许 `var/data` 作为 live 数据目录；源码审核包不得包含 `.env`、数据库或前端 `dist`。

## Collaboration Rules

- 当前产品代码只改 `apps/web` 和 `apps/api`。
- 开发前先读 `docs/development/active-worktree-manifest.md`；不要从根目录旧 `src/`、旧 `backend/`、旧 `data/`、旧团队包或旧 release 包继续接代码。
- 可复用业务资源放 `resources`，不要散落在仓库根目录。
- 本地数据库、日志、导出文件和临时文件放 `var`，不要提交。
- 历史同事包、release 包、交付说明和旧导入工作簿只放 `archive`，不要在仓库根目录继续开发或当作当前运行入口。
- 新增目录或跨目录职责变化时，同步更新 `docs/development/repo-layout.md`。
- 新增或归档根目录持久入口时，同步维护本文的根目录精确清单；`.git`、`.venv`、`node_modules` 等本机状态不进入该清单。
- 业务口径、数据库表或导航入口变化时，同步更新 `CONTEXT.md` 和 `docs/development/current-system-map.md`。
