# 银行业务预算管理系统及智能体（AI-Native Budget System）数据库设计文档


| 项目       | 说明                                                               |
| -------- | ---------------------------------------------------------------- |
| **文档版本** | v2.0                                                             |
| **产品定位** | 面向银行业务的财务预算原型系统，集成传统数据编报与 LangGraph 智能体分析，实现 AI 原生的预算管理与测算体验。 |
| **交付范围** | 与 **Rules「范围与演进」**、**System PDD §2.4** 一致：**当前目标版本为内网多用户**（登录会话、RBAC、HTTPS）；并支持“当前年度多版本透视”与“多年度对比透视（`compare.db`）”。 |
| **权威范围** | **本文档为数据库结构、字段约束与主数据编码规则的唯一权威。** Figma / `src_from_Figma/` 中的表格填充值、科目/产品编号样式等**仅为界面示例**；若与本文冲突，**迁移、API、持久化与校验以本文为准**，前端在绑定真实数据时须与本文对齐。 |


**相关文档**：[`Banking_Budget_Rules_PDD.md`](Banking_Budget_Rules_PDD.md)（工程底线）、[`Banking_Budget_System_PDD.md`](Banking_Budget_System_PDD.md)（产品功能与界面原则）、[`Banking_Budget_Database_ERD.md`](Banking_Budget_Database_ERD.md)（库表关系图）。**前端可交付代码**目录见 Rules **E.7**：仓库根下 **`src/`**（与 `src_from_Figma/` 平级）。

---

## 0.1 本轮同步说明（2026-04-28）

- 本轮需求调整不涉及数据库表结构变更（无新增/删除字段、无约束调整）。
- 变更主要发生在 Agent 问询展示与前端透视交互层：
  - 锁定维度区块改为紧凑展示（文案层）。
  - 透视建议说明去重（消息渲染层）。
  - 多年度对比透视保留 `pivot_search_text` 预填（前端筛选层）。
- 由于上述变更不改动持久化模型，本文各库表定义维持原版本有效。

## 0.2 本轮同步说明（2026-05-06）— ZLC

### 数据科目范围表达重构

- 废弃 `data_account.applies_to_all_products` 布尔字段，新增 `product_codes TEXT` 字段承载产品范围语义：
  - `product_codes IS NULL` 或空字符串 → 适用所有产品（等价旧 `applies_to_all_products=1`）
  - `product_codes = ''` → 公司级，未分配到具体产品
  - `product_codes = 'Z0001,Z0002'` → 逗号分隔的指定产品代码列表
- 旧 `product_code` 字段保留，但仅作历史兼容，写入时置 `NULL`，业务语义以 `product_codes` 为准。
- 原有 CHECK 约束 `(applies_to_all_products=1 AND product_code IS NULL) OR ...` 随字段废弃同步移除。
- 兼容迁移逻辑 `migrate_data_account_product_codes()` 在 `init_db.py` 中自动执行（`ALTER TABLE ADD COLUMN product_codes TEXT`）。

### 产品科目层级扩展

- `ProductType` 表新增 `parent_code` 和 `level` 字段（当前通过 ALTER TABLE 补充，尚未纳入新建表 DDL，待下一轮固化）：
  - `parent_code TEXT` → 父级产品代码，根节点为 `NULL`
  - `level INTEGER DEFAULT 1` → 层级深度
- 产品编码规则从 `Z + 4 位数字` 放宽为 `Z + 4~8 位数字`，兼容层级编码（如父级 Z01、子级 Z010101）。
- 前端的部门-产品映射树将使用产品自身层级替代部门树进行多选展示。

### 其他

- 本轮未新增独立业务表，对既有字段语义与兼容迁移逻辑进行了增强。
- 数据科目维护页的 Excel 导出需识别 `product_codes` 多值语义并正确展示。

## 0.3 本轮同步说明（2026-05-08）— merge-release

### 费用管理模块新增表

- 新增 `budget_subject_catalog`：部门预算科目目录，支持 1 至 5 级树状结构，字段包括 `id`、`parent_id`、`level_number`、`subject_name`、`formula_text`、`sort_order`。
- 新增 `expense_sync_meta`：费用数据同步元信息，记录同步键、源文件路径、源文件修改时间、同步时间、行数和备注。
- 新增 `expense_framework_budget_department`：费用框架中的预算部门快照，包含 `entity_name`、`group_name`、`owner_name`、`budget_department`。
- 新增 `expense_framework_product_department`：费用框架中的产品部门快照，包含 `entity_name`、`group_name`、`owner_name`、`product_department`。
- 新增 `expense_framework_subject`：费用框架中的预算科目快照，包含 `budget_subject`、`level_label`、`manage_department`、`formula_text`、`sort_order`。
- 新增 `expense_execution_monthly`：费用执行月度汇总，按 `owner_name + budget_subject + month` 唯一。
- 新增 `expense_actual_import_batch` 与 `expense_actual_detail_raw`：记录费用执行明细导入批次、原始行、匹配结果与失败原因。
- 新增 `expense_forecast_entry`：费用预测录入数据，按 `forecast_year + forecast_version + scope_type + scope_value + subject_id + month` 唯一，并新增查询索引 `idx_expense_forecast_lookup`。

### 合并约束

- 本轮保留 ZLC 已确立的 `data_account.product_codes` 多产品范围表达，不恢复来源包中的 `applies_to_all_products` 旧模型。
- 费用模块新增表通过 `init_db.ensure_databases()` 幂等创建；发版打包不包含 SQLite 数据库文件。

## 0.4 本轮同步说明（2026-05-08）— Codex

### 数据科目多层指标树规划

- 预算预测驱动与数据科目维护后续统一采用“指标树 + 产品继承”的业务层级模型，用于表达如 `01.01.01.Z0004` 这类“指标口径 + 产品编码”的完整业务编码。
- 该业务编码用于界面展示、树状归类、导入导出识别与预算预测驱动分组；产品末级编码必须直接复用 `product_type.product_code`，禁止另造一套产品维度编码。
- 推荐分层规则：
  - 上层指标节点采用数字分段编码（如 `01`、`01.01`、`01.01.01`）。
  - 产品化末级节点编码为 `上级指标节点编码 + "." + product_code`（如 `01.01.01.Z0004`）。

### 主键替换边界

- 本轮仅确认“业务层级编码”设计方向，**不直接替换** `data_account.data_acct_code` 主键。
- `data_acct_code` 仍为当前数据库、公式引用、`report_data_mapping`、`budget_data` 联合唯一键、导入模板识别键与历史审计链路的兼容主键。
- 若后续决定将 `data_acct_code` 从现行“字母 + 4 位数字”格式迁移为业务层级编码，必须作为单独的数据库主键迁移专题执行，并同步修订：
  - `DataAccount`、`ReportDataMapping`、`BudgetData` 等表结构与唯一性定义；
  - 预算/实际公式中的数据科目引用规则；
  - Excel 模板识别规则与导入导出约定；
  - 宽表 `budget_summary.data_code_name`、审计日志与跨年度历史库兼容策略。

## 0.5 本轮同步说明（2026-05-09）— merge-release

### 工作台与参数模板新增表

- 新增 `scenario_catalog`：预算假设场景目录，当前默认预置 `BASE` 基准场景，为后续多场景预测预留。
- 新增 `assumption_parameter`：预测参数目录，维护参数编码、名称、分类、数值类型、适用范围、时间粒度、取值方式、默认单位与启用状态。
- 新增 `assumption_value`：预测参数值，按 `parameter_code + budget_year + version_id + scenario_code + product_scope_key + month_index` 唯一，支持月度值与 `month_index=0` 年值。
- 新增 `assumption_rule_template`：预测规则模板，保存模板编码、名称、类型和 JSON 配置。
- 新增 `forecast_workbench_layout`：预测预算工作台行定义，保存开鑫贷/小小账户等预测行、分组、分类、排序与维护提示。
- 新增 `forecast_line_binding`：工作台行绑定表，用于记录预测行与数据科目、报表科目、假设参数、规则模板之间的绑定关系。
- `data_account` 兼容新增 `budget_rule_code` 与 `budget_rule_config_json`，用于后续把数据科目预算公式扩展为模板配置绑定；当前不替换已有 `budget_formula` 链路。
- 上述表与字段均由 `init_db.ensure_databases()` 幂等创建/补齐，并预置开鑫贷/小小账户首批工作台骨架、参数与模板种子。

## 0.6 本轮同步说明（2026-05-09）— Codex

### 数据科目编码与层级架构现行基线

- `data_account.data_acct_code` 是系统技术主键与稳定引用键，不承载完整业务层级语义；现有公式、报告映射、预算明细、导入导出、审计追溯仍以该字段作为底层引用。
- 新增数据科目时，`data_acct_code` 由后端自动生成，当前采用兼容历史数据的 `A####` 形态；用户不在前端手工填写该字段。
- 完整业务层级编码由 `data_account_metric_binding.binding_code` 承载，生成规则为 `metric_node_code + "." + scope_code`。
- `metric_node_code` 是多层数字分段指标节点编码，如 `01`、`01.01`、`01.01.31`；`scope_code` 为产品范围编码，产品级通常使用 `product_type.product_code`，公司级保留 `CORP` 作为特殊范围。
- 示例：`01.01.31.Z01010101` 表示某一指标树节点在产品 `Z01010101` 下的完整业务明细编码；产品中文名称必须从 `product_type.product_name` 读取，不在指标树中重复维护。
- 当前不将 `binding_code` 替换为 `data_acct_code` 主键；二者分工为：`data_acct_code` 负责系统引用稳定性，`binding_code` 负责业务层级展示、导入识别、预算预测驱动分类与用户理解。

### 指标树与绑定表

- 新增 `data_account_metric_node`：维护指标树本体，字段包括 `node_code`、`node_name`、`parent_code`、`level`、`node_type`、`sort_order`、`is_active`、`remark`、`created_at`、`updated_at`。
- 新增 `data_account_metric_binding`：维护指标节点与产品范围、数据科目的绑定关系，字段包括 `binding_code`、`metric_node_code`、`scope_type`、`scope_code`、`product_code`、`data_acct_code`、`sort_order`、`is_active`、`remark`、`created_at`、`updated_at`。
- 有效绑定应满足一对一业务明细关系：一个有效 `binding_code` 对应一个 `data_acct_code`，一个有效 `data_acct_code` 不应同时挂到多个有效 `binding_code`。若发现多绑定历史数据，需拆分为多个数据科目后再绑定。
- 指标树只表达“指标口径”层级，产品不作为额外树层重复挂载；产品维度通过绑定表的 `scope_code` / `product_code` 关联到 `product_type`。

### 报告映射、预算明细与预测驱动

- `report_data_mapping` 继续维护 `report_acct_code -> data_acct_code` 的映射，不直接绑定指标节点或产品范围；报告侧业务上下文通过 `data_acct_code` 反查 `data_account_metric_binding` 获得。
- `budget_data` 的物理粒度保持为 `data_acct_code × product_code × period_id × version_id × budget_actual`，其中 `budget_actual=0` 为预算，`budget_actual=1` 为实际。
- 预算预测驱动模块以 `data_account_metric_node + data_account_metric_binding + data_account` 作为当前主数据来源；旧 `driver_category`、`driver_indicator`、`driver_account_mapping` 仅作为历史兼容或导入兼容使用，不再作为驱动分类的唯一事实来源。
- 预测驱动只允许用户维护底层输入类数据科目；具有 `budget_formula` / `actual_formula` 的计算科目由重算链路按产品维度计算展示。
- 实际数与预算预测数必须来自同一套 `budget_data` 明细来源，区别仅由 `budget_actual` 口径标识；前端实际数单元格为只读展示。

### 已执行数据修复记录

- 2026-05-09 已对历史多绑定数据执行拆分：原先部分 `data_acct_code` 同时绑定多个 `binding_code`，已拆为“一条业务绑定对应一个数据科目”的形态。
- 修复前已备份数据库至 `data/backups/`；修复工具为 `backend/scripts/split_multi_metric_bindings.py`。
- 修复输出文件包括 `data/split_multi_metric_bindings_preview_20260509_160630.xlsx` 与 `data/split_multi_metric_bindings_applied_20260509_160655.xlsx`。
- 修复后有效多绑定数量为 0；有效指标绑定 624 条，数据科目 648 条，报告映射 714 条，报告映射孤儿记录 0。
- 公式文本中出现的旧 `data_acct_code` 仍是技术引用指针；如数据拆分影响公式引用目标，必须按公式含义复核并调整引用代码。

## 0.7 本轮同步说明（2026-05-09）— Codex

### 报告科目现行事实源与历史残留表

- `report_account` 是当前系统唯一运行时报告科目事实表；报告科目维护、预算基础数据维护、预算汇总、图表与智能查询均以该表为准。
- `report_account_new` 为历史导入或迁移试验残留表，不参与当前代码查询、写入、汇总与展示；不得以该表校验页面口径或作为新功能数据源。
- 如后续决定清理 `report_account_new`，需先完成数据库备份，并确认没有外部脚本或人工流程依赖该表。

### 预算基础数据维护展示规则

- 当前产品可见数据科目以 `data_account_metric_binding` 的有效绑定为主，匹配当前产品、其父级产品范围与 `CORP` 公司级范围。
- 仅在历史库不存在任何有效 `data_account_metric_binding` 时，才回退使用 `data_account.product_codes` 兼容筛选。
- 预算基础数据维护是录入视图，不允许同一个 `data_acct_code` 在同一产品、期间、版本与预算/实际口径下重复出现为多条可编辑行。
- 若 `report_data_mapping` 中一个 `data_acct_code` 映射到多个报告科目，预算输入页只选一个主报告路径展示；主路径选择规则为优先更深层级的报告科目，层级相同时按 `report_acct_code` 升序稳定选取。完整多映射关系仍保留在 `report_data_mapping` 中，待业务口径确认后再清理或标注。

---

## 命名约定（文档实体名与 SQLite 物理表名）

本仓库内 **AI 生成代码、迁移脚本与手写 SQL** 均以本节为权威；与 [`Banking_Budget_Rules_PDD.md`](Banking_Budget_Rules_PDD.md) 交叉阅读时，Rules 中的 **PascalCase** 与本节「逻辑实体」列一致，**物理表名**仅以下表第二列为准。

- **正文各小节标题**使用 **PascalCase**（如 `BudgetData`），表示**逻辑实体**，与 Rules、ORM 类名方向一致。
- **SQLite 真实表名**统一为 **snake_case**，与下表第二列**逐字一致**（含单复数：一律以下表为准，禁止自行按英文习惯加 `s` 等）。
- ORM 类名若与逻辑实体相同（如 `BudgetData`），**必须**显式声明物理表名为下表对应值（例如 SQLAlchemy `__tablename__ = "budget_data"`、TypeORM `@Entity({ name: 'budget_data' })`）；**禁止**在未核对本节的情况下将类名直接当作表名。

| 逻辑实体（文档标题） | SQLite 物理表名 | 所在库 |
| -------------------- | --------------- | ------ |
| `DataAccount` | `data_account` | `common.db` |
| `DataAccountMetricNode` | `data_account_metric_node` | `common.db` |
| `DataAccountMetricBinding` | `data_account_metric_binding` | `common.db` |
| `ReportAccount` | `report_account` | `common.db` |
| `ReportDataMapping` | `report_data_mapping` | `common.db` |
| `DeptAccount` | `dept_account` | `common.db` |
| `ProductType` | `product_type` | `common.db` |
| `DeptProductMapping` | `dept_product_mapping` | `common.db` |
| `Period` | `period` | `common.db` |
| `ChartTemplate` | `chart_template` | `common.db` |
| `OperationLog` | `operation_log` | `common.db` |
| `Users` | `users` | `common.db` |
| `Databases` | `databases` | `common.db` |
| `EditShowVersion` | `edit_show_version` | `common.db` |
| `Version` | `version` | `budget_{year}.db` |
| `Settings` | `settings` | `budget_{year}.db` |
| `BudgetData` | `budget_data` | `budget_{year}.db` |
| `BudgetSummary` | `budget_summary` | `budget_{year}.db` |
| `CompareBudgetSummary` | `compare_budget_summary` | `compare.db` |
| `CompareSyncJobLog` | `compare_sync_job_log` | `compare.db` |

**审计字段 `target_table`**：`operation_log.target_table` 填写受影响的 **SQLite 物理表名**（本表第二列，snake_case），与对照表逐字一致，便于检索与对账；勿填 PascalCase 逻辑实体名。

---

## 数据库表结构设计（Database Schema）

系统采用 SQLite 纯本地数据库，分为：

- **`common.db`**：通用字典库 + **全库统一操作日志**（`operation_log`，按时间追加；快照中须能还原业务年度与版本）  
- **`budget_{year}.db`**：年度预算数据分库（示例：`budget_yyyy.db`），含 `version`、`budget_data`、`budget_summary`
- **`compare.db`**：多年度对比透视只读库，承载 `compare_budget_summary` 与同步日志 `compare_sync_job_log`

**跨库逻辑引用与 SQLite 限制**：`budget_data.period_id` 在业务上指向 `common.db` 中 `period.period_id`。SQLite 的外键约束仅在**同一数据库文件**内可靠；若年度库与字典库为两个独立 `.db` 文件且未通过 `ATTACH` 统一到同一连接上下文建表，则**不宜**在 `budget_data` 上声明指向 `period` 的数据库级外键。实现须在应用层（或同步/导入流水线）保证 `period_id` 有效，或采用「`ATTACH common` + 约定 schema」或「年度库内冗余只读期间副本」等策略之一，并在 System PDD / 实现说明中定稿。

**年度库文件名**：`{year}` 建议与业务年度一致（如 `2026` → `budget_2026.db`）；与 `Period.year` 字段的 `Y2026` 形式不同属正常，打开文件时以约定规则解析即可。

**日期时间字符串**：`create_time`、`update_time`、`version_date_time` 等时刻字段，统一为 **ISO 8601** 字符串（推荐 UTC：`2026-04-10T08:30:00Z`，或带显式偏移如 `2026-04-10T16:30:00+08:00`）；同一字段在全库、API与导入导出中格式一致，避免混用多种写法。

---

### 1. 通用字典库（`common.db`）

**树表（`ReportAccount`、`DeptAccount`）**：`parent_code` 为指向本表主键（`report_acct_code` / `dept_code`）的自引用，根节点为 `NULL`。本文不强制约定数据库级外键及 `ON DELETE` 级联策略；**必须**在应用层保证无环、层级深度上限，以及删除或调整父节点时的依赖检查（参见 System PDD / 实现说明），避免孤儿节点及与映射表、明细数据不一致。

#### 1.1 DataAccount（数据科目）

用于存储最底层的财务数据科目项。


| 字段               | 类型     | 约束           | 说明                             |
| ---------------- | ------ | ------------ | ------------------------------ |
| `data_acct_code` | String | PK, Not Null | 数据科目代码，长度5 位：第 1 位大写字母，后 4 位数字 |
| `data_acct_name` | String | Not Null     | 科目名称                           |
| `product_code`   | String | Nullable, FK | 历史兼容字段；当前产品范围以 `product_codes` 与 `data_account_metric_binding` 为准 |
| `product_codes`  | Text   | Nullable     | 历史范围表达字段；多产品或全部产品兼容口径。新业务层级优先读取 `data_account_metric_binding.scope_code` / `product_code` |
| `applies_to_all_products` | Integer | Deprecated | 历史兼容字段；已由 `product_codes` 与指标绑定表替代，不作为新逻辑主口径 |
| `budget_formula` | Text   | Nullable     | 预算计算公式（由公式编辑器生成）               |
| `actual_formula` | Text   | Nullable     | 实际计算公式（由公式编辑器生成）               |
| `need_calc`      | Integer | Default 0 (`0/1`) | 公式变更标识：`1`=公式有变更待重算，`0`=无待重算；当预算式/实际式发生变化时置 `1`，对应口径重算完成后回写为 `0` |
| `value_type`     | String | Not Null     | **与「数据科目维护」界面中的「数值类型」列对应**（金额、百分比、户数等）；**存储小数位**见 **System PDD §2.2.1**。**并非**已废弃的 `budget_data.data_type`。库内可存界面展示名或稳定字典码，以实现与迁移策略为准。 |
| `remark`         | Text   | Nullable     | 备注                             |

**业务层级编码与指标树绑定（现行基线）**

- 为支撑“多层指标树 + 产品末级范围”的展示与维护体验，`DataAccount` 与 `data_account_metric_node`、`data_account_metric_binding` 联合表达完整业务路径。
- `data_acct_code` 继续作为技术主键与系统引用键；新增数据科目由后端自动编码，前端只展示“保存后系统生成”或保存后的实际代码。
- 完整业务编码由 `data_account_metric_binding.binding_code` 表达，格式为 `metric_node_code + "." + scope_code`，例如 `01.01.31.Z01010101`。
- 产品末级必须引用 `product_type.product_code`；产品名称展示始终来自 `product_type.product_name`，避免在指标树中重复维护第二份产品主数据。
- 有效状态下，同一个 `data_acct_code` 不应绑定多个 `binding_code`；如业务上需要拆分多个产品或多个指标口径，必须拆成多个数据科目。

**公式引用与重算口径约束（MUST）**

- 公式引用以 `data_acct_code` 作为稳定指针，但计算时必须带入当前产品上下文读取 `budget_data`。
- 当目标科目存在产品级绑定时，重算按绑定产品逐一执行并回写 `budget_data`；同一公式、不同产品独立求值。
- 保存接口必须校验公式引用范围，禁止将不适用当前产品范围的科目作为输入来源。


#### 1.1.1 DataAccountMetricNode（数据科目指标树节点）

用于维护数据科目的业务指标树。该表只表达指标口径层级，不表达产品维度。

| 字段 | 类型 | 约束 | 说明 |
| ---- | ---- | ---- | ---- |
| `node_code` | String | PK, Not Null | 指标节点编码，采用多层数字分段，如 `01`、`01.01`、`01.01.31` |
| `node_name` | String | Not Null | 指标节点名称，如“表内各项贷款”“贷款_日均”等 |
| `parent_code` | String | Nullable | 父级指标节点编码，根节点为 `NULL` |
| `level` | Integer | Not Null | 层级深度，由 `node_code` 分段推导并持久化 |
| `node_type` | String | Nullable | 节点类型，可用于区分目录、指标族、明细指标等 |
| `sort_order` | Integer | Default 0 | 同级排序 |
| `is_active` | Integer | Default 1 | 是否启用 |
| `remark` | Text | Nullable | 备注 |
| `created_at` | String | Nullable | 创建时刻，ISO 8601 |
| `updated_at` | String | Nullable | 更新时间，ISO 8601 |

**约束与生成规则**

- `node_code` 必须能由点号分段识别层级；新增子节点时由系统根据父节点下最大序号自动生成下一段编码。
- 用户选择父节点和填写节点名称，不直接维护完整编码，避免多层指标树下的人为编码冲突。
- 节点删除或停用前，必须检查是否存在有效 `data_account_metric_binding` 子绑定。

#### 1.1.2 DataAccountMetricBinding（数据科目指标绑定）

用于维护“指标节点 + 产品范围 + 数据科目”的一对一业务明细关系。

| 字段 | 类型 | 约束 | 说明 |
| ---- | ---- | ---- | ---- |
| `binding_code` | String | PK, Not Null | 完整业务层级编码，格式为 `metric_node_code + "." + scope_code` |
| `metric_node_code` | String | Not Null | 指向 `data_account_metric_node.node_code` |
| `scope_type` | String | Not Null | 范围类型，如 `PRODUCT`、`CORP` |
| `scope_code` | String | Not Null | 范围编码；产品级取 `product_type.product_code`，公司级取 `CORP` |
| `product_code` | String | Nullable | 产品级绑定时指向 `product_type.product_code`；公司级为 `NULL` |
| `data_acct_code` | String | Not Null | 指向 `data_account.data_acct_code` |
| `sort_order` | Integer | Default 0 | 同指标节点下展示排序 |
| `is_active` | Integer | Default 1 | 是否启用 |
| `remark` | Text | Nullable | 备注 |
| `created_at` | String | Nullable | 创建时刻，ISO 8601 |
| `updated_at` | String | Nullable | 更新时间，ISO 8601 |

**唯一性与读取规则**

- `binding_code` 为完整业务编码主键，必须唯一。
- 有效记录中，`data_acct_code` 应保持唯一；一个数据科目不应同时表示多个业务明细。
- `binding_code` 可用于导入导出和前端展示，但预算明细落库仍需解析到 `data_acct_code + product_code`。
- 预算预测驱动、预算基础数据维护、报告映射联查均通过本表取得数据科目的指标树上下文。

#### 1.2 ReportAccount（报告科目）

用于构建预算报告的树状科目展示结构；**最多5 层**，编辑界面需约束最大层级深度。


| 字段                 | 类型      | 约束           | 说明                                                  |
| ------------------ | ------- | ------------ | --------------------------------------------------- |
| `report_acct_code` | String  | PK, Not Null | 第1 级：`1 位大写字母 X` + `2 位数字`；下一级为上一级代码 + `2 位数字`，依此类推 |
| `report_acct_name` | String  | Not Null     | 报告科目名称                                              |
| `parent_code`      | String  | Nullable     | 父级代码（根节点为 `NULL`）                                   |
| `is_summary`       | Integer | Default 1    | 是否为汇总节点（1：是，0：否）                                    |
| `is_minus`         | Integer | Default 0    | 汇总时是否取反（1：取相反数，0：否）                                 |
| `level`            | Integer | Not Null     | 层级深度（最多 5 级）                                        |
| `is_leaf`          | Integer | Default 0    | 是否为叶子节点                                             |
| `remark`           | Text    | Nullable     | 备注                                                  |


#### 1.3 ReportDataMapping（报告科目 ↔ 数据科目）

维护报告科目叶子节点与底层数据科目的**多对多**关系。


| 字段                 | 类型      | 约束                 | 说明     |
| ------------------ | ------- | ------------------ | ------ |
| `id`               | Integer | PK, Auto Increment | —      |
| `report_acct_code` | String  | FK                 | 关联报告科目 |
| `data_acct_code`   | String  | FK                 | 关联数据科目 |


**联合唯一约束**：`(report_acct_code, data_acct_code)`

**层级语义说明（2026-05-09）**

- 本表仍只存报告科目到数据科目的映射，不存 `metric_node_code`、`binding_code` 或产品范围。
- 报告展示、预算基础数据维护、预算预测驱动如需读取指标树层级，应通过 `report_data_mapping.data_acct_code -> data_account_metric_binding.data_acct_code -> data_account_metric_node.node_code` 联查。
- 该设计保证报告映射继续以稳定技术键为准，同时允许数据科目维护页和预算预测驱动页用业务层级编码组织展示。

#### 1.4 DeptAccount（部门科目）

用于组织架构树状展示；**最多 3 层**，编辑界面需约束最大层级深度。


| 字段            | 类型      | 约束           | 说明                                                   |
| ------------- | ------- | ------------ | ---------------------------------------------------- |
| `dept_code`   | String  | PK, Not Null | 第 1 级：`1 位大写字母 Y` + `1 位数字`；下一级为上一级代码 + `1 位数字`，依此类推 |
| `dept_name`   | String  | Not Null     | 部门名称                                                 |
| `parent_code` | String  | Nullable     | 父级代码（根节点为 `NULL`）                                    |
| `level`       | Integer | Not Null     | 层级深度（最多 3 级）                                         |
| `is_leaf`     | Integer | Default 0    | 是否为叶子节点                                              |


#### 1.5 ProductType（产品科目）

存储最细粒度的业务产品项。


| 字段             | 类型     | 约束           | 说明                           |
| -------------- | ------ | ------------ | ---------------------------- |
| `product_code` | String | PK, Not Null | 长度 5 位：第 1 位大写字母 `Z`，后 4 位数字 |
| `product_name` | String | Not Null     | 产品名称                         |
| `remark`       | Text   | Nullable     | 备注                           |


#### 1.6 DeptProductMapping（部门叶子节点 → 产品）

维护部门叶子节点到产品科目的**一对多**关系（部门一侧一对多，产品一侧至多归属一个部门）。


| 字段             | 类型      | 约束                 | 说明     |
| -------------- | ------- | ------------------ | ------ |
| `id`           | Integer | PK, Auto Increment | —      |
| `dept_code`    | String  | FK                 | 关联部门科目 |
| `product_code` | String  | FK, Unique         | 关联产品科目（全表唯一，产品不可重复映射到多个部门） |


**唯一约束**：`product_code`（确保单个产品仅可映射到一个部门叶子节点）

#### 1.7 Period（期间）

存储标准年月时间维度；**`quarter`** 供分季度汇总等场景与 `period_id` 直接关联使用。


| 字段           | 类型      | 约束                 | 说明            |
| ------------ | ------- | ------------------ | ------------- |
| `period_id`  | Integer | PK, Auto Increment | —             |
| `year`       | String  | Not Null           | 年度，示例：`Y2026` |
| `month`      | String  | Not Null           | 月份，示例：`M03`   |
| `quarter`    | String  | Not Null           | 自然季度，取值 **`Q1`** / **`Q2`** / **`Q3`** / **`Q4`**；与 `month` 对应关系固定（M01–M03→`Q1`，M04–M06→`Q2`，M07–M09→`Q3`，M10–M12→`Q4`）。在 **生成或初始化 `period` 表数据时一次性静态写入**，与同行 `year`/`month` 一致，不单独手工改填 |
| `year_month` | String  | Not Null, Unique   | 示例：`2026-01`  |
| `days`       | Integer | Not Null           | 该月天数          |


#### 1.8 ChartTemplate（图表模板）

存储用户定义的 ECharts 分析图表配置。


| 字段              | 类型      | 约束                 | 说明              |
| --------------- | ------- | ------------------ | --------------- |
| `template_id`   | Integer | PK, Auto Increment | —               |
| `template_name` | String  | Not Null           | 模板名称            |
| `chart_type`    | String  | Not Null           | 图表类型            |
| `config_json`   | Text    | Not Null           | ECharts JSON 配置 |
| `create_time`   | String  | —                  | 创建时刻，ISO 8601（见上文「日期时间字符串」） |
| `update_time`   | String  | —                  | 更新时刻，ISO 8601 |
| `remark`        | Text    | Nullable           | 备注              |


#### 1.9 OperationLog（操作日志）

全库**单一**审计表，位于 **`common.db`**；按 **`create_time`** 时间序追加，**不按编报年度分文件**。须满足 Rules **E.2**「凡改必记」。**`action_desc`、`before_data`、`after_data`**（或等价 JSON）中**必须**能识别本次操作涉及的**业务年度**（如打开的 `budget_{year}.db` 之年份、`Period.year`）及 **`version_id` / 版本名称**（若变更与某年度预算库相关）；变更仅影响 `common.db` 字典时亦须如此说明上下文，避免事后无法对账。


| 字段              | 类型      | 约束                 | 说明                        |
| --------------- | ------- | ------------------ | ------------------------- |
| `log_id`        | Integer | PK, Auto Increment | —                         |
| `user_id`       | String  | Nullable           | —                         |
| `action_type`   | String  | Not Null           | 如 `UPDATE`、`AGENT_MODIFY` |
| `action_desc`   | Text    | Not Null           | 自然语言描述；**须含或可解析出**业务年度、版本等上下文（见上文） |
| `target_table`  | String  | Nullable           | 受影响表：SQLite **物理表名**（snake_case），见「命名约定」 |
| `affected_rows` | Integer | Nullable           | 影响行数                      |
| `before_data`   | Text    | Nullable           | 变更前 JSON 快照               |
| `after_data`    | Text    | Nullable           | 变更后 JSON 快照               |
| `ip_address`    | String  | Nullable           | —                         |
| `create_time`   | String  | —                  | 记录时刻，ISO 8601；排序与追溯主键之一 |


#### 1.10 Users（用户）

用于系统登录身份与权限管理。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | 用户ID |
| `user_name` | String | Not Null, Unique | 用户名称（全局唯一） |
| `first_login_password` | Text | Not Null | 首次登录密码（按已确认需求明文存储） |
| `daily_login_password` | Text | Nullable | 日常登录密码（加密存储） |
| `permission_type` | Integer | Not Null | 用户类型：`1`=全权管理员，`2`=数据录入用户，`3`=数据浏览用户 |
| `first_login_flag` | Integer | Not Null, Default 1 | 首次登录标记：`1`=首次登录需改密，`0`=非首次 |
| `create_time` | String | Not Null | 创建时间，ISO 8601 |
| `update_time` | String | — | 更新时间，ISO 8601 |

权限映射约定（按已确认口径）：
- 全权管理员：拥有权限 1/2/3。
- 数据录入用户：拥有权限 1/2。
- 数据浏览用户：拥有权限 1。

#### 1.11 Databases（年度库清单）

用于维护 `data/` 目录下可用年度预算库文件。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | 随机ID/主键 |
| `data_file_name` | String | Not Null, Unique | 年度库文件名（如 `budget_2026.db`） |
| `year` | Integer | Not Null | 库所属年份 |
| `create_time` | String | Not Null | 库创建时间（精确到秒，ISO 8601） |

#### 1.12 EditShowVersion（编辑/展示版本控制）

用于定义当前唯一可编辑版本与最多5个展示对比版本。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | 随机ID/主键 |
| `data_file_id` | Integer | Not Null, FK | 关联 `databases.id` |
| `version_id` | Integer | Not Null | 对应年度库 `version.version_id` |
| `edit_show_sign` | Integer | Not Null | `0`=当前可编辑版本，`1..5`=展示层级版本 |

约束：
- 全局仅允许一条 `edit_show_sign=0`（唯一当前编辑版本）。
- `edit_show_sign=1..5` 每个层级最多一条记录。

---

### 2. 年度预算分库（`budget_{year}.db`）

#### 2.1 Version（版本管理）


| 字段                  | 类型      | 约束                 | 说明        |
| ------------------- | ------- | ------------------ | --------- |
| `version_id`        | Integer | PK, Auto Increment | —         |
| `version_date_time` | String  | Not Null           | 版本时间戳，ISO 8601；前端创建时自动生成 |
| `version_name`      | String  | Not Null           | 版本名称 |
| `current_month`     | Integer | Not Null, Check(1-13) | 当前月份（1-13）。`1` 表示年度刚开始，`13` 表示年度结束。用于预算值/实际值录入开放区间控制与透视取数口径控制。 |

`current_month` 业务规则（与 `budget_data` 强一致）：
- `X=current_month` 时，`1..X-1` 月只允许 `budget_actual=1`（实际）；
- `X..12` 月只允许 `budget_actual=0`（预算）；
- `X=1` 全年仅预算；`X=13` 全年仅实际。
- 新版本继承父版本时，迁移记录必须按以上窗口筛选，不允许先全量复制再依赖展示层过滤。


#### 2.2 Settings（年度库配置）

每个年度库必须包含 `settings` 表，记录年度元信息。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | 随机ID/主键 |
| `setting_key` | String | Not Null | 标识：`year` / `create_user` / `create_time` |
| `setting_value` | Text | Not Null | 对应内容值 |

说明：
- `year` 必须对应 `common.db.period` 中存在的业务年度。
- `create_time` 精确到秒并使用 ISO 8601。

#### 2.3 BudgetData（底层预算明细）

全行最核心的数据表，仅存储**最底层颗粒度**的预算数据。


| 字段               | 类型      | 约束                 | 说明                                |
| ---------------- | ------- | ------------------ | --------------------------------- |
| `id`             | Integer | PK, Auto Increment | —                                 |
| `data_acct_code` | String  | Not Null           | 关联数据科目 |
| `product_code`   | String  | Not Null           | **产品维度**：该明细行所属产品（`product_type.product_code`）。同一数据科目如适用多个产品，应在库内按产品分别落行。 |
| `period_id`      | Integer | Not Null           | 关联期间                              |
| `budget_actual`  | Integer | Not Null           | **`0`** = **预算**口径数值（与界面「预算值」一致），**`1`** = **实际**口径数值（与界面「实际值」一致）；持久化层须校验仅为 `0` 或 `1`。不再使用已废弃的 `data_type` 列。 |
| `version_id`     | Integer | FK                 | 关联版本                              |
| `value`          | Float   | Default 0.0        | 具体数值                              |
| `need_calc`      | Integer | Default 1 (`0/1`)  | `1` = 需重算，`0` = 已算                |
| `create_time`    | String  | —                  | 创建时刻，ISO 8601                                 |
| `update_time`    | String  | —                  | 更新时刻，ISO 8601                                 |


**联合唯一约束**：`(data_acct_code, product_code, period_id, version_id, budget_actual)`  

业务粒度为 **数据科目 × 产品 × 期间 × 版本 × 预算/实际口径**（`budget_actual`）。**数值类科目区分**（金额/百分比/户数等）由 **`DataAccount.value_type`** 表达，**与** `budget_data` **无关**；**`need_calc`** 为引擎/任务标脏字段，**无对应界面控件**（见 System PDD）。

**编码引用说明（2026-05-09）**：`budget_data.data_acct_code` 引用的是技术主键，不直接解析业务层级。若需要按指标树或完整业务编码查询预算/实际值，必须先通过 `data_account_metric_binding` 将 `binding_code` 解析到 `data_acct_code` 与 `product_code`，再读取本表。实际数与预算数同源，差异仅由 `budget_actual` 区分。

预算输入 Excel 导入（模板与落库）约束：
- 模板文件：`download_template/budget_data_temp.xlsx`。
- 工作表：`预算数据` 写 `budget_actual=0`，`实际数据` 写 `budget_actual=1`。
- 识别键：第6列数据科目代码 + 第8列产品科目代码；月度值取第10~21列（M1~M12）。
- 代码提取：导入识别时仅取代码单元格前5位（兼容“代码+名称”全文单元格）。
- 公式互斥：若该数据科目在对应口径存在公式（预算看 `budget_formula`，实际看 `actual_formula`），则该口径导入必须失败并给出失败原因。

**命名更新说明**：本版本将历史命名 `needs_calc` 统一为 `need_calc`（语义不变）。实现层需在初始化/迁移时兼容旧库列名并完成数据回填，避免运行期 SQL 字段不一致。

#### 2.4 BudgetSummary（多维预聚合宽表）

用于**数据透视表-当前年度多版本透视**与前台快速查询；由后端定期生成写入，**用户不得直接改本表**。

**展开逻辑（摘要）**：报告科目树由一维表递归展开，经 `ReportDataMapping` 连到数据科目；部门树递归展开，经 `DeptProductMapping` 连到产品；再结合 `Version`、`Period`、`BudgetData` 等展开为宽表行。时间维度上冗余 **`year` / `month` / `quarter`**（与 `Period` 一致）。每一逻辑行须携带与明细一致的 **`budget_actual`**（与 `budget_data` 及界面「预算值/实际值」一致），以便透视与联查。


| 字段                                | 类型      | 约束                 | 说明                                                                     |
| --------------------------------- | ------- | ------------------ | ---------------------------------------------------------------------- |
| `id`                              | Integer | PK, Auto Increment | —                                                                      |
| `report_level1` … `report_level5` | String  | Nullable           | 各级报告科目展示（`report_acct_code` + `report_acct_name`）                      |
| `dept_level1` … `dept_level3`     | String  | Nullable           | 各级部门路径展示（`dept_code` + `dept_name` 拼接）                                 |
| `data_code_name`                  | String  | Not Null           | 数据科目全称（`data_acct_code` + `data_acct_name`）                            |
| `product_code_name`               | String  | Nullable           | 产品全称（`product_code` + `product_name`）                                  |
| `year`                            | String  | Not Null           | 年度，与 `Period.year` 同形：`Y2026`                                          |
| `month`                           | String  | Not Null           | 月份，与 `Period.month` 同形：`M03`                                           |
| `quarter`                         | String  | Not Null           | 自然季度，与 `Period.quarter` 同形（`Q1` / `Q2` / `Q3` / `Q4`）；由预聚合任务按关联 `Period` 冗余写入，供分季汇总与透视 |
| `budget_actual`                   | Integer | Not Null           | 与 `BudgetData` 一致：**`0`** = 预算口径，**`1`** = 实际口径；由预聚合任务写入 |
| `version_id`                      | Integer | FK                 | 版本 ID                                                                  |
| `version_name`                    | String  | Nullable           | 版本名称（冗余展示；与 `Version.version_name` 一致写入，或查询时 JOIN `Version` 带出） |
| `value`                           | Float   | Default 0.0        | 数值口径以计算引擎为权威，须与本行维度及在线展示一致；具体由引擎按展开规则自 `BudgetData` 派生或与单条明细对齐，以实现与 System PDD 为准                                        |
| `value_type`                      | String  | Not Null           | 来自 `DataAccount`                                                       |
| `update_time`                     | String  | —                  | 行数据刷新时刻，ISO 8601；语义与同口径 `BudgetData` /引擎任务一致，以实现为准 |


---

### 3. 多年度对比库（`compare.db`）

#### 3.1 CompareBudgetSummary（多年度对比透视宽表）

用于**数据透视表-多年度对比透视**，承载最多5组展示版本的只读快照数据。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | — |
| `show_level` | Integer | Not Null, Check(1-5) | 展示层级（1-5） |
| `data_file_id` | Integer | Not Null | 来源年度库ID（对应 `common.db.databases.id`） |
| `source_year` | Integer | Not Null | 来源年度 |
| `source_version_id` | Integer | Not Null | 来源版本ID |
| `source_version_name` | String | Nullable | 来源版本名称 |
| `report_level1` … `report_level5` | String | Nullable | 报告层级 |
| `dept_level1` … `dept_level3` | String | Nullable | 部门层级 |
| `data_code_name` | String | Not Null | 数据科目全称 |
| `product_code_name` | String | Nullable | 产品全称 |
| `year` | String | Not Null | 年度（`Y2026`） |
| `month` | String | Not Null | 月份（`M03`） |
| `quarter` | String | Not Null | 季度（`Q1`..`Q4`） |
| `budget_actual` | Integer | Not Null | `0`=预算口径，`1`=实际口径 |
| `value` | Float | Default 0.0 | 数值 |
| `value_type` | String | Not Null | 数值类型 |
| `sync_time` | String | Not Null | 同步时间，ISO 8601 |

#### 3.2 CompareSyncJobLog（对比库同步日志）

记录每次 compare 同步任务，保障可追溯。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `job_id` | Integer | PK, Auto Increment | 同步任务ID |
| `start_time` | String | Not Null | 任务开始时间，ISO 8601 |
| `end_time` | String | Nullable | 任务结束时间，ISO 8601 |
| `trigger_source` | String | Not Null | 触发源：`manual` / `auto_after_setting_save` / `auto_on_system_page_open` |
| `status` | String | Not Null | `success` / `failed` / `partial` |
| `message` | Text | Nullable | 任务摘要或错误信息 |
| `operator_user_id` | Integer | Nullable | 操作用户ID（对应 `users.id`） |

同步约束：
- 同步以 `common.db.edit_show_version` 为权威，只同步 `edit_show_sign=1..5` 的记录。
- 同步失败时不得清空已有可用快照，需保留旧数据并写入失败日志。
