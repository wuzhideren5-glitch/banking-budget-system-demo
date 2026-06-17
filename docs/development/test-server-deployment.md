# 测试服务器部署说明

## 目录结构

- `apps/web/`：React + Vite 前端。
- `apps/api/`：FastAPI 后端。
- `resources/download_template/`：页面下载和导入依赖的模板。
- `resources/knowledge_base/`：Agent 语义、提示词、同义词、指标定义和运行配置。
- `resources/business_inputs/`：仅交付运行依赖的少量业务文件，不默认包含全部业务底稿。
- `var/data/`：SQLite 数据库和必要运行数据；历史备份、日志和生成报告输出不随精准包交付。
- `docs/`：PDD、数据库、接口/规则、设计规范和验收文档。
- `var/output/acceptance/`：本地验收材料目录；精准交付包默认不包含，除非打包时显式启用。

## 依赖安装

前端依赖：

```bash
npm install --include=optional
```

不要从本机或其他系统复制 `node_modules/` 到服务器；Linux 服务器必须在服务器本机安装依赖，否则 Vite/Rollup 可能缺少 `@rollup/rollup-linux-x64-gnu` 等平台原生包。

后端依赖：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.txt
```

如果服务器已安装 `uv`，也可以跳过手动创建 `.venv`，启动脚本会优先尝试 `uv run`。

## 启动和停止

启动：

```bash
bash start.sh
```

`start.sh` 在支持 `screen` 的环境中优先使用两个 detached screen 会话托管服务：

- `banking-budget-api`：后端 FastAPI，监听 `8009`。
- `banking-budget-web`：前端 Vite，监听 `8443`。

重复执行 `bash start.sh` 会识别已有 screen 会话并跳过，不会重复启动第二套服务。如果端口已经被外部进程占用，脚本会提示对应端口已占用。

`start.sh` 会在后端启动前执行 `apps/api/scripts/prepare_deploy_generated_paths.py`，
把 Smart Report/PPT 模板路径规范到当前解压目录的 `var/data/`。精准交付包默认不包含
`var/data/smart_report_outputs/` 历史生成物，因此历史报告/PPT 实例的下载路径会被清空；
部署后如需下载这些报告，请在系统内重新生成。

停止：

```bash
bash stop.sh
```

`stop.sh` 会先停止上述 screen 会话，再按 pid 文件和端口监听做兜底清理；可处理 screen 会话退出后子进程仍占用 `8009` / `8443` 的情况。

启动后访问：

- 前端：`http://127.0.0.1:8443/`
- 测试域名：`http://guanheng.webank.com:8443/`
- 后端：`http://127.0.0.1:8009/`
- API 文档：`http://127.0.0.1:8009/docs`

## 端口说明

- `8443`：测试服务器前端 Vite 服务端口。
- `8009`：后端 FastAPI 服务端口。
- 前端 `/api` 请求通过 `apps/web/vite.config.ts` 代理到 `http://127.0.0.1:8009`。
- 后端跨域配置读取 `apps/api/.env`。

## 常见排查

- 如果浏览器显示 `Internal Server Error`，先查看 `var/logs/backend.log`。
- 如果前端页面能打开但接口返回 `Not Found`，检查后端是否在 `8009` 启动，以及前端代理是否仍指向 `http://127.0.0.1:8009`。
- 如果需要查看或手工关闭服务会话，可执行：

```bash
screen -ls
screen -S banking-budget-api -X quit
screen -S banking-budget-web -X quit
```

- Playwright 端到端验收默认复用 `bash start.sh` 已启动的服务：

```bash
npx --prefix apps/web playwright test full-user-journey.spec.ts --config apps/web/playwright.config.ts
```

只有在希望 Playwright 自己启动服务时才设置 `E2E_START_SERVERS=1`；若当前 `8009` / `8443` 已经有服务运行，不要打开该开关。
- 如果提示 `Cannot find module '@rollup/rollup-linux-x64-gnu'`，删除前端依赖后在服务器本机重新安装：

```bash
rm -rf node_modules apps/web/node_modules
npm install --include=optional
```

- 如果提示其他依赖缺失，重新执行 `npm install --include=optional` 和 `pip install -r apps/api/requirements.txt`。
- 如果端口被占用，先执行 `bash stop.sh`，再检查本机是否已有其他进程占用 `8443` 或 `8009`。
