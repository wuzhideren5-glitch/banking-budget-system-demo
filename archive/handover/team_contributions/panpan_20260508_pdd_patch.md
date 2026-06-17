# PDD 章节补丁 — panpan — 2026-05-08

> 历史归档说明：本文件是同事提交包原始补丁，不代表当前导航或代码结构。费用相关功能已按当前 `apps/web/src/app/workspaceCatalog.tsx` 与 `apps/api/app/routers/` 中的正式入口收敛；旧“只隐藏不删除”的说明不得再作为当前清理依据。

> 请主合并人使用 /merge-release 将此补丁内容合入正式 PDD。

---

## System PDD 建议新增 (§0.7)

- 新增**费用管理模块群**，覆盖从基础科目维护、数据同步、执行导入、预测录入到执行报表的完整链路。
- 新增**部门预算科目维护**模块：支持五级树状科目目录（一级至五级），每级科目可维护公式文本与排序号，支持从 Excel 源文件批量初始化导入。
- 新增**费用执行明细导入**模块：支持从桌面 Excel 源文件（`.xls` 格式）读取费用执行明细，经框架校验（预算部门、产品部门、预算科目三重映射）后预览并批量写入数据库。
- 新增**费用预测表**模块：支持按"主体 / 事业群 / 费用归属部门"三种维度切换，提供月度单元格编辑（回车纵向、Tab 横向、方向键导航），支持追加导入与覆盖导入两种模式，并展示同比上年实际数据。
- 新增**费用预算执行报表**模块：提供"查询模式"与"模板模式"两种展示方式，支持"主体 / 事业群 / 费用归属部门"三视角切换，核心指标包括月度实际、累计实际、年度预算、执行率、预算进度、同比变动率；支持金额单位切换（元/千元/万元/百万元/亿元）。
- 新增**数据同步管理**模块：作为费用数据入口的总控台，负责从桌面源文件同步"费用整体框架"（预算部门、产品部门、预算科目）和"部门费用执行"实际明细，提供同步状态监控与一键重同步能力。
- **导航体系重构**：左侧导航"预算数据输入"更名为"部门费用输入"，"预算基础数据维护"更名为"部门费用数据维护"；新增"部门预算科目维护"、"费用执行明细导入"、"费用预测表"、"费用预算执行报表"、"数据同步管理"五个导航入口。
- **部门科目维护增强**：扩展部门科目维护能力，以支撑费用框架所需的责任部门与多层级部门路径展示；产品层级由产品科目维护独立承担。

> 插入位置：System PDD 的 `## 0.6` 之后，新增 `## 0.7` 小节。

---

## Database PDD 建议新增 (§1.X)

- 新增 `budget_subject_catalog` 表：部门预算科目目录，支持五级树状结构。
  - `id` INTEGER PRIMARY KEY AUTOINCREMENT
  - `parent_id` INTEGER REFERENCES budget_subject_catalog(id) ON DELETE RESTRICT
  - `level_number` INTEGER NOT NULL CHECK (1~5)
  - `subject_name` TEXT NOT NULL
  - `formula_text` TEXT
  - `sort_order` INTEGER NOT NULL DEFAULT 0
- 新增 `expense_sync_meta` 表：记录数据同步的元信息（源文件路径、修改时间、同步时间、行数、备注）。
  - `sync_key` TEXT PRIMARY KEY
  - `source_file` TEXT NOT NULL
  - `source_mtime` TEXT
  - `synced_at` TEXT NOT NULL
  - `row_count` INTEGER DEFAULT 0
  - `note` TEXT
- 新增 `expense_framework_budget_department` 表：费用框架之预算部门快照。
  - `entity_name`, `group_name`, `owner_name`, `budget_department`
  - UNIQUE (group_name, owner_name, budget_department)
- 新增 `expense_framework_product_department` 表：费用框架之产品部门快照。
  - `entity_name`, `group_name`, `owner_name`, `product_department`
  - UNIQUE (group_name, owner_name, product_department)
- 新增 `expense_framework_subject` 表：费用框架之预算科目快照。
  - `budget_subject` TEXT PRIMARY KEY
  - `level_label`, `manage_department`, `formula_text`, `sort_order`
- 新增 `expense_execution_monthly` 表：费用执行月度汇总数据。
  - `owner_name`, `budget_subject`, `month` (1~12), `amount`
  - UNIQUE (owner_name, budget_subject, month)
- 新增 `expense_forecast_entry` 表：费用预测数据。
  - `forecast_year`, `forecast_version`, `scope_type` ('entity'/'group'/'owner')
  - `scope_value`, `subject_id` REFERENCES budget_subject_catalog(id)
  - `month` (1~12), `forecast_value`, `create_time`, `update_time`
  - UNIQUE (forecast_year, forecast_version, scope_type, scope_value, subject_id, month)
  - INDEX: (forecast_year, forecast_version, scope_type, scope_value)

> 插入位置：Database PDD 的 `§1.8`（period 表）之后，新增 `§1.9` 小节。

---

## Agent PDD 建议新增

本次无 Agent 变更，无需更新。

---

## 补充说明

1. **依赖变更**：`apps/api/requirements.txt` 新增 `xlrd==2.0.1`，用于读取 `.xls` 格式的费用执行源文件。接收方需执行 `pip install -r apps/api/requirements.txt`。
2. **源文件约定（历史补丁，已废弃）**：早期方案曾要求费用同步管理默认读取桌面路径；当前主线已改为前端显式上传 Excel 后解析入库，后端不得再从部署机固定目录自动读取业务源文件。
3. **数据库迁移**：本次新增表通过 `apps/api/app/init_db.py` 中的 `ensure_databases()` 自动创建，无需手动迁移脚本。已有数据库在下次启动时会自动补齐新表。
4. **权限映射**：新增接口的权限等级已注册到 `main.py` 的 `_path_required_permission()` 中：
   - `/api/budget-subject-catalog` → 3（管理）
   - `/api/expense-actual-import` → 2（编辑）
   - `/api/expense-forecast` → 2（编辑）
   - `/api/expense-budget-execution/admin` → 3（管理）
   - `/api/expense-budget-execution` → 1（浏览）
5. **历史说明（已失效）**：原提交包曾采用“新增模块 + 隐藏旧入口”的过渡策略；当前主线已经删除旧报告科目入口与旧表，不再把“隐藏但保留”作为产品口径。正式事实以 `CONTEXT.md`、`docs/development/current-system-map.md` 和当前代码为准。
