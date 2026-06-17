# CTO 交付说明：20260602 精简完整包

## 包用途

本包用于内部测试服务器或其他组员电脑验证当前银行预算项目。它是敏感内部交付包，包含运行配置、SQLite 数据库、必要配置表、前端构建产物和启动脚本；接收方安装依赖后即可按说明启动验证。

## 端口约定

- 后端 FastAPI：`8009`
- 前端 Vite：`8443`
- 前端默认代理后端：`http://127.0.0.1:8009`

历史 `5177` 是旧本地开发端口，本包以 `8443/8009` 为准。

## 主要包含内容

- `apps/`：当前前后端源码。
- `apps/api/.env`：后端运行环境变量，请按接收方环境检查敏感配置。
- `apps/web/dist/`：已构建前端产物，便于静态部署或快速验收。
- `var/data/common.db`、`var/data/budget_2025.db`、`var/data/budget_2026.db`、`var/data/compare.db`：当前运行数据库。
- `resources/download_template/`：用户导入/下载模板。
- `resources/knowledge_base/`：智能体语义、提示词、字典和运行配置。
- `resources/business_inputs/科目和层级表.xlsx`：科目/层级配置来源。
- `resources/business_inputs/费用整体框架.xlsx`：费用整体框架配置来源。
- `resources/business_inputs/部门费用执行.xls`：费用执行明细导入样例/业务输入。
- `resources/business_inputs/部门架构维护模版.xlsx`：部门架构维护模板。
- `resources/business_inputs/BI科目匹配表.xlsx`：BI 映射维护初始化来源，当前规则已落库，Excel 用于复核和重建。
- `resources/business_inputs/26年一季度全行经营简报_脱敏版.pptx`：智能报告/PPT 相关必要业务输入。
- `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md`、`CHANGELOG.md`：项目说明、PDD/PRD/设计规范和变更记录。
- `start.sh`、`stop.sh`：启动/停止脚本。

## 明确排除内容

- `node_modules/`、`.venv/`：可重建依赖，不跨机器拷贝。
- `.git/`、`.scratch/`、`.agents/`：本机开发/代理状态。
- `archive/`、`releases/`、历史 TeamSubmit/回退包：历史包不进入本次交付。
- `var/logs/`、`var/pids/`、`var/output/`、`var/data/backups/`：运行噪声、日志、PID、备份和输出。
- root 临时 Excel，例如重复下载的费用明细和 BI 表副本：已将必要版本归档到 `resources/business_inputs/`。

## 接收方启动步骤

1. 解压 zip 到目标目录。
2. 安装前端依赖：

```bash
npm install --include=optional
```

Linux x64 测试服务器需要 Rollup/Vite 的平台可选包，例如 `@rollup/rollup-linux-x64-gnu`；不要从 macOS 拷贝 `node_modules/` 到 Linux。

3. 准备 Python 后端环境，并安装 `apps/api/pyproject.toml` 所需依赖。若使用项目已有约定，可在根目录创建 `.venv` 后安装。
4. 启动服务：

```bash
bash start.sh
```

5. 打开：

```text
http://127.0.0.1:8443/
```

6. 停止服务：

```bash
bash stop.sh
```

## 验收建议

- 确认 `http://127.0.0.1:8443/` 能打开前端。
- 确认后端 `http://127.0.0.1:8009/docs` 可访问。
- 重点验证费用预算管理、BI 映射维护、费用预测规则、费用预算执行报表、模拟测算、成本收入比等近期合并模块。
- 费用执行明细导入由用户 Excel 导入；其他主要配置规则已在数据库中提供当前版本。

