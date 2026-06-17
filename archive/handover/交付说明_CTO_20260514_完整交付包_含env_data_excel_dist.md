# CTO 完整交付包说明（2026-05-14）

本交付包为敏感内部完整包，面向 PMO/CTO 交接、测试环境发布和异机恢复验证。包内包含运行所需源码、配置、数据库、模板和业务 Excel，并包含最新构建后的 `dist/`。

## 已包含内容

- 前端源码：`src/`、`index.html`、`vite.config.ts`、`tailwind.config.cjs`、`postcss.config.cjs`、`tsconfig*.json`
- 后端源码与依赖说明：`backend/`，包含 `requirements.txt`、`pyproject.toml`、`backend/.env`
- 运行数据：`data/`，包含 `common.db`、`budget_2025.db`、`budget_2026.db`、`compare.db` 及必要备份/导出文件
- 模板与业务表：`download_template/`、根目录 `*.xlsx`、`*.xls`、`*.csv`
- 文档与规范：`Design docs/`、`docs/`、`AGENTS.md`、`CONTEXT.md`、`CHANGELOG.md`、`测试服务器部署说明.md`
- 参考资产：`src_from_Figma/`、`参考预算动因（公式）配置照片/`、根目录脱敏 PPTX
- 构建产物：`dist/`
- 启停脚本：`start.sh`、`stop.sh`

## 已排除内容

- 依赖目录：`node_modules/`、`.venv/`、`.venv312/`
- 版本与历史包：`.git/`、`releases/`
- 运行噪声：`*.log`、`*.pid`、`__pycache__/`、`*.pyc`、`.DS_Store`、cookie 文件、Excel 临时锁文件 `.~*`
- 原始同事源码包：如 `ZLC_*`、`panpan_*`、`潘潘_*`、`Codex_*` 等未作为当前主线代码直接交付

## 异机恢复步骤

1. 解压压缩包到目标目录。
2. 安装前端依赖：在项目根目录执行 `npm install`。
3. 安装后端依赖：进入 `backend/`，使用 Python 3.11/3.12 创建虚拟环境后执行 `pip install -r requirements.txt`；如使用测试服务器脚本，需先安装 `uv`，再执行 `bash start.sh`。
4. 本地开发模式推荐后端端口 `8003`、前端端口 `5177`；`vite.config.ts` 默认将 `/api` 代理到 `http://127.0.0.1:8003`。
5. 测试服务器发布模式执行 `bash start.sh`，后端端口 `8009`、前端端口 `8443`，脚本会显式设置前端代理到 `8009`。
6. 如仅需静态前端产物，可使用包内 `dist/`，但后端 API 与 `data/` 仍需按上述方式部署。

## 安全提醒

本包包含 `backend/.env`、SQLite 数据库和业务 Excel，属于敏感内部交付包。请勿外发到公开仓库、外部网盘或无权限群组。
