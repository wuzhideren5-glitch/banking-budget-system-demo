# 交付说明

**提交人**：Codex（PMO / CTO 交付包整理）  
**日期**：2026-05-09  
**主题**：完整项目交付包（含 `.env`、`data`、依赖 Excel 表）

---

## 产物清单

| 文件 | 说明 |
|------|------|
| `releases/CTO_20260509_完整交付包_含env_data_excel.zip` | 当前主干完整交付包，包含源码、配置、PDD、知识库、数据目录、导入模板和依赖 Excel 表 |
| `releases/CTO_20260509_完整交付包_含env_data_excel_dist.zip` | 在上述完整包基础上额外包含最新前端构建产物 `dist/` |
| `交付说明_CTO_20260509_完整交付包_含env_data_excel.md` | 本文件 |

---

## 打包范围

本包用于项目 PMO / CTO 级完整归档与迁移交接，按本次要求**刻意包含**以下内容：

- `backend/.env` 与 `backend/.env.example`
- `data/` 目录下当前 SQLite 数据库、备份库与调试数据
- 根目录依赖/业务 Excel、xls、csv 文件
- `download_template/` 下所有导入模板
- 前后端源码、后端测试脚本、知识库、PDD 文档、配置文件和 `CHANGELOG.md`
- `dist/` 前端静态构建产物（`*_含dist.zip` 版本包含）

本包**刻意排除**以下内容：

- `node_modules/`
- `.venv/`
- `dist/`
- `.git/`
- `releases/` 历史包（避免递归打包）
- 团队成员原始提交目录（如 `ZLC_...`、`panpan_...`），当前主干已完成合并
- `__pycache__/`、`*.pyc`、运行日志、PID、cookie 等临时文件

> 注：`CTO_20260509_完整交付包_含env_data_excel_dist.zip` 按后续要求保留 `dist/`，用于静态部署或验收归档；不含 `dist` 的版本保留给源码交接场景。

---

## 当前合并状态

- 已合入预算预测驱动因素模块。
- 已合入费用管理五大核心模块。
- 已合入工作台和参数模板模块。
- 已更新 System PDD、Database PDD、Files.md 与 CHANGELOG。
- 当前前端确认地址：`http://127.0.0.1:5177/`
- 当前后端默认地址：`http://127.0.0.1:8003/`

---

## 注意事项

- 本包包含 `.env`、SQLite 数据库和业务 Excel，属于敏感完整交付包，请按内部受控范围分发。
- 接收方无需使用本机 `.venv` 或 `node_modules`，应自行执行依赖安装。
- 后端建议使用 Python 3.10+，当前验证环境为项目 `.venv` Python 3.12。
- 前端依赖按 `package-lock.json` 安装，后端依赖按 `backend/requirements.txt` 安装。
