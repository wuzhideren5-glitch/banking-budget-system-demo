# 银行预算管理系统 — 变更日志 (CHANGELOG)

> 本文档由 AI Release Manager 自动维护。  
> 格式规范见 `.claude/skills/merge-release/SKILL.md` 阶段四。

---

## v2.3-merge (2026-05-09) — 合并工作台和参数模板

### 变更来源
- ZLC: 增加工作台和参数模板
- Codex: 在当前主干上执行增量合并，保留费用模块、预算预测驱动、智能报告与数据科目指标树等已有能力

### 变更明细
- 新增: 预测预算工作台后端概览接口与前端页面，展示开鑫贷/小小账户预测行和绑定概览
- 新增: 预算基本假设接口与参数模板维护页面，支持参数目录、参数值、规则模板和引用关系查看
- 新增: `assumption_parameter`、`assumption_value`、`assumption_rule_template`、`forecast_workbench_layout`、`forecast_line_binding` 等表的幂等建表和默认种子
- 修改: `data_account` 兼容新增 `budget_rule_code`、`budget_rule_config_json`，为后续模板绑定保留字段
- 修改: 导航树与工作区新增“预测预算工作台”“参数与模板维护”入口，权限按数据录入用户及以上开放
- 保留: 当前主线已有的费用管理、预算预测驱动、智能报告、产品层级和数据科目指标树逻辑，未用来源包旧版本覆盖

### 风险评估
- 高风险: 1 项（新增数据库表与现有 `common.db` 自愈迁移）
- 中风险: 3 项（新增 API 路由、权限映射、前后端 DTO）
- 低风险: 2 项（工作台/参数模板展示页面、PDD/文件清单记录）

### PDD 更新
- System PDD: 新增 §0.9 本轮需求变更（2026-05-09）— merge-release
- Database PDD: 新增 §0.5 本轮同步说明（2026-05-09）— merge-release
- Files.md: 追加 2026-05-09 合并摘要

### 验证
- 后端 `python -m compileall backend/app` 通过
- 后端 `PYTHONPATH=backend ./.venv/bin/python` 执行 `ensure_databases()` 通过，并确认新增表种子入库
- 后端 `app.main` 导入通过，仅有既有 LangGraph deprecation warning
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.2-merge (2026-05-08) — 合并费用管理模块与预算预测驱动增强

### 变更来源
- Kevin/Codex: 预算预测驱动因素模块与数据科目绑定增强
- Panpan: 费用管理五大核心模块

### 变更明细
- 新增: 部门预算科目维护、费用执行明细导入、费用预测表、费用预算执行报表、数据同步管理五个费用入口
- 新增: 费用管理相关表结构，包括 `budget_subject_catalog`、`expense_forecast_entry`、`expense_actual_detail_raw` 等
- 新增: 费用模块后端路由、前端页面、导航入口和权限映射
- 新增: `xlrd==2.0.1` 依赖，用于读取 `.xls` 费用执行源文件
- 修改: 预算预测驱动模块复用报告科目分类体系，并支持人工维护驱动指标-产品-数据科目绑定
- 修改: 预算预测驱动模板增加报告科目、数据科目编码、数据科目名称，导入可精确写入数据科目
- 保留: 当前主线的 `data_account.product_codes` 多产品范围表达、产品层级和预算预测驱动逻辑，未用来源包旧模型覆盖

### 风险评估
- 高风险: 3 项（新增费用预测写库、费用执行导入写库、费用相关数据库表）
- 中风险: 4 项（新增 API 路由、权限映射、导航入口、前后端 DTO）
- 低风险: 3 项（PDD、说明文档、模板与页面展示）

### PDD 更新
- System PDD: 新增 §0.8 本轮需求变更（2026-05-08）— merge-release
- Database PDD: 新增 §0.3 本轮同步说明（2026-05-08）— merge-release
- Files.md: 追加 2026-05-08 合并摘要

### 验证
- 后端 `py_compile` 通过
- 后端 `app.main` 无写库导入检查通过
- 前端 `npm run build` 通过，仅保留既有 eval/chunk size 警告

---

## v2.1 (2026-05-06) — 产品多层与Excel导入改造

### 变更来源
- ZLC: 20 项变更

### 变更明细
- 新增: `product_codes TEXT` 字段替代 `applies_to_all_products` 布尔值，支持"全部产品 / 公司级 / 指定多产品"三类语义
- 新增: `ProductType.parent_code`、`ProductType.level` 字段，支持产品科目多层树形结构
- 新增: `ProductMultiSelectDialog.tsx` 分层多选产品弹窗，支持父级展开到叶子节点
- 新增: Excel 导入"新增/更新"与"覆盖"两种模式（upsert/replace）
- 修改: 产品编码规则从 `Z+4位` 放宽为 `Z+4~8位`，兼容层级编码
- 修改: 数据科目 CRUD 全链路适配 `product_codes`
- 修改: 预算数据导入结果区分新增/覆盖/失败统计
- 移除: `data_account.applies_to_all_products` 字段及关联 CHECK 约束

### 已知待解决问题
- product_type 表的 `parent_code`/`level` 列通过 ALTER TABLE 补充，尚未纳入 `init_db.py` 新建表 DDL（待下一轮固化）
- `dept_product_mapping` 仍强制一产品一部门约束，多部门对应一产品的需求待专项改造
- `budget_summary` 重建仍使用 `dept_by_product` 字典，多部门场景下仅最后一个部门生效

### 风险评估
- 高风险: 4 项（核心数据模型变更，影响公式引擎、预算汇总、导入导出链路）
- 中风险: 4 项
- 低风险: 2 项

### PDD 更新
- System PDD: 新增 §0.7 本轮需求变更（2026-05-06）— ZLC
- Database PDD: 新增 §0.2 本轮同步说明（2026-05-06）— ZLC
- Files.md: ZLC 已追加 2026-05-06 更新摘要

### 数据库迁移
- `data_account`: `ALTER TABLE ADD COLUMN product_codes TEXT`，数据已从 `applies_to_all_products` + `product_code` 迁移
- `product_type`: `ALTER TABLE ADD COLUMN parent_code TEXT`，`ALTER TABLE ADD COLUMN level INTEGER DEFAULT 1`

---

---

## v2.0 (2026-04-29) — PDD 文档体系建立与项目初始化

### 变更来源
- 项目初始化阶段，未按团队成员拆分

### 变更明细
- 新增: 完整 PDD 文档体系 (System/Database/Agent/Rules/ERD/Files)
- 新增: FastAPI 后端 + Vite React 前端项目骨架
- 新增: 三库架构 (common.db / budget_{year}.db / compare.db)
- 新增: LangGraph Agent 智能体框架
- 新增: 飞书机器人 WebSocket 通道
- 新增: Excel 导入导出功能
- 新增: 公式引擎与预算汇总预聚合
- 新增: 多版本管理与多年度对比透视
- 新增: RLBA 用户权限体系

### 风险评估
- 高风险: 0 项（初始化阶段）
- 中风险: 0 项
- 低风险: 0 项

### PDD 更新
- System PDD: v1.0 初始版本
- Database PDD: v2.0 初始版本
- Agent PDD: 初始版本
- Rules PDD: 初始版本
- Files.md: 初始版本

---
