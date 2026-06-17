---
name: qoder-deploy-package
description: 打包银行预算系统为可部署 ZIP 包（含预构建前端、数据库、.env、测试、文档），自动校验完整性。Use when 用户要求打包、部署、发布、交付、导出系统，或提到 deploy/package/ship/release/交付/部署包/上线。
---

# Qoder 部署打包

## Quick start

```bash
bash scripts/package_deploy.sh
```

产物：`releases/qoder-banking-budget-<时间戳>.zip`

## 工作流

### 1. 执行打包

```bash
# 完整打包（含数据库 + .env）
bash scripts/package_deploy.sh

# 不含数据库（服务器已有数据时）
bash scripts/package_deploy.sh --skip-data

# 不含 .env（需手动配置时）
bash scripts/package_deploy.sh --skip-env
```

### 2. 打包前检查清单

打包脚本自动执行以下步骤，如需手动排查：

- [ ] 前端构建成功：`cd apps/web && npm run build`，确认 `dist/` 存在
- [ ] 后端无语法错误：`cd apps/api && python3 -c "import app.main"`
- [ ] TypeScript 编译通过：`npx tsc -p apps/web/tsconfig.json --noEmit`
- [ ] `.env` 文件存在：`apps/api/.env`

### 3. 必含文件校验（15 项）

脚本自动校验，全部 ✓ 才算通过：

| 类别 | 校验项 |
|------|--------|
| 前端预构建 | `apps/web/dist/index.html` |
| 前端样式 | `apps/web/tailwind.config.cjs`, `apps/web/postcss.config.cjs` |
| 前端 TS | `apps/web/tsconfig.node.json` |
| npm workspace | `package.json`, `package-lock.json` |
| 环境变量 | `apps/api/.env`, `apps/api/.env.example` |
| 锁文件 | `apps/api/uv.lock` |
| 测试 | `apps/api/tests/`, `apps/web/e2e/` |
| 文档 | `docs/` |
| 运维 | `start.sh`, `stop.sh`, `DEPLOY_GUIDE.md` |

### 4. 部署到服务器

```bash
scp releases/qoder-banking-budget-*.zip user@server:/opt/
ssh user@server
cd /opt && unzip qoder-banking-budget-*.zip
cd qoder-banking-budget-*
vim apps/api/.env    # 修改环境变量
bash start.sh         # 启动
```

## 打包内容架构

```
qoder-banking-budget-<ts>/
├── apps/api/
│   ├── app/            # FastAPI 后端源码
│   ├── scripts/        # 运维脚本（验证、修复等）
│   ├── tests/          # 后端测试（~600 个）
│   ├── .env            # 环境变量（⚠ 密钥）
│   ├── .env.example    # 配置模板
│   ├── uv.lock         # 依赖锁版本
│   ├── pyproject.toml  # Python 依赖声明
│   └── run_server.py   # 启动入口
├── apps/web/
│   ├── src/            # React 前端源码
│   ├── dist/           # 预构建产物（开箱即用）
│   ├── e2e/            # Playwright 端到端测试
│   ├── tailwind.config.cjs  # Tailwind CSS 配置
│   ├── postcss.config.cjs   # PostCSS 配置
│   ├── tsconfig.node.json   # TS Node 配置
│   └── vite.config.ts       # Vite 构建 + 代理配置
├── docs/               # 架构/产品/开发文档
├── resources/          # 模板、知识库、下载模板
├── var/data/           # SQLite 数据库（⚠ 业务数据）
├── package.json        # npm workspace 根配置
├── package-lock.json   # npm 依赖锁
├── start.sh / stop.sh  # 一键启停
└── DEPLOY_GUIDE.md     # 3 步部署指南
```

## 关键设计决策

1. **预构建前端**：`npm run build` 在打包时执行，服务器无需安装 Node.js 依赖
2. **直接 zip 源目录**：不复制到临时目录，节省磁盘空间
3. **Python 重命名**：用 `zipfile` 模块处理 zip 内文件名调整（DEPLOY_GUIDE.md、前缀目录）
4. **uv.lock 必含**：确保服务器 `uv sync` 依赖版本确定性
5. **完整性校验**：打包后自动验证 15 项关键文件，防止遗漏

## 常见问题

| 问题 | 解决 |
|------|------|
| 磁盘不足 | 用 `--skip-data` 跳过数据库；清理 `releases/` 旧包 |
| 前端构建失败 | 检查 `npm install` 是否正常、TypeScript 编译是否通过 |
| zip 内文件无前缀 | 脚本 `[final]` 步骤自动添加 `qoder-banking-budget-<ts>/` 前缀 |
| .env 缺失 | 确认 `apps/api/.env` 存在，或用 `--skip-env` 后手动创建 |

## 参考

- 打包脚本源码：[scripts/package_deploy.sh](scripts/package_deploy.sh)
- 启停脚本：[start.sh](start.sh) / [stop.sh](stop.sh)
