# 银行业务预算管理系统及智能体（AI-Native Budget System）数据库设计文档


| 项目       | 说明                                                               |
| -------- | ---------------------------------------------------------------- |
| **文档版本** | v2.0                                                             |
| **产品定位** | 面向银行业务的财务预算原型系统，集成传统数据编报与 LangGraph 智能体分析，实现 AI 原生的预算管理与测算体验。 |
| **交付范围** | 与 **Rules「范围与演进」**、**System PDD §2.4** 一致：**当前目标版本为内网多用户**（登录会话、RBAC、HTTPS）；并支持“当前年度多版本透视”与“多年度对比透视（`compare.db`）”。 |
| **权威范围** | **本文档为数据库结构、字段约束与主数据编码规则的唯一权威。** 历史 Figma 导出或归档前端样例中的表格填充值、科目/产品编号样式等**仅为界面示例**；若与本文冲突，**迁移、API、持久化与校验以本文为准**，前端在绑定真实数据时须与本文对齐。 |


**相关文档**：[`Banking_Budget_Rules_PDD.md`](Banking_Budget_Rules_PDD.md)（工程底线）、[`Banking_Budget_System_PDD.md`](Banking_Budget_System_PDD.md)（产品功能与界面原则）、[`Banking_Budget_Database_ERD.md`](Banking_Budget_Database_ERD.md)（库表关系图）。当前前端应用位于 **`apps/web/`**，后端应用位于 **`apps/api/`**；历史根目录 `src/` 与 `src_from_Figma/` 已从活仓根目录删除，不是归档入口、开发入口或交付入口。

---

> 2026-06-10 当前口径：旧 `product_type` 物理维护表和同名运行视图均已下线删除；当前运行产品清单由服务直接从 `org_product_tree_snapshot` 展开。本文早期章节中把 `product_type` 描述为物理主数据表的内容，以 `CONTEXT.md`、`docs/development/current-system-map.md` 和 `docs/development/current-database-inventory.md` 的当前事实为准。

## 0. 当前数据库权威基线（2026-06-02）

本文只记录当前运行库合同、表关系和禁止依赖。历史合并说明、团队补丁、回退包和归档 Excel 不再作为数据库设计正文；需要追溯时读取 `.scratch/architecture-deep-clean/` 与 `archive/`，不得据此恢复旧入口或旧表。

### 表归属与依赖规则

运行库表归属清单见 `.scratch/architecture-deep-clean/TABLE_OWNERSHIP.md`。后续迁移、重构和删除必须先更新该清单，再同步本文与 ERD。

- **事实表**：可作为业务事实源，但只能通过 owner Module 的 Interface 读写。
- **投影表**：由事实表重建，不允许作为反向维护入口。
- **Adapter 表**：仅用于导入、外部集成或带明确删除期限的数据改造；新业务不得把 adapter 表升级为主事实源，也不得用它恢复旧口径兼容入口。
- **Private 表**：即使物理上位于 `common.db`，也只属于一个专业 Module；其他 Module 不得直接 SQL 依赖。

### 当前主事实源

- **数据科目身份**：只由 `data_account.data_acct_code` 表达，且必须等于产品前缀指标主键 `data_account_metric_binding.metric_node_code`。
- **指标口径**：只由 `data_account_metric_node` 表达；面向产品的节点编码采用 `产品码.产品内指标码`，例如 `A01.01.01.001`。
- **产品编码**：`product_code` 是查询/展示维度，产品名称和层级只从“机构及产品”主表读取；运行 SQL 通过服务内 CTE 展开 `org_product_tree_snapshot`，`data_account_metric_binding.scope_code` 由产品前缀派生并仅用于绑定校验。
- **旧指标编码处理**：当前启动链路和活跃运维脚本均不再把旧 `metric_node_code + scope_code`、旧本地指标节点或旧后缀式 `data_acct_code` 自动改写为产品前缀指标主键；旧五级迁移/语义重整脚本已从 `apps/api/scripts/` 删除。运行库若出现这些旧编码，应清理/重导，而不是作为兼容输入继续进入当前 Module。
- **旧产品预算工作台处理**：`product_budget_component*` 与配置包只属于退休表清理范围；旧工作台补齐、去重、绑定范围合并和旧目录重建脚本已从 `apps/api/scripts/` 删除，不得作为当前 **机构及产品指标** 的迁移入口。
- **预算/实际明细**：只由年度库 `budget_data` 表达；写入和数据科目删除联动清理必须通过 **BudgetDataWriter**。
- **预算汇总与对比**：`budget_summary`、`budget_pivot_aggregate`、`compare_budget_summary`、`compare_pivot_aggregate` 均为投影或快照，不得作为人工维护入口。

### 已退休兼容源与私有表

- `report_account` / `report_data_mapping` 已于 2026-05-19 从当前 schema 和运行库删除。报告展示、预算汇总、图表和智能查询必须读取 `data_account_metric_node`、`data_account_metric_binding`、`data_account` 与年度库事实/投影，不得恢复这两张旧表。
- `driver_category` / `driver_indicator` / `driver_product` / `driver_account_mapping` 已随旧“预算驱动因素页面”下线而退休；模拟测算只保留测算 Interface，基准值读取 **机构及产品指标体系**、**机构产品指标运行引用** 与年度库事实。
- `forecast_workbench_layout` / `forecast_line_binding` / `scenario_catalog` / `assumption_parameter` / `assumption_value` / `assumption_rule_template` 已随隐藏“预测工作台 / 假设参数”页面退休；不得恢复为第二套预测配置语言。
- `chart_template` 已于 2026-05-19 从当前 schema 和运行库删除；多年度数据透视图按页面请求实时读取汇总数据，智能 PPT 图表配置使用 `smart_ppt_chart_config` 私有表，不得恢复 `chart_template` 为全局图表模板主数据。
- `dept_name_alias` 已从当前部门费用链路删除；部门改名通过费用私有表引用同步完成，不再保留旧部门名称作为后续导入别名。
- `control_item_subject_mapping` 已从当前 BI 映射和费用执行明细导入链路退休；导入预算科目兜底只读取 `bi_ai_subject_mapping`，不得恢复旧 BI 科目维护表。
- `smart_report_*`、`smart_ppt_*`、`expense_*`、`business_cost_income_*` 是对应专业 Module 私有表，不应出现在全局主数据依赖链中。

### 当前部门费用数据库关系

- **费用框架快照链路**：费用框架导入写入 `expense_framework_budget_department`、`expense_framework_product_department`、`expense_framework_subject`，同步元数据只记录在 `expense_sync_meta.framework_import`；框架应用到主数据时更新 `dept_account` 与 `budget_subject_catalog`，并只写 `expense_sync_meta.master_apply`。
- **费用执行明细链路**：`expense_actual_import_batch` 记录本年实际、本年预算和上年实际三类批次；`expense_actual_detail_raw` 保存原始行、匹配结果和 `import_kind`。本年实际报表只读取 `current_year_actual`，去年同期优先读取 `prior_year_actual`，本年预算导入用于后续费用闭环口径，不替代年度库 `budget_summary`。
- **BI 映射链路**：`bi_ai_subject_mapping` 负责 BI 六级科目到预算发布口径、费用类别、费用大类的映射，是当前唯一 BI 科目类维护表；`manage_dept_owner_mapping` 负责归口管理部门到费用归属部门的映射，允许费用归属部门选择“其他”后由用户手动填写。
- **费用预测链路**：`expense_forecast_entry`、`expense_forecast_annual_entry`、`expense_forecast_rule*`、`expense_forecast_calc_result` 和 `expense_forecast_override` 是费用预测私有表；实际数读取来自当前费用执行明细 Adapter，不从旧月度快照取数。指标表达式变量可通过费用预测页面、Excel 导入和 API 请求先填写 `source_type=org_product_metric` 机构产品引用，保存/试算/导入应用工作流会在进入计算或持久化前解析成 `source_type=metric_tree`、`source_key=data_acct_code`、`source_subkey=实体/产品编码`；只读来源说明 `org_product_refs` 从 `org_product_metric_table` 回填给 API/页面和规则模板候选 sheet，不写入 `expense_forecast_rule_variable`，数据库仍只保存当前计算合同字段。
- **费用预算执行报表链路**：报表读模型综合 `budget_summary` 年度预算/上一年实际、`expense_actual_detail_raw` 当前导入实际、`expense_actual_import_batch` 来源说明、`budget_subject_catalog` 部门预算科目树、`dept_account` 主体/事业群/费用归属部门和费用框架快照；HTTP 路由不得恢复旧 `expense_execution_monthly`。
- **投入产出/成本收入比链路**：`business_cost_income_item`、`business_cost_income_indicator`、`business_cost_income_value` 和 `business_cost_income_source_mapping` 是年度库内成本收入比与投入产出专题私有表。`item` 按产品模板维护投入/产出明细，并可记录 `data_acct_code`、手工录入模式和取值模式；`indicator` 按产品维护指标树，支持父级、分组、专题指标节点、分子/分母取值模式、年化和 `number` 格式；`source_mapping` 只承载成本收入比明细/指标到当前数据科目口径的来源映射。启动初始化仅在无产品模板且无 `business_cost_income_value` 业务值时重播模板，不得覆盖已有人工值；不得恢复来源包旧 `bcir_*` 第二套模型表。
- **机构及产品指标树链路**：`org_product_tree_snapshot`、`org_product_metric_table`、`org_product_metric_table_catalog`、`org_product_data_entry_snapshot`、`org_product_data_entry_snapshot_v2`、`org_product_data_entry_draft`、`org_product_output_snapshot_v1` 是 `common.db` 内的机构及产品滚动预测表，也是唯一主指标配置源。该链路承载机构/产品树、单机构指标表、月内公式、数据录入草稿/提交和预测输出快照。`data_account_metric_node`、`data_account`、`data_account_metric_binding` 已直接采用机构及产品指标体系的编码、名称和层级；不得继续扩展第二套指标配置入口、中间映射层或保留旧数据科目编码语义。机构产品数据录入版本确认后可显式同步预算事实，同步入口只把已确认、已进入同一数据科目体系的月度实际/预测单元格交给 BudgetDataWriter 写入年度库 `budget_data`；写入成功后重建同一预算版本的 `budget_summary` 和 `budget_pivot_aggregate`，并更新预算全局刷新时间。
- **潘潘费用类迁移结果**：潘潘旧费用类已并入机构及产品指标体系，机构产品指标运行引用直接使用机构及产品指标主键，不再保留独立迁移区。

---

## 命名约定（文档实体名与 SQLite 物理表名）

本仓库内 **AI 生成代码、迁移脚本与手写 SQL** 均以本节为权威；与 [`Banking_Budget_Rules_PDD.md`](Banking_Budget_Rules_PDD.md) 交叉阅读时，Rules 中的 **PascalCase** 与本节「逻辑实体」列一致，**SQLite 对象名**仅以下表第二列为准；标注为运行视图的对象不得作为物理维护表恢复。

- **正文各小节标题**使用 **PascalCase**（如 `BudgetData`），表示**逻辑实体**，与 Rules、ORM 类名方向一致。
- **SQLite 真实表名/视图名**统一为 **snake_case**，与下表第二列**逐字一致**（含单复数：一律以下表为准，禁止自行按英文习惯加 `s` 等）。
- ORM 类名若与逻辑实体相同（如 `BudgetData`），**必须**显式声明物理表名为下表对应值（例如 SQLAlchemy `__tablename__ = "budget_data"`、TypeORM `@Entity({ name: 'budget_data' })`）；**禁止**在未核对本节的情况下将类名直接当作表名。

| 逻辑实体（文档标题） | SQLite 物理表名 | 所在库 |
| -------------------- | --------------- | ------ |
| `DataAccount` | `data_account` | `common.db` |
| `DataAccountMetricNode` | `data_account_metric_node` | `common.db` |
| `DataAccountMetricBinding` | `data_account_metric_binding` | `common.db` |
| `OrgProductTreeSnapshot` | `org_product_tree_snapshot` | `common.db` |
| `DeptAccount` | `dept_account` | `common.db` |
| `OrgProductRuntimeCatalog` | 运行产品清单（服务内展开） | `common.db` |
| `Period` | `period` | `common.db` |
| `OperationLog` | `operation_log` | `common.db` |
| `Users` | `users` | `common.db` |
| `Databases` | `databases` | `common.db` |
| `EditShowVersion` | `edit_show_version` | `common.db` |
| `Version` | `version` | `budget_{year}.db` |
| `Settings` | `settings` | `budget_{year}.db` |
| `BudgetData` | `budget_data` | `budget_{year}.db` |
| `BudgetSummary` | `budget_summary` | `budget_{year}.db` |
| `BudgetPivotAggregate` | `budget_pivot_aggregate` | `budget_{year}.db` |
| `CompareBudgetSummary` | `compare_budget_summary` | `compare.db` |
| `ComparePivotAggregate` | `compare_pivot_aggregate` | `compare.db` |
| `CompareSyncJobLog` | `compare_sync_job_log` | `compare.db` |

**审计字段 `target_table`**：`operation_log.target_table` 填写受影响的 **SQLite 物理表名**（本表第二列，snake_case），与对照表逐字一致，便于检索与对账；勿填 PascalCase 逻辑实体名。

---

## 数据库表结构设计（Database Schema）

系统采用 SQLite 纯本地数据库，分为：

- **`common.db`**：通用字典库 + **全库统一操作日志**（`operation_log`，按时间追加；快照中须能还原业务年度与版本）
- **`budget_{year}.db`**：年度预算数据分库（示例：`budget_yyyy.db`），含 `version`、`settings`、`budget_data`、`budget_summary`、`budget_pivot_aggregate` 与年度私有业务表
- **`compare.db`**：多年度对比透视只读库，承载 `compare_budget_summary`、`compare_pivot_aggregate` 与同步日志 `compare_sync_job_log`

**跨库逻辑引用与 SQLite 限制**：`budget_data.period_id` 在业务上指向 `common.db` 中 `period.period_id`。SQLite 的外键约束仅在**同一数据库文件**内可靠；若年度库与字典库为两个独立 `.db` 文件且未通过 `ATTACH` 统一到同一连接上下文建表，则**不宜**在 `budget_data` 上声明指向 `period` 的数据库级外键。实现须在应用层（或同步/导入流水线）保证 `period_id` 有效，或采用「`ATTACH common` + 约定 schema」或「年度库内冗余只读期间副本」等策略之一，并在 System PDD / 实现说明中定稿。

**年度库文件名**：`{year}` 建议与业务年度一致（如 `2026` → `budget_2026.db`）；与 `Period.year` 字段的 `Y2026` 形式不同属正常，打开文件时以约定规则解析即可。

**日期时间字符串**：`create_time`、`update_time`、`version_date_time` 等时刻字段，统一为 **ISO 8601** 字符串（推荐 UTC：`2026-04-10T08:30:00Z`，或带显式偏移如 `2026-04-10T16:30:00+08:00`）；同一字段在全库、API与导入导出中格式一致，避免混用多种写法。

---

### 1. 通用字典库（`common.db`）

**树表（`DataAccountMetricNode`、`DeptAccount`）**：`parent_code` 为指向本表主键（指标树 `node_code` / 部门树 `dept_code`）的自引用，根节点为 `NULL`。本文不强制约定数据库级外键及 `ON DELETE` 级联策略；**必须**在应用层保证无环、层级深度上限，以及删除或调整父节点时的依赖检查（参见 System PDD / 实现说明），避免孤儿节点及与绑定表、明细数据不一致。

#### 1.1 DataAccount（数据科目）

用于存储最底层的财务数据科目项。


| 字段               | 类型     | 约束           | 说明                             |
| ---------------- | ------ | ------------ | ------------------------------ |
| `data_acct_code` | String | PK, Not Null | 唯一指标号码；格式为 `产品码.产品内指标码` |
| `data_acct_name` | String | Not Null     | 科目名称                           |
| `budget_formula` | Text   | Nullable     | 预算计算公式（由公式编辑器生成）               |
| `actual_formula` | Text   | Nullable     | 实际计算公式（由公式编辑器生成）               |
| `budget_rule_code` | String | Nullable | 预算规则模板编码；用于规则化预算公式配置 |
| `budget_rule_config_json` | Text | Nullable | 预算规则模板参数 JSON |
| `need_calc`      | Integer | Default 0 (`0/1`) | 公式变更标识：`1`=公式有变更待重算，`0`=无待重算；当预算式/实际式发生变化时置 `1`，对应口径重算完成后回写为 `0` |
| `formula_calc_mode` | Integer | Default 0, Check(0-3) | 公式配置状态：`0`=无公式，`1`=仅预算公式，`2`=仅实际公式，`3`=预算/实际均有公式；由保存接口按公式字段派生 |
| `allow_manual_entry` | Integer | Default 1 (`0/1`) | 是否允许手工补录：`1`=允许，`0`=不允许；由机构及产品指标保存链路同步维护，预算基础数据写入与导入以此字段判断公式科目是否锁定 |
| `value_type`     | String | Not Null     | 数据科目运行字段，表示金额、百分比、户数等数值类型；由机构及产品指标保存链路同步，不再通过独立数据科目维护界面编辑。**存储小数位**见 **System PDD §2.2.1**。**并非**已废弃的 `budget_data.data_type`。库内可存展示名或稳定字典码，以实现与迁移策略为准。 |
| `remark`         | Text   | Nullable     | 备注                             |

**当前物理表合同（2026-06-01）**：`data_account` 只允许上表字段集合。历史 `legacy_product_code`、`legacy_dimension` 或缺少 `budget_rule_code` / `budget_rule_config_json` / `need_calc` / `formula_calc_mode` / `allow_manual_entry` / `value_type` 的旧表不是兼容输入；启动链路发现后必须失败并要求清理/重建 `common.db`，不得自动补列、改名、回填或重建旧表。

**业务层级编码与指标树绑定（现行基线）**

- 为支撑“产品内指标树”的展示与维护体验，`DataAccount` 与 `data_account_metric_node`、`data_account_metric_binding` 联合表达完整业务路径。
- 指标层级只由 `data_account_metric_node` 表达；`data_account_metric_binding.metric_node_code` 负责把唯一指标号码挂到指标树节点，不在 `DataAccount` 内重复保存指标族或层级字段。功能相似但口径未必一致的指标通过 `functional_group_code` 显式归族。
- `data_acct_code` 继续作为系统引用键，且必须等于唯一指标号码。
- 唯一指标号码由 `data_account.data_acct_code` 表达，目标格式为 `metric_node_code` 本身（当 `metric_node_code` 已含产品前缀，如 `A05.01.01.001`）；绑定表解释该号码对应的指标节点和查询产品。
- 产品末级必须引用“机构及产品”主表编码；运行查询通过服务展开 `org_product_tree_snapshot` 读取产品名称和层级，避免在指标树中重复维护第二份产品主数据。
- 有效状态下，同一个 `data_acct_code` 不应绑定多个指标节点；如业务上需要拆分多个产品或多个指标口径，必须拆成多个数据科目。

**公式引用与重算口径约束（MUST）**

- 公式引用以 `data_acct_code` 作为稳定指针，但计算时必须带入当前产品上下文读取 `budget_data`。
- 当目标科目存在产品级绑定时，重算按绑定产品逐一执行并回写 `budget_data`；同一公式、不同产品独立求值。
- 保存接口必须校验公式引用，禁止将不适用当前产品前缀的科目作为输入来源。


#### 1.1.1 DataAccountMetricNode（数据科目指标树节点）

用于维护数据科目的业务指标树。该表用产品前缀表达产品内指标层级。

| 字段 | 类型 | 约束 | 说明 |
| ---- | ---- | ---- | ---- |
| `node_code` | String | PK, Not Null | 指标节点编码，产品根如 `A01`，正式节点如 `A01.01.01.001` |
| `node_name` | String | Not Null | 指标节点名称，如“表内各项贷款”“贷款_日均”等 |
| `parent_code` | String | Nullable | 父级指标节点编码，根节点为 `NULL` |
| `product_code` | String | Nullable | 由 `node_code` 产品前缀派生，产品根节点等于自身编码 |
| `local_metric_code` | String | Nullable | 由 `node_code` 去掉产品前缀后派生；产品根节点为空 |
| `logic_code` | String | Nullable | 不含产品前缀的逻辑码，用于跨产品横向汇总和同类指标识别 |
| `functional_group_code` | String | Nullable | 指标功能族，仅用于相似指标比较和治理 |
| `level` | Integer | Not Null | 层级深度，由 `node_code` 分段推导并持久化 |
| `node_type` | String | Not Null | 节点类型：`CATEGORY`、`GROUP`、`METRIC` |
| `horizontal_rollup` | Integer | Not Null, Default 0 | 是否按 `logic_code` 跨产品横向汇总 |
| `vertical_rollup` | Integer | Not Null, Default 0 | 是否按子节点纵向汇总 |
| `sort_order` | Integer | Default 0 | 同级排序 |
| `is_active` | Integer | Default 1 | 是否启用 |
| `remark` | Text | Nullable | 备注 |
| `created_at` | String | Not Null | 创建时刻，ISO 8601 |
| `updated_at` | String | Not Null | 更新时间，ISO 8601 |

**约束与生成规则**

- `node_code` 必须能由点号分段识别层级；当前正式指标叶子为五级码，第三、第四段是业务语义层，不再使用 `.00.00` 占位层。新增子节点时由系统根据父节点下最大序号自动生成下一段编码。
- 用户选择父节点和填写节点名称，不直接维护完整编码，避免多层指标树下的人为编码冲突。
- `product_code`、`local_metric_code`、`level` 必须与 `node_code` 派生结果一致；启动链路发现旧本地指标表缺列或派生字段不一致时直接失败，不再自动补列、回填或修正。
- 节点删除或停用前，必须检查是否存在有效 `data_account_metric_binding` 子绑定。

#### 1.1.2 DataAccountMetricBinding（数据科目指标绑定）

用于维护“产品前缀指标节点 + 数据科目”的一对一业务明细关系。

| 字段 | 类型 | 约束 | 说明 |
| ---- | ---- | ---- | ---- |
| `data_acct_code` | String | PK, Not Null | 唯一指标号码；等于产品前缀 `metric_node_code` |
| `metric_node_code` | String | Not Null | 指向 `data_account_metric_node.node_code` |
| `scope_type` | String | Not Null | 当前产品类型为 `PRODUCT`；历史 `CORP` 仅作为旧库清洗/迁移识别值，不再作为机构及产品指标主键口径 |
| `scope_code` | String | Not Null | 产品编码；必须等于 `metric_node_code` 的产品前缀 |
| `sort_order` | Integer | Default 0 | 同指标节点下展示排序 |
| `is_active` | Integer | Default 1 | 是否启用 |
| `remark` | Text | Nullable | 备注 |
| `created_at` | String | Not Null | 创建时刻，ISO 8601 |
| `updated_at` | String | Not Null | 更新时间，ISO 8601 |

**唯一性与读取规则**

- `data_acct_code` 为唯一指标号码主键，必须唯一。
- 物理约束必须保证 `data_acct_code = metric_node_code`，且 `scope_code` 等于 `metric_node_code` 的产品前缀；旧绑定表约束 `data_acct_code = metric_node_code || '.' || scope_code` 不是兼容输入。
- 有效记录中，一个数据科目不应同时表示多个业务明细。
- 新业务导入导出和前端展示只使用 `data_acct_code`；产品维度数据科目的预算明细也使用同一 `data_acct_code` 写入。
- 预算输入、模拟测算、费用预测指标表达式和预算展示联查均通过本表取得数据科目的指标树上下文。

#### 1.2 BudgetOutputDisplayItem（预算输出展示配置）

`budget_output_display_item` 是当前预算展示报表的展示行配置表。它不是旧 `report_account` 的恢复版；展示行可指向 `data_account.data_acct_code`，预算事实和指标身份仍以 **机构及产品指标体系** 与 **机构产品指标运行引用** 为准。通过机构产品指标候选创建展示行时，系统额外保存 `org_product_*` 追溯身份，用于后续从预算展示配置、预算展示报表页面和 Excel 导出反查目标机构及产品指标体系；这些字段不参与预算展示计算，且优先级高于按 `data_acct_code` 反查出的泛化来源列表。删除运行引用记录时，系统只解除展示行的 `data_acct_code`、`org_product_*`、`row_type` 和 `value_type` 取数绑定，保留展示结构行本身，避免把展示布局误删成运行引用附属物。

| 字段 | 类型 | 约束 | 说明 |
| ---- | ---- | ---- | ---- |
| `row_key` | String | PK, Not Null | 展示行编码 |
| `display_view` | String | Not Null | 展示视图，如全行、分产品、单产品 |
| `parent_row_key` | String | Nullable | 父展示行 |
| `data_acct_code` | String | Nullable | 可关联唯一指标号码 |
| `org_product_ref` | String | Nullable | 机构产品指标来源引用，格式 `entity:table:metric`，只作追溯 |
| `org_product_entity_code` | String | Nullable | 来源机构/产品编码，只作追溯 |
| `org_product_table_name` | String | Nullable | 来源机构产品指标表名，只作追溯 |
| `org_product_metric_code` | String | Nullable | 来源机构产品指标编码，只作追溯 |
| `org_product_metric_name` | String | Nullable | 来源机构产品指标名称，只作追溯 |
| `row_type` | String | Not Null | `GROUP` 或 `METRIC` |
| `display_name` | String | Not Null | 展示名称 |
| `value_type` | String | Nullable | 展示值类型 |
| `level` | Integer | Not Null | 展示层级 |
| `sort_order` | Integer | Not Null | 同级排序 |
| `is_active` | Integer | Not Null | 是否启用 |

#### 1.3 Retired Report Tables（已退休报告科目表）

`report_account` 与 `report_data_mapping` 已从当前 schema 与运行库删除。报告展示、预算汇总、图表、Agent 查询和模拟测算不得再依赖这两张表；需要展示层级时读取 `budget_output_display_item`，需要业务指标身份时读取 `data_account_metric_node`、`data_account_metric_binding`、`data_account` 和年度预算事实/投影。

**模拟测算取数说明（2026-05-14）**

- 模拟测算正算、倒算和导出属于数据科目指标体系消费场景，应直接读取 `data_account_metric_node`、`data_account_metric_binding`、`data_account` 与年度库 `budget_data`。
- 模拟测算不得恢复 `report_account` 或 `report_data_mapping`；指标联动和产品下钻依据只来自标准指标树、数据科目绑定和年度预算事实。
- 当前模拟测算不新增表结构；若某业务指标在 `data_account_metric_binding` 中缺少绑定，应优先补齐指标绑定，而不是回退到新增报告科目映射。

#### 1.4 DeptAccount（部门科目）

用于部门科目维护页的组织架构展示；当前权威结构为 **两级部门科目**：`主体 -> 事业群 -> 费用归属部门`。费用发生部门不写入本表，属于 `expense_framework_budget_department` 的费用整体框架快照。


| 字段            | 类型      | 约束           | 说明                                                   |
| ------------- | ------- | ------------ | ---------------------------------------------------- |
| `dept_code`   | String  | PK, Not Null | 第 1 级：`1 位大写字母 Y` + `1 位数字`；下一级为上一级代码 + `1 位数字`，依此类推 |
| `dept_name`   | String  | Not Null     | 部门名称                                                 |
| `entity_name` | String  | Not Null     | 主体名称，示例：微众银行、科技子、科技孙等                              |
| `parent_code` | String  | Nullable     | 父级代码（根节点为 `NULL`）                                    |
| `level`       | Integer | Not Null     | 层级深度，当前只维护 1 级事业群与 2 级费用归属部门                         |
| `is_leaf`     | Integer | Default 0    | 是否为叶子节点                                              |

**当前数据口径（2026-05-19）**：本表已按 `resources/business_inputs/部门架构维护模版.xlsx` 重建为 37 条部门科目，且不得包含“开心账户 / 开鑫贷”等历史演示口径。若后续需新增事业群或费用归属部门，应先确认编码与主键影响，再通过部门架构维护导入或受控脚本写入。


#### 1.5 OrgProductTreeSnapshot 与 OrgProductRuntimeCatalog（机构及产品主表与运行产品清单）

`org_product_tree_snapshot` 存储“机构及产品”页面保存的完整产品/机构树，是产品维度唯一主表。旧产品科目维护物理表、产品科目导入、产品科目 CRUD 与独立产品维护页面均已下线删除。

旧 `product_type` 对象不再保留。运行产品清单由 `org_product_tree_snapshot.payload_json` 递归展开，用于预算展示、模拟测算、运行引用链路读取产品名称/层级。它不是配置入口，也不得作为导入或写入目标。

**`org_product_tree_snapshot` 字段**

| 字段             | 类型     | 约束           | 说明                           |
| -------------- | ------ | ------------ | ---------------------------- |
| `id`           | Integer | PK, Check(id=1) | 单例主表快照 |
| `payload_json` | Text   | Not Null     | 机构及产品树 JSON；包含编码、名称、节点类型和 children |
| `updated_at`   | String | Not Null     | 最近保存时间 |

**运行产品清单字段**


| 字段             | 类型     | 约束           | 说明                           |
| -------------- | ------ | ------------ | ---------------------------- |
| `product_code` | String  | PK, Not Null | 机构/产品编码，如 `AAA`、`AA`、`A`、`A01`、`A0101`；`AA` 表示微众银行实体 |
| `product_name` | String  | Not Null     | 产品名称                         |
| `parent_code`  | String  | Nullable     | 父级产品代码；根节点为 `NULL`             |
| `level`        | Integer | Default 1    | 产品层级                         |
| `remark`       | Text    | Nullable     | 固定说明，标识来源为机构及产品主表快照 |

**当前对象合同（2026-06-10）**：旧 `product_type` table/view 必须不存在；启动链路发现旧对象时直接删除。任何产品新增、更新、删除、模板下载、导入预览或导入应用都必须从“机构及产品”进入，不得恢复旧产品科目维护表。

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


#### 1.8 Retired ChartTemplate（已退休图表模板表）

`chart_template` 已从当前 schema 与运行库删除。多年度数据透视图按页面请求实时读取 `budget_pivot_aggregate` / `compare_pivot_aggregate`；智能演示 PPT 的图表配置由 `smart_ppt_chart_config` 作为智能 PPT 私有表维护，不恢复全局图表模板主数据。

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

用于维护 `var/data/` 目录下可用年度预算库文件。

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
| `product_code`   | String  | Not Null           | **产品维度**：该明细行所属产品；产品名称和层级由运行服务从机构及产品主表展开查询。同一数据科目如适用多个产品，应在库内按产品分别落行。 |
| `period_id`      | Integer | Not Null           | 关联期间                              |
| `budget_actual`  | Integer | Not Null           | **`0`** = **预算**口径数值（与界面「预算值」一致），**`1`** = **实际**口径数值（与界面「实际值」一致）；持久化层须校验仅为 `0` 或 `1`。不再使用已废弃的 `data_type` 列。 |
| `version_id`     | Integer | FK                 | 关联版本                              |
| `value`          | Float   | Default 0.0        | 具体数值                              |
| `formula_value`  | Float   | Nullable           | 公式/系统派生值；公式重算和父节点汇总写入此列 |
| `manual_value`   | Float   | Nullable           | 手工录入/导入值；手工值存在时优先生效 |
| `value_source`   | String  | Default `manual`   | 生效值来源，仅允许 `manual`、`formula`、`none`、`rollup` |
| `need_calc`      | Integer | Default 1 (`0/1`)  | `1` = 需重算，`0` = 已算                |
| `create_time`    | String  | —                  | 创建时刻，ISO 8601                                 |
| `update_time`    | String  | —                  | 更新时刻，ISO 8601                                 |


**联合唯一约束**：`(data_acct_code, product_code, period_id, version_id, budget_actual)`

业务粒度为 **数据科目 × 产品 × 期间 × 版本 × 预算/实际口径**（`budget_actual`）。**数值类科目区分**（金额/百分比/户数等）由 **`DataAccount.value_type`** 表达，**与** `budget_data` **无关**；**`need_calc`** 为引擎/任务标脏字段，**无对应界面控件**（见 System PDD）。

**编码引用说明（2026-05-16）**：`budget_data.data_acct_code` 统一使用唯一指标号码。实际数与预算数同源，差异仅由 `budget_actual` 区分。

**当前事实粒度说明（2026-06-01）**：`budget_data` 必须已经具备 `product_code` 与 `budget_actual` 字段。历史无产品维事实表、历史 `data_type` 口径列或其他旧事实粒度不是兼容输入，启动链路发现后必须失败并要求重建/清理年度库，不得自动展开到产品维或自动改写口径字段。

**当前取值合同说明（2026-06-01）**：`budget_data` 必须已经具备 `formula_value`、`manual_value`、`value_source`，且 `value_source` 约束必须允许 `manual`、`formula`、`none`、`rollup`。历史缺列事实表、旧三值 `value_source` 约束或需要按 `value` 猜测回填 `manual_value` 的旧数据不是兼容输入，启动链路发现后必须失败并要求重建/清理年度库。

预算输入 Excel 导入（模板与落库）约束：
- 模板文件：`resources/download_template/budget_data_temp.xlsx`。
- 工作表：`预算数据` 写 `budget_actual=0`，`实际数据` 写 `budget_actual=1`。
- 识别键：第6列唯一指标号码 + 第8列产品科目代码；月度值取第10~21列（M1~M12）。
- 代码提取：导入识别时读取唯一指标号码列中的 `产品码.产品内指标码`。
- 公式互斥：若该数据科目在对应口径存在公式（预算看 `budget_formula`，实际看 `actual_formula`），则该口径导入必须失败并给出失败原因。

**命名更新说明**：当前 schema 只允许 `need_calc`。历史 `needs_calc` 列不是兼容输入，启动链路发现后必须失败并要求重建/清理年度库，不得在运行时自动改名或回填。

#### 2.4 BudgetSummary（多维预聚合宽表）

用于**数据透视表-当前年度多版本透视**与前台快速查询；由后端定期生成写入，**用户不得直接改本表**。

**展开逻辑（摘要）**：指标树经 `DataAccountMetricBinding` 连到数据科目，产品维由 `BudgetData.product_code` 关联“机构及产品”主表编码，运行查询通过运行产品清单读取名称和层级；`DeptAccount` 只保留部门科目自身层级，`BudgetSummary` 不再通过全局部门-产品映射反推部门。时间维度上冗余 **`year` / `month` / `quarter`**（与 `Period` 一致）。每一逻辑行须携带与明细一致的 **`budget_actual`**（与 `budget_data` 及界面「预算值/实际值」一致），以便透视与联查。


| 字段                                | 类型      | 约束                 | 说明                                                                     |
| --------------------------------- | ------- | ------------------ | ---------------------------------------------------------------------- |
| `id`                              | Integer | PK, Auto Increment | —                                                                      |
| `metric_level1` … `metric_level5` | String  | Nullable           | 数据科目运行指标树层级，由 `DataAccountMetricNode` / `DataAccountMetricBinding` 展开 |
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
| `value_source`                    | String  | Default `manual`   | 生效值来源，与 `BudgetData.value_source` 同口径，用于区分手工、公式、空值与父节点汇总 |
| `update_time`                     | String  | —                  | 行数据刷新时刻，ISO 8601；语义与同口径 `BudgetData` /引擎任务一致，以实现为准 |

**当前投影结构合同（2026-06-01）**：`budget_summary` 只接受 `metric_level1` … `metric_level5` 作为指标层级字段。历史 `display_level*` / `report_level*` 投影列不是兼容输入，启动链路发现后必须失败并要求清理/重建年度库，不得自动改名或继续读取。


#### 2.5 BudgetPivotAggregate（当前年度透视预聚合表）

用于**数据透视表-当前年度多版本透视**的可重建预聚合表。该表由预算/实际跑批与透视聚合 Module 写入，不是人工维护表；前端只通过透视聚合接口读取，不直接依赖物理表名。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | — |
| `grain` | String | Not Null, Check(`year`,`quarter`,`month`) | 聚合粒度 |
| `metric_level1` … `metric_level5` | String | Nullable | 数据科目运行指标树层级 |
| `dept_level1` … `dept_level3` | String | Nullable | 部门层级 |
| `data_code_name` | String | Not Null | 数据科目全称 |
| `product_code_name` | String | Nullable | 产品全称 |
| `year` | String | Not Null | 年度（如 `Y2026`） |
| `month` | String | Not Null | 月份（如 `M03`）；年度/季度粒度下保留当前展开口径 |
| `quarter` | String | Not Null | 季度（`Q1`..`Q4`） |
| `budget_actual` | Integer | Not Null | `0`=预算口径，`1`=实际口径 |
| `version_id` | Integer | Not Null | 年度库版本 ID |
| `version_name` | String | Nullable | 版本名称 |
| `value` | Float | Default 0.0 | 聚合值 |
| `value_type` | String | Not Null | 数值类型 |
| `value_source` | String | Default `manual` | 生效值来源；当分组包含父节点汇总时保留 `rollup` 可追溯性 |
| `update_time` | String | Not Null | 聚合刷新时间，ISO 8601 |

**当前投影结构合同（2026-06-01）**：`budget_pivot_aggregate` 必须包含 `metric_level1` … `metric_level5` 与 `value_source`。历史 `report_level*` / `display_level*` 投影结构不是兼容输入；启动链路只在表缺失时创建当前表结构，已有表若缺少当前字段或包含退休层级字段必须直接失败，不得补列或静默改写。


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
| `metric_level1` … `metric_level5` | String | Nullable | 标准指标树层级 |
| `dept_level1` … `dept_level3` | String | Nullable | 部门层级 |
| `data_code_name` | String | Not Null | 数据科目全称 |
| `product_code_name` | String | Nullable | 产品全称 |
| `year` | String | Not Null | 年度（`Y2026`） |
| `month` | String | Not Null | 月份（`M03`） |
| `quarter` | String | Not Null | 季度（`Q1`..`Q4`） |
| `budget_actual` | Integer | Not Null | `0`=预算口径，`1`=实际口径 |
| `value` | Float | Default 0.0 | 数值 |
| `value_type` | String | Not Null | 数值类型 |
| `value_source` | String | Default `manual` | 生效值来源，与年度库投影同口径 |
| `sync_time` | String | Not Null | 同步时间，ISO 8601 |

#### 3.2 ComparePivotAggregate（多年度对比透视预聚合表）

用于**数据透视表-多年度对比透视**的可重建预聚合表。该表由 compare 同步或预算/实际跑批生成；它消费 `compare_budget_summary` 快照，不作为人工维护入口。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `id` | Integer | PK, Auto Increment | — |
| `grain` | String | Not Null, Check(`year`,`quarter`,`month`) | 聚合粒度 |
| `show_level` | Integer | Not Null, Check(1-5) | 展示层级（1-5） |
| `data_file_id` | Integer | Not Null | 来源年度库 ID（对应 `common.db.databases.id`） |
| `source_year` | Integer | Not Null | 来源年度 |
| `source_version_id` | Integer | Not Null | 来源版本 ID |
| `source_version_name` | String | Nullable | 来源版本名称 |
| `metric_level1` … `metric_level5` | String | Nullable | 数据科目运行指标树层级 |
| `dept_level1` … `dept_level3` | String | Nullable | 部门层级 |
| `data_code_name` | String | Not Null | 数据科目全称 |
| `product_code_name` | String | Nullable | 产品全称 |
| `year` | String | Not Null | 年度（如 `Y2026`） |
| `month` | String | Not Null | 月份（如 `M03`）；年度/季度粒度下保留当前展开口径 |
| `quarter` | String | Not Null | 季度（`Q1`..`Q4`） |
| `budget_actual` | Integer | Not Null | `0`=预算口径，`1`=实际口径 |
| `value` | Float | Default 0.0 | 聚合值 |
| `value_type` | String | Not Null | 数值类型 |
| `value_source` | String | Default `manual` | 生效值来源，与年度库投影同口径 |
| `sync_time` | String | Not Null | 同步时间，ISO 8601 |

**当前投影结构合同（2026-06-01）**：`compare_budget_summary` 与 `compare_pivot_aggregate` 均使用 `metric_level1` … `metric_level5`，并必须携带 `value_source`。历史 `report_level*` / `display_level*` 对比投影结构不是兼容输入。

#### 3.3 CompareSyncJobLog（对比库同步日志）

记录每次 compare 同步任务，保障可追溯。

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `job_id` | Integer | PK, Auto Increment | 同步任务ID |
| `start_time` | String | Not Null | 任务开始时间，ISO 8601 |
| `end_time` | String | Nullable | 任务结束时间，ISO 8601 |
| `trigger_source` | String | Not Null | 触发源；当前 compare 同步由“预算事实刷新跑批”统一触发，主口径为 `manual_budget_actual_batch` |
| `status` | String | Not Null | `success` / `failed` / `partial` |
| `message` | Text | Nullable | 任务摘要或错误信息 |
| `operator_user_id` | Integer | Nullable | 操作用户ID（对应 `users.id`） |

同步约束：
- 同步以 `common.db.edit_show_version` 为权威，只同步 `edit_show_sign=1..5` 的记录。
- 系统配置保存展示版本只更新槽位，不自动同步 compare；用户需在“预算事实刷新跑批”生成 `compare_budget_summary` 快照和 `compare_pivot_aggregate` 聚合表。
- 同步失败时不得清空已有可用快照，需保留旧数据并写入失败日志。
