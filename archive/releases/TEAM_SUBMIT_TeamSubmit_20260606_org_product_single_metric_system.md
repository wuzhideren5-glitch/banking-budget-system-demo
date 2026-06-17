# 团队提交包说明：TeamSubmit_20260606_org_product_single_metric_system

生成时间：2026-06-06 00:29:38

## 本次新增内容

本次新增内容：合并 bin 机构及产品指标体系，并将数据科目表直接重构为同一套机构及产品指标体系；修正机构及产品指标表 9 个同码冲突，源体系冲突归零；数据科目三表重建为 node=1687、data_account=1252、binding=1252，保留潘潘 99 保护区 202 个节点；预算展示配置按新体系自动安全回挂 508 条，剩余同名多义或旧展示层级项留待业务确认；新增重构、冲突修复、预算展示回挂脚本和 PDD/CHANGELOG/CONTEXT 说明。

## 包含范围

- 当前主线源码：`apps/`（monorepo 项目），并兼容旧结构 `src/`、`backend/`
- 项目规范与文档：`Design docs/`、`docs/`、`AGENTS.md`、`CONTEXT.md`、`CHANGELOG.md`
- 安装与构建配置：`package.json`、`package-lock.json`、`vite.config.ts`、`tsconfig*.json`、Tailwind/PostCSS 配置
- 启停与部署说明：`start.sh`、`stop.sh`、`测试服务器部署说明.md`（如存在）
- 业务参考输入：`resources/business_inputs/`（仅限本次提交确实依赖的参考数据）

## 明确不包含

- 敏感环境文件：`.env`、`backend/.env`、`apps/api/.env`
- 本地运行数据与数据库快照：`data/`、`backend/data/`、`apps/*/data/`、`var/data/`
- 依赖与运行环境：`node_modules/`、`.venv/`、`.venv312/`、`backend/.venv/`
- 构建产物：`dist/`（除非本次显式指定 `--include-dist`）
- 历史交付包：`releases/`
- 原始同事源码包：不依赖固定命名；会同时按目录内容特征识别并排除独立源码包/压缩包目录
- 运行噪声：日志、pid、cookie、缓存、Excel 临时锁文件

## 接收方恢复方式

1. 解压团队提交包。
2. 执行 `npm install` 恢复前端依赖。
3. 后端按 `backend/requirements.txt` 或 `backend/pyproject.toml` 恢复依赖。
4. 如需真实数据、`.env` 或 DB，请使用 CTO 完整交付包，不要从团队提交包中寻找。
